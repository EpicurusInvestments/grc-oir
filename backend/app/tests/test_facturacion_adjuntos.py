"""Pruebas del endpoint genérico de adjuntos de Facturación (`/facturacion/adjuntos`).

Mismo patrón que `test_ordenes_adjuntos.py`: sin credenciales ni red, el adaptador de
almacenamiento se sobreescribe por `AlmacenamientoLocal` (filesystem en `tmp_path`).

Este archivo no existía antes de F3 (F2 nunca tuvo pruebas propias de adjuntos — hueco
preexistente). Nace junto con `app/shared/adjuntos_router.py` (la factory compartida que
reemplazó las dos copias casi idénticas de F1/F2): convierte en cobertura permanente lo
que hasta ahora solo se había verificado manualmente al extraer la factory.

Deliberadamente cubre las DOS diferencias de comportamiento que distinguen a este router
del de `ordenes/adjuntos.py` (documentadas en `adjuntos_router.py`): `Content-Disposition`
es `attachment` (se descarga) y no `inline`, y el nombre de descarga CONSERVA el prefijo
UUID de la clave en vez de limpiarlo. Si alguien "corrige" sin querer esa segunda
diferencia al tocar la factory, `test_subir_y_descargar_conserva_el_prefijo_uuid` falla.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.documentos import EXTENSIONES_ADJUNTO_FACTURACION
from app.modules.facturacion.adjuntos import router as adjuntos_router

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
XML_BYTES = b'<?xml version="1.0"?><cfdi:Comprobante/>'


# ══════════════════════════════════════════════════════════════════════════════════
# Endpoint HTTP: /api/v1/facturacion/adjuntos
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api(tmp_path):  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(adjuntos_router, prefix="/api/v1/facturacion")
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path)
    yield TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_subir_y_descargar_pdf(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.pdf", PDF_BYTES, "application/pdf")}
    r = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_afiliado", files=files, headers=_hdr("cxp")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["nombre_archivo"] == "factura.pdf"
    assert body["ref"].startswith("facturacion/proveedor/afiliado/")

    r = api.get(f"/api/v1/facturacion/adjuntos?ref={body['ref']}", headers=_hdr("cxp"))
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"] == "application/pdf"
    # Content-Disposition es `attachment` (se descarga), NO `inline` como en órdenes.
    assert r.headers["content-disposition"].startswith("attachment;")


def test_subir_y_descargar_conserva_el_prefijo_uuid(api) -> None:  # type: ignore[no-untyped-def]
    """A diferencia de `ordenes/adjuntos.py`, este router NO limpia el prefijo UUID del
    nombre de descarga — inconsistencia real entre F1/F2 que se preserva a propósito
    (ver `adjuntos_router.py` y ADR de la excepción de anotaciones diferidas)."""
    files = {"archivo": ("cfdi.xml", XML_BYTES, "application/xml")}
    r = api.post(
        "/api/v1/facturacion/adjuntos?tipo=cfdi_xml", files=files, headers=_hdr("cxp")
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    clave = ref.rsplit("/", 1)[-1]  # "<uuid_hex_32>_cfdi.xml"
    assert clave != "cfdi.xml"  # confirma que la clave SÍ lleva el prefijo

    r = api.get(f"/api/v1/facturacion/adjuntos?ref={ref}", headers=_hdr("cxp"))
    # El nombre de descarga es la clave COMPLETA, uuid incluido — no el nombre original.
    assert r.headers["content-disposition"] == f'attachment; filename="{clave}"'


def test_extensiones_permitidas_incluyen_xml() -> None:
    """La única extensión que F2 admite de más respecto al set base de F1 (para el CFDI)."""
    assert "xml" in EXTENSIONES_ADJUNTO_FACTURACION
    assert "exe" not in EXTENSIONES_ADJUNTO_FACTURACION


def test_prefijo_distinto_por_tipo(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("respaldo.pdf", PDF_BYTES, "application/pdf")}
    r = api.post(
        "/api/v1/facturacion/adjuntos?tipo=respaldo_costo", files=files, headers=_hdr("cxp")
    )
    assert r.status_code == 201
    assert r.json()["ref"].startswith("facturacion/costos/respaldo/")


def test_subir_pdf_y_xml_de_factura_agencia(api) -> None:  # type: ignore[no-untyped-def]
    """ADR-079: la factura de la agencia se sube en PDF y XML por separado, mismo
    criterio que ADR-070 en factura de afiliado — prefijos propios, uno por tipo."""
    r_pdf = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_agencia_pdf",
        files={"archivo": ("factura.pdf", PDF_BYTES, "application/pdf")},
        headers=_hdr("cxp"),
    )
    assert r_pdf.status_code == 201, r_pdf.text
    assert r_pdf.json()["ref"].startswith("facturacion/proveedor/agencia/pdf/")

    r_xml = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_agencia_xml",
        files={"archivo": ("factura.xml", XML_BYTES, "application/xml")},
        headers=_hdr("cxp"),
    )
    assert r_xml.status_code == 201, r_xml.text
    assert r_xml.json()["ref"].startswith("facturacion/proveedor/agencia/xml/")

    r = api.get(f"/api/v1/facturacion/adjuntos?ref={r_pdf.json()['ref']}", headers=_hdr("cxp"))
    assert r.status_code == 200
    assert r.content == PDF_BYTES


def test_subir_pdf_y_xml_de_factura_vendedor(api) -> None:  # type: ignore[no-untyped-def]
    """Paridad con `FacturaAgencia`: la factura del vendedor también se sube en PDF y
    XML por separado, con su propio prefijo de almacenamiento."""
    r_pdf = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_vendedor_pdf",
        files={"archivo": ("factura.pdf", PDF_BYTES, "application/pdf")},
        headers=_hdr("cxp"),
    )
    assert r_pdf.status_code == 201, r_pdf.text
    assert r_pdf.json()["ref"].startswith("facturacion/proveedor/vendedor/pdf/")

    r_xml = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_vendedor_xml",
        files={"archivo": ("factura.xml", XML_BYTES, "application/xml")},
        headers=_hdr("cxp"),
    )
    assert r_xml.status_code == 201, r_xml.text
    assert r_xml.json()["ref"].startswith("facturacion/proveedor/vendedor/xml/")


def test_rbac_ventas_no_puede_subir(api) -> None:  # type: ignore[no-untyped-def]
    """`costos:editar` exige CxP (o Admin); Ventas solo lee en este módulo."""
    files = {"archivo": ("factura.pdf", PDF_BYTES, "application/pdf")}
    r = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_afiliado", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 403


def test_subir_exe_rechazado(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("virus.exe", b"MZ" + b"\x00" * 20, "application/octet-stream")}
    r = api.post(
        "/api/v1/facturacion/adjuntos?tipo=factura_afiliado", files=files, headers=_hdr("cxp")
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_permitido"


def test_descargar_fuera_de_prefijos_permitidos_404(api) -> None:  # type: ignore[no-untyped-def]
    r = api.get(
        "/api/v1/facturacion/adjuntos?ref=ordenes/odc/secreto.pdf", headers=_hdr("cxp")
    )
    assert r.status_code == 404
