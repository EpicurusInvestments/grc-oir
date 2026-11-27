"""Pruebas de la lectura del Timbre Fiscal Digital (ADR-296, petición del usuario):
precargar «Registrar respuesta del timbrado» (Factura, Nota de Crédito) al cargar el
XML ya timbrado que regresa el PAC.

`test_parsear_timbre_fiscal_*` prueban el parser puro
(`app/integrations/timbrado/lector_respuesta.py`) directamente, sin HTTP.
`test_endpoint_*` prueban `POST /facturacion/clientes/cfdi-timbrado/leer` de punta a
punta (mismo patrón que `test_facturas_proveedor_cfdi.py`: app mínima + TestClient, sin
red ni almacenamiento real ni base de datos — este endpoint no toca ninguna de las dos).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.integrations.timbrado.lector_respuesta import parsear_timbre_fiscal
from app.modules.facturacion.factura_cliente import router_clientes

# Mismo archivo de ejemplo que ya usa `test_facturas_proveedor_cfdi.py` — ya trae un
# Complemento/TimbreFiscalDigital de prueba (sin valor fiscal real).
_CFDI_EJEMPLO = (
    Path(__file__).resolve().parents[3] / "docs" / "referencias" / "cfdi_ejemplo_prueba.xml"
)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


# ══════════════════════════════════════════════════════════════════════════════════
# Parser puro
# ══════════════════════════════════════════════════════════════════════════════════
def test_parsear_timbre_fiscal_del_ejemplo_extrae_uuid_fecha_y_certificado() -> None:
    contenido = _CFDI_EJEMPLO.read_bytes()
    r = parsear_timbre_fiscal(contenido)
    assert r.ok, r.motivo
    assert r.folio_fiscal_sat == "00000000-0000-0000-0000-000000000000"
    assert r.fecha_timbrado == date(2026, 11, 24)
    assert r.no_certificado_sat == "00000000000000000000"


def test_parsear_timbre_fiscal_xml_no_es_comprobante_regresa_ok_false_sin_excepcion() -> None:
    r = parsear_timbre_fiscal(b"<?xml version='1.0'?><otracosa/>")
    assert r.ok is False
    assert r.motivo


def test_parsear_timbre_fiscal_contenido_no_es_xml_regresa_ok_false_sin_excepcion() -> None:
    r = parsear_timbre_fiscal(b"esto no es xml en absoluto")
    assert r.ok is False
    assert r.motivo


def test_parsear_timbre_fiscal_sin_complemento_regresa_ok_false_sin_excepcion() -> None:
    """Un CFDI preparado pero TODAVÍA no timbrado (sin Complemento) — el usuario
    sigue pudiendo capturar los 3 campos a mano, no se le avienta un error crudo."""
    xml = (
        b'<?xml version="1.0"?>'
        b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        b'SubTotal="500.00" Total="500.00"/>'
    )
    r = parsear_timbre_fiscal(xml)
    assert r.ok is False
    assert r.motivo


def test_parsear_timbre_fiscal_fecha_con_formato_inesperado_regresa_ok_false() -> None:
    xml = (
        b'<?xml version="1.0"?>'
        b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4">'
        b"<cfdi:Complemento>"
        b'<tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        b'UUID="00000000-0000-0000-0000-000000000000" FechaTimbrado="no-es-una-fecha"/>'
        b"</cfdi:Complemento>"
        b"</cfdi:Comprobante>"
    )
    r = parsear_timbre_fiscal(xml)
    assert r.ok is False
    assert r.motivo


# ══════════════════════════════════════════════════════════════════════════════════
# Endpoint HTTP: POST /facturacion/clientes/cfdi-timbrado/leer
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api():  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router_clientes, prefix="/api/v1/facturacion")
    yield TestClient(app)


def test_endpoint_lee_el_xml_de_ejemplo(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", _CFDI_EJEMPLO.read_bytes(), "application/xml")}
    r = api.post(
        "/api/v1/facturacion/clientes/cfdi-timbrado/leer", files=files, headers=_hdr("facturacion")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["folio_fiscal_sat"] == "00000000-0000-0000-0000-000000000000"
    assert body["fecha_timbrado"] == "2026-11-24"
    assert body["serie_timbrado"] == "00000000000000000000"


def test_endpoint_xml_no_cfdi_regresa_200_ok_false_no_bloquea(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", b"<?xml version='1.0'?><otracosa/>", "application/xml")}
    r = api.post(
        "/api/v1/facturacion/clientes/cfdi-timbrado/leer", files=files, headers=_hdr("facturacion")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["motivo"]


def test_endpoint_rechaza_extension_que_no_sea_xml(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")}
    r = api.post(
        "/api/v1/facturacion/clientes/cfdi-timbrado/leer", files=files, headers=_hdr("facturacion")
    )
    assert r.status_code == 400, r.text


def test_endpoint_exige_permiso(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("factura.xml", _CFDI_EJEMPLO.read_bytes(), "application/xml")}
    r = api.post(
        "/api/v1/facturacion/clientes/cfdi-timbrado/leer", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 403, r.text
