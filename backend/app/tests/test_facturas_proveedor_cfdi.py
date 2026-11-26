"""Pruebas de la lectura de CFDI de facturas de proveedor (Agencia/Vendedor/Afiliado) —
petición del usuario: precargar Subtotal/IVA al cargar el XML, dejándolos editables.

`test_parsear_cfdi_*` prueban el parser puro (`app/integrations/facturas_proveedor`)
directamente, sin HTTP. `test_endpoint_*` prueban `POST /facturacion/cfdi/leer` de punta
a punta (mismo patrón que `test_facturacion_adjuntos.py`: app mínima + TestClient, sin
red ni almacenamiento real — este endpoint ni siquiera toca almacenamiento).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.integrations.facturas_proveedor.parser import parsear_cfdi
from app.modules.facturacion.cfdi import router_cfdi

_CFDI_EJEMPLO = (
    Path(__file__).resolve().parents[3] / "docs" / "referencias" / "cfdi_ejemplo_prueba.xml"
)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


# ══════════════════════════════════════════════════════════════════════════════════
# Parser puro
# ══════════════════════════════════════════════════════════════════════════════════
def test_parsear_cfdi_de_ejemplo_extrae_subtotal_iva_total_rfc_folio() -> None:
    contenido = _CFDI_EJEMPLO.read_bytes()
    r = parsear_cfdi(contenido)
    assert r.ok
    assert str(r.subtotal) == "957.00"
    assert str(r.iva) == "153.12"
    assert str(r.total) == "1110.12"
    assert r.rfc_emisor == "PBA260101XX1"
    assert r.folio == "0071"


def test_parsear_cfdi_xml_no_es_comprobante_regresa_ok_false_sin_excepcion() -> None:
    r = parsear_cfdi(b"<?xml version='1.0'?><otracosa/>")
    assert r.ok is False
    assert r.motivo


def test_parsear_cfdi_contenido_no_es_xml_regresa_ok_false_sin_excepcion() -> None:
    r = parsear_cfdi(b"esto no es xml en absoluto")
    assert r.ok is False
    assert r.motivo


def test_parsear_cfdi_sin_impuestos_trasladados_precarga_iva_en_cero() -> None:
    xml = (
        b'<?xml version="1.0"?>'
        b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        b'SubTotal="500.00" Total="500.00">'
        b'<cfdi:Emisor Rfc="EJE010101AB1"/>'
        b"</cfdi:Comprobante>"
    )
    r = parsear_cfdi(xml)
    assert r.ok
    assert str(r.iva) == "0"


# ══════════════════════════════════════════════════════════════════════════════════
# Endpoint HTTP: POST /facturacion/cfdi/leer
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api():  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router_cfdi, prefix="/api/v1/facturacion")
    yield TestClient(app)


def test_endpoint_lee_el_xml_de_ejemplo(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", _CFDI_EJEMPLO.read_bytes(), "application/xml")}
    r = api.post("/api/v1/facturacion/cfdi/leer", files=files, headers=_hdr("cxp"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["subtotal"] == "957.00"
    assert body["iva"] == "153.12"
    assert body["rfc_emisor"] == "PBA260101XX1"


def test_endpoint_xml_no_cfdi_regresa_200_ok_false_no_bloquea(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", b"<?xml version='1.0'?><otracosa/>", "application/xml")}
    r = api.post("/api/v1/facturacion/cfdi/leer", files=files, headers=_hdr("cxp"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["motivo"]


def test_endpoint_rechaza_extension_que_no_sea_xml(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")}
    r = api.post("/api/v1/facturacion/cfdi/leer", files=files, headers=_hdr("cxp"))
    assert r.status_code == 400, r.text


def test_endpoint_exige_permiso(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", _CFDI_EJEMPLO.read_bytes(), "application/xml")}
    r = api.post("/api/v1/facturacion/cfdi/leer", files=files, headers=_hdr("ventas"))
    assert r.status_code == 403, r.text
