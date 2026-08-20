"""Adjuntos de Órdenes (ODC, carta de conciliación, reportes de afiliado).

Antes "simulados" en el frontend (solo se capturaba el nombre del archivo, nunca se
subía nada). Un solo endpoint genérico de subida/descarga para los 5 campos que lo
necesitan (`OrdenCliente.odc_pdf_ref`, `odc_cerrada_ref`, `carta_conciliacion_ref`,
`OrdenEstacion.reporte_reales_ref`, `reporte_programados_ref`) — todos son columnas de
texto que ya existían como referencia simulada; ahora guardan la CLAVE real en el
almacenamiento (S3 o local, según `STORAGE_BACKEND`, mismo bucket que los adjuntos de
Contrato — ADR-027 — bajo un prefijo propio para no mezclarlos).

El bucket es PRIVADO: el archivo se sirve SIEMPRE por este endpoint, nunca por URL
pública directa (mismo criterio que Contrato).
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.documentos import content_type_de_extension, leer_adjunto
from app.integrations.almacenamiento.port import AlmacenamientoPort

router = APIRouter(prefix="/adjuntos", tags=["ordenes:adjuntos"])


class TipoAdjuntoOrden(StrEnum):
    ODC = "odc"
    CIERRE_ODC = "cierre_odc"
    CIERRE_CARTA = "cierre_carta"
    REPORTE_REALES = "reporte_reales"
    REPORTE_PROGRAMADOS = "reporte_programados"


# Prefijo propio por tipo (no se mezclan con `contratos/` ni entre sí).
_PREFIJOS: dict[TipoAdjuntoOrden, str] = {
    TipoAdjuntoOrden.ODC: "ordenes/odc/",
    TipoAdjuntoOrden.CIERRE_ODC: "ordenes/cierre/odc/",
    TipoAdjuntoOrden.CIERRE_CARTA: "ordenes/cierre/carta/",
    TipoAdjuntoOrden.REPORTE_REALES: "orden_estacion/reportes/reales/",
    TipoAdjuntoOrden.REPORTE_PROGRAMADOS: "orden_estacion/reportes/programados/",
}
# Único punto de entrada permitido para descargar por este endpoint (guardarraíl: no
# sirve para leer objetos de otros prefijos del mismo bucket, p.ej. `contratos/`).
_PREFIJOS_DESCARGABLES = tuple(_PREFIJOS.values())


class AdjuntoOrdenRead(BaseModel):
    ref: str
    nombre_archivo: str


@router.post("", response_model=AdjuntoOrdenRead, status_code=201)
def subir_adjunto_orden(
    tipo: TipoAdjuntoOrden = Query(...),
    archivo: UploadFile = File(..., description="Documento o imagen (máx. configurable)"),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> AdjuntoOrdenRead:
    """Valida (extensión + magic bytes + tamaño) y sube el adjunto; devuelve su clave.

    La clave incluye un UUID para no colisionar entre órdenes distintas que compartan
    el mismo prefijo (a diferencia de Contrato, aquí no hay un "número" estable para
    agrupar antes de que la orden exista).
    """
    contenido, nombre_sano, extension = leer_adjunto(archivo, max_bytes=settings.s3_max_pdf_bytes)
    prefijo = _PREFIJOS[tipo]
    nombre_clave = f"{uuid.uuid4().hex}_{nombre_sano}"
    clave = almacenamiento.subir(
        prefijo=prefijo,
        nombre_archivo=nombre_clave,
        contenido=contenido,
        content_type=content_type_de_extension(extension),
    )
    return AdjuntoOrdenRead(ref=clave, nombre_archivo=nombre_sano)


@router.get("")
def descargar_adjunto_orden(
    ref: str = Query(...),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    """Descarga/sirve un adjunto de orden a través del backend (bucket privado)."""
    if not ref.startswith(_PREFIJOS_DESCARGABLES):
        return Response(status_code=404)
    contenido = almacenamiento.obtener(ref)
    base = ref.rsplit("/", 1)[-1]
    # La clave es "<uuid_hex_32>_<nombre_original>" (ver subir_adjunto_orden); se quita
    # el prefijo UUID para que la descarga muestre el nombre original al usuario.
    nombre = base[33:] if len(base) > 33 and base[32] == "_" else base
    extension = nombre.rsplit(".", 1)[-1] if "." in nombre else ""
    return Response(
        content=contenido,
        media_type=content_type_de_extension(extension),
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
