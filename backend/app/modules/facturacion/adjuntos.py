"""Adjuntos de Facturación (XML/PDF del CFDI timbrado y archivos de proveedor).

Mismo patrón que `ordenes/adjuntos.py` (ADR-042): un solo endpoint genérico de
subida/descarga, lista blanca de extensiones y verificación de *magic bytes* — todo
reutilizando `integrations/almacenamiento/documentos.py`, que es la pieza genuinamente
genérica y neutral (no se importa nada del módulo `ordenes`).

**Por qué un router hermano y no extender el de F1** (regla de tres): extender
`ordenes/adjuntos.py` colgaría los archivos de facturación del prefijo `ordenes/` y haría
que F2 dependiera del módulo F1 por conveniencia. Extraer una factory compartida a
`app/shared/` con un solo segundo consumidor es prematuro: si F3 necesita el mismo patrón,
ahí sí valdrá la pena (tres consumidores identificados). Decisión del equipo, anotada aquí
para que la duplicación de ~40 líneas se lea como deliberada, no como descuido.

El bucket es PRIVADO: el archivo se sirve SIEMPRE por este endpoint, nunca por URL
pública directa.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.documentos import (
    EXTENSIONES_ADJUNTO_FACTURACION,
    content_type_de_extension,
    leer_adjunto,
)
from app.integrations.almacenamiento.port import AlmacenamientoPort

router = APIRouter(prefix="/adjuntos", tags=["facturacion:adjuntos"])


class TipoAdjuntoFacturacion(StrEnum):
    """Los 4 archivos que F2 necesita almacenar."""

    #: XML del CFDI devuelto por el PAC (`FacturaCliente.xml_path`).
    CFDI_XML = "cfdi_xml"
    #: PDF impreso del CFDI (`FacturaCliente.pdf_path`).
    CFDI_PDF = "cfdi_pdf"
    #: Factura recibida del afiliado (`FacturaAfiliado.archivo_path`).
    FACTURA_AFILIADO = "factura_afiliado"
    #: Factura recibida de la agencia (`FacturaAgencia.archivo_path`).
    FACTURA_AGENCIA = "factura_agencia"
    #: Respaldo de un costo adicional (`CostoAdicional.archivo_path`).
    RESPALDO_COSTO = "respaldo_costo"


# Prefijo propio por tipo: no se mezclan con `contratos/` ni con `ordenes/` ni entre sí.
_PREFIJOS: dict[TipoAdjuntoFacturacion, str] = {
    TipoAdjuntoFacturacion.CFDI_XML: "facturacion/cfdi/xml/",
    TipoAdjuntoFacturacion.CFDI_PDF: "facturacion/cfdi/pdf/",
    TipoAdjuntoFacturacion.FACTURA_AFILIADO: "facturacion/proveedor/afiliado/",
    TipoAdjuntoFacturacion.FACTURA_AGENCIA: "facturacion/proveedor/agencia/",
    TipoAdjuntoFacturacion.RESPALDO_COSTO: "facturacion/costos/respaldo/",
}
# Guardarraíl: este endpoint solo sirve objetos de SUS prefijos. No se puede usar para
# leer `contratos/` ni `ordenes/` del mismo bucket.
_PREFIJOS_DESCARGABLES = tuple(_PREFIJOS.values())


class AdjuntoFacturacionRead(BaseModel):
    ref: str
    nombre_archivo: str


@router.post("", response_model=AdjuntoFacturacionRead, status_code=201)
def subir_adjunto_facturacion(
    tipo: TipoAdjuntoFacturacion = Query(...),
    archivo: UploadFile = File(...),
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> AdjuntoFacturacionRead:
    """Sube un adjunto y devuelve su CLAVE de almacenamiento (`ref`).

    Esa `ref` es lo que se guarda en la columna correspondiente (`xml_path`, `pdf_path`,
    `archivo_path`) vía el endpoint de la entidad — este endpoint NO toca la base.

    Permiso: `costos:editar`. Los adjuntos del CFDI son de Facturación, pero Admin y CxP
    también los suben en la práctica; se usa la clave más amplia del módulo y la
    asignación de la `ref` a la factura sí queda gateada por el permiso de su entidad.
    """
    contenido, nombre_sano, extension = leer_adjunto(
        archivo,
        max_bytes=settings.s3_max_pdf_bytes,
        extensiones_permitidas=EXTENSIONES_ADJUNTO_FACTURACION,
    )
    # Prefijo con UUID para que dos archivos con el mismo nombre no se pisen (igual que F1).
    nombre_clave = f"{uuid.uuid4().hex}_{nombre_sano}"
    clave = almacenamiento.subir(
        prefijo=_PREFIJOS[tipo],
        nombre_archivo=nombre_clave,
        contenido=contenido,
        content_type=content_type_de_extension(extension),
    )
    return AdjuntoFacturacionRead(ref=clave, nombre_archivo=nombre_sano)


@router.get("")
def descargar_adjunto_facturacion(
    ref: str = Query(..., description="Clave de almacenamiento devuelta al subir"),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    if not ref.startswith(_PREFIJOS_DESCARGABLES):
        # 404 y no 403 a propósito: no se confirma la existencia de objetos de otros
        # prefijos del bucket.
        return Response(status_code=404)
    contenido = almacenamiento.obtener(ref)
    nombre = ref.rsplit("/", 1)[-1]
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    return Response(
        content=contenido,
        media_type=content_type_de_extension(extension),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
