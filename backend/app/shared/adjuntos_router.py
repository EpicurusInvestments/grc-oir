"""Factory de router genérico de adjuntos (subida/descarga) — ADR-042, extraída en F3.

Antes había DOS copias casi idénticas de este router (`ordenes/adjuntos.py`,
`facturacion/adjuntos.py`), con una nota explícita en la segunda diciendo que extraer
una factory con solo 2 consumidores era prematuro: "si F3 necesita el mismo patrón, ahí
sí valdrá la pena (tres consumidores identificados)". F3 es ese tercer consumidor —
esta factory reemplaza las dos copias sin cambiar su comportamiento observable; lo único
que cambia es dónde vive el código.

## Por qué NO lleva `from __future__ import annotations`

Ver **ADR-067** en `docs/arquitectura.md` — buscable ahí sin tener que abrir este
archivo primero. Resumen: es deliberado, no un descuido. El router construido aquí
acepta el tipo de `tipo` como parámetro (`tipos: type[StrEnum]`) para que cada módulo
declare SU propio enum de tipos
de adjunto (`TipoAdjuntoOrden`, `TipoAdjuntoFacturacion`...) y FastAPI siga generando el
`enum` correcto en OpenAPI —y el 422 automático ante un valor inválido— exactamente como
antes. Eso exige que la anotación `tipo: tipos = Query(...)` del endpoint interno se
resuelva en tiempo de DEFINICIÓN de la función (Python evalúa la anotación contra el
closure, ve el objeto `Enum` real). Con `from __future__ import annotations` las
anotaciones se guardan como texto y FastAPI las resolvería con `get_type_hints()` contra
los globals del módulo, donde `tipos` (variable local del closure) no existe — el enum
dinámico dejaría de funcionar. Python 3.12 no necesita el future import para la sintaxis
`X | None` de todos modos.

## Diferencias de comportamiento preservadas EXACTAS entre los dos consumidores actuales

Ambas eran reales antes de esta extracción y siguen siéndolo — no se "corrigieron" de
paso, porque el pedido explícito fue no cambiar comportamiento externo:

- `content_disposition`: `ordenes/adjuntos.py` usa `inline` (se previsualiza en el
  navegador); `facturacion/adjuntos.py` usa `attachment` (se descarga). Parámetro
  `content_disposition`.
- Nombre de archivo al descargar: `ordenes/adjuntos.py` LE QUITA el prefijo
  `<uuid_hex_32>_` a la clave para mostrar el nombre original; `facturacion/adjuntos.py`
  NO se lo quita (el nombre visible incluye el UUID). Parámetro
  `quitar_prefijo_uuid_en_descarga`. Se documenta aquí porque es fácil no notar la
  inconsistencia entre los dos módulos si alguien solo lee uno de ellos.

## Lo que sí se unificó (sin cambio de comportamiento)

- El esquema de respuesta: antes `AdjuntoOrdenRead`/`AdjuntoFacturacionRead`, dos clases
  con los DOS MISMOS campos (`ref`, `nombre_archivo`). Ahora una sola `AdjuntoRead`. El
  payload JSON es idéntico; lo único que cambia es el nombre del componente en el
  OpenAPI generado (nadie en el código ni en las pruebas lo referenciaba por nombre).
- `extension.lower()` antes de `content_type_de_extension()`: la función YA lowercasea
  internamente, así que quitar ese `.lower()` de F2 no cambia el resultado — se
  unifica al criterio más simple de F1.
"""

import uuid
from enum import StrEnum
from typing import Literal, TypeVar

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.documentos import (
    EXTENSIONES_ADJUNTO_ORDENES,
    content_type_de_extension,
    leer_adjunto,
)
from app.integrations.almacenamiento.port import AlmacenamientoPort


class AdjuntoRead(BaseModel):
    ref: str
    nombre_archivo: str


# `dict` es invariante en su tipo de clave: sin este TypeVar, `dict[TipoAdjuntoOrden, str]`
# (el enum CONCRETO de cada módulo) no sería aceptable donde se pide `dict[StrEnum, str]`.
_E = TypeVar("_E", bound=StrEnum)


def build_adjuntos_router(
    *,
    tag: str,
    tipos: type[_E],
    prefijos: dict[_E, str],
    permiso_subir: str,
    permiso_descargar: str,
    content_disposition: Literal["inline", "attachment"],
    quitar_prefijo_uuid_en_descarga: bool = False,
    extensiones_permitidas: frozenset[str] = EXTENSIONES_ADJUNTO_ORDENES,
) -> APIRouter:
    """Construye un router `/adjuntos` completo (subir + descargar) para un módulo.

    `tipos` y `prefijos` van separados (en vez de que `prefijos` sea el único parámetro
    y se infiera el enum de sus claves) para que la anotación `tipo: tipos = Query(...)`
    del endpoint de subida quede explícita y clara de leer aquí — ver el docstring del
    módulo sobre por qué esto exige evaluación inmediata de anotaciones.
    """
    router = APIRouter(prefix="/adjuntos", tags=[tag])
    prefijos_descargables = tuple(prefijos.values())

    # NO usar `from __future__ import annotations` en este módulo: `tipo: tipos` debe
    # resolver el objeto Enum real al definir la función (ver docstring del módulo).
    # mypy no puede verificar una anotación que es una VARIABLE en tiempo de ejecución —
    # es dinámico a propósito (cada módulo pasa su propio enum); FastAPI sí la resuelve
    # bien porque lee el objeto real, no una anotación estática.
    def subir_adjunto(
        tipo: tipos = Query(...),  # type: ignore[valid-type]
        archivo: UploadFile = File(...),
        usuario: CurrentUser = Depends(requiere_permiso(permiso_subir)),
        almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
    ) -> AdjuntoRead:
        """Valida (extensión + magic bytes + tamaño) y sube el adjunto; devuelve su clave.

        La clave incluye un UUID para no colisionar entre entidades distintas que
        compartan el mismo prefijo.
        """
        contenido, nombre_sano, extension = leer_adjunto(
            archivo,
            max_bytes=settings.s3_max_pdf_bytes,
            extensiones_permitidas=extensiones_permitidas,
        )
        nombre_clave = f"{uuid.uuid4().hex}_{nombre_sano}"
        clave = almacenamiento.subir(
            prefijo=prefijos[tipo],
            nombre_archivo=nombre_clave,
            contenido=contenido,
            content_type=content_type_de_extension(extension),
        )
        return AdjuntoRead(ref=clave, nombre_archivo=nombre_sano)

    def descargar_adjunto(
        ref: str = Query(..., description="Clave de almacenamiento devuelta al subir"),
        usuario: CurrentUser = Depends(requiere_permiso(permiso_descargar)),
        almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
    ) -> Response:
        # Guardarraíl: este endpoint SOLO sirve objetos de SUS propios prefijos. 404 y no
        # 403 a propósito: no se confirma la existencia de objetos de otros prefijos del
        # mismo bucket (p.ej. `contratos/`).
        if not ref.startswith(prefijos_descargables):
            return Response(status_code=404)
        contenido = almacenamiento.obtener(ref)
        base = ref.rsplit("/", 1)[-1]
        if quitar_prefijo_uuid_en_descarga:
            # La clave es "<uuid_hex_32>_<nombre_original>": se quita el prefijo UUID
            # para que la descarga muestre el nombre original al usuario.
            nombre = base[33:] if len(base) > 33 and base[32] == "_" else base
        else:
            nombre = base
        extension = nombre.rsplit(".", 1)[-1] if "." in nombre else ""
        return Response(
            content=contenido,
            media_type=content_type_de_extension(extension),
            headers={"Content-Disposition": f'{content_disposition}; filename="{nombre}"'},
        )

    router.post("", response_model=AdjuntoRead, status_code=201)(subir_adjunto)
    router.get("")(descargar_adjunto)
    return router
