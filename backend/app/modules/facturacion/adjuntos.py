"""Adjuntos de Facturación (XML/PDF del CFDI timbrado y archivos de proveedor).

Mismo patrón que `ordenes/adjuntos.py` (ADR-042): un solo endpoint genérico de
subida/descarga, lista blanca de extensiones y verificación de *magic bytes* — todo
reutilizando `integrations/almacenamiento/documentos.py`, que es la pieza genuinamente
genérica y neutral (no se importa nada del módulo `ordenes`).

Construido con `build_adjuntos_router` (`app/shared/adjuntos_router.py`, extraída en
F3 — regla de tres: con F1 y F2 duplicando el mismo router, extraerlo era prematuro; F3
es el tercer consumidor). `content_disposition="attachment"` (se descarga, no se
previsualiza) y NO quita el prefijo UUID de la clave al mostrar el nombre de descarga —
el par de detalles que distingue a este router del de `ordenes/adjuntos.py`.

El bucket es PRIVADO: el archivo se sirve SIEMPRE por este endpoint, nunca por URL
pública directa.
"""

from __future__ import annotations

from enum import StrEnum

from app.integrations.almacenamiento.documentos import EXTENSIONES_ADJUNTO_FACTURACION
from app.shared.adjuntos_router import build_adjuntos_router


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

# Permiso: `costos:editar`/`costos:leer`. Los adjuntos del CFDI son de Facturación, pero
# Admin y CxP también los suben en la práctica; se usa la clave más amplia del módulo y
# la asignación de la `ref` a la factura sí queda gateada por el permiso de su entidad.
router = build_adjuntos_router(
    tag="facturacion:adjuntos",
    tipos=TipoAdjuntoFacturacion,
    prefijos=_PREFIJOS,
    permiso_subir="costos:editar",
    permiso_descargar="costos:leer",
    content_disposition="attachment",
    quitar_prefijo_uuid_en_descarga=False,
    extensiones_permitidas=EXTENSIONES_ADJUNTO_FACTURACION,
)
