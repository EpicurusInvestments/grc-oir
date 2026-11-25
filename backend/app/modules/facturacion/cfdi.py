"""Lectura de un CFDI (XML) de un proveedor — Agencia/Vendedor/Afiliado (petición del
usuario): precarga Subtotal/IVA en el formulario al cargar el XML, dejándolos editables
después. Endpoint SEPARADO de `adjuntos.py` (ese router es compartido entre módulos —
ordenes/facturación/cobranza — y no debe acoplarse a un formato de un solo módulo) y
también independiente del almacenamiento: no depende de que el XML ya se haya subido,
lee directo el archivo que el usuario acaba de elegir.

Nunca regresa un error HTTP por un XML que no se pueda leer como CFDI (ver
`parsear_cfdi`) — el usuario siempre puede seguir capturando Subtotal/IVA a mano. Sí
valida extensión/tamaño/firma de archivo como cualquier adjunto (`leer_adjunto`,
mismo criterio que `adjuntos.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento.documentos import leer_adjunto
from app.integrations.facturas_proveedor.parser import parsear_cfdi

router_cfdi = APIRouter(prefix="/cfdi", tags=["facturacion:cfdi"])

_SOLO_XML: frozenset[str] = frozenset({"xml"})


class LecturaCfdiRead(BaseModel):
    ok: bool
    motivo: str | None = None
    subtotal: str | None = None
    iva: str | None = None
    total: str | None = None
    rfc_emisor: str | None = None
    folio: str | None = None


@router_cfdi.post("/leer", response_model=LecturaCfdiRead)
def leer_cfdi_factura_proveedor(
    archivo: UploadFile = File(...),
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
) -> LecturaCfdiRead:
    """Lee Subtotal/IVA/Total/RFC emisor/folio del XML recién elegido (antes de o
    independientemente de subirlo a almacenamiento) — para precargar el formulario."""
    contenido, _, _ = leer_adjunto(
        archivo, max_bytes=settings.s3_max_pdf_bytes, extensiones_permitidas=_SOLO_XML
    )
    resultado = parsear_cfdi(contenido)
    return LecturaCfdiRead(
        ok=resultado.ok,
        motivo=resultado.motivo,
        subtotal=str(resultado.subtotal) if resultado.subtotal is not None else None,
        iva=str(resultado.iva) if resultado.iva is not None else None,
        total=str(resultado.total) if resultado.total is not None else None,
        rfc_emisor=resultado.rfc_emisor,
        folio=resultado.folio,
    )
