"""Pruebas de los adjuntos de Órdenes (antes "simulados"): validación multi-extensión
(`leer_adjunto`) y el endpoint genérico de subida/descarga (`/ordenes/adjuntos`).

Se prueba SIN credenciales ni red: el adaptador de almacenamiento se sobreescribe por
`AlmacenamientoLocal` (filesystem en `tmp_path`), igual que las pruebas de adjuntos de
Contrato (`test_s3_adjuntos.py`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.documentos import (
    ArchivoDemasiadoGrandeError,
    ArchivoNoPermitidoError,
    EXTENSIONES_ADJUNTO_ORDENES,
    leer_adjunto,
)
from app.modules.ordenes.adjuntos import router as adjuntos_router

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 20
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


class _ArchivoFalso:
    """Emula lo mínimo de `UploadFile` que usa `leer_adjunto` (solo `filename`/`file`)."""

    def __init__(self, filename: str, contenido: bytes) -> None:
        self.filename = filename
        import io

        self.file = io.BytesIO(contenido)


# ══════════════════════════════════════════════════════════════════════════════════
# leer_adjunto: lista blanca + magic bytes
# ══════════════════════════════════════════════════════════════════════════════════
def test_leer_adjunto_acepta_pdf_jpg_png() -> None:
    for nombre, contenido in [("a.pdf", PDF_BYTES), ("b.jpg", JPG_BYTES), ("c.png", PNG_BYTES)]:
        contenido_leido, nombre_sano, extension = leer_adjunto(
            _ArchivoFalso(nombre, contenido), max_bytes=1024
        )
        assert contenido_leido == contenido
        assert nombre_sano.endswith(f".{extension}")


def test_leer_adjunto_rechaza_extension_no_permitida() -> None:
    with pytest.raises(ArchivoNoPermitidoError):
        leer_adjunto(_ArchivoFalso("virus.exe", b"MZ" + b"\x00" * 20), max_bytes=1024)


def test_leer_adjunto_rechaza_extension_disfrazada() -> None:
    # Extensión .pdf pero contenido que en realidad es un ejecutable (magic bytes MZ).
    with pytest.raises(ArchivoNoPermitidoError):
        leer_adjunto(_ArchivoFalso("no_es_pdf.pdf", b"MZ" + b"\x00" * 20), max_bytes=1024)


def test_leer_adjunto_rechaza_tamano_excedido() -> None:
    with pytest.raises(ArchivoDemasiadoGrandeError):
        leer_adjunto(_ArchivoFalso("a.pdf", PDF_BYTES), max_bytes=4)


def test_leer_adjunto_rechaza_vacio() -> None:
    with pytest.raises(ArchivoNoPermitidoError):
        leer_adjunto(_ArchivoFalso("a.pdf", b""), max_bytes=1024)


def test_extensiones_permitidas_no_incluyen_ejecutables() -> None:
    assert "exe" not in EXTENSIONES_ADJUNTO_ORDENES
    assert "bat" not in EXTENSIONES_ADJUNTO_ORDENES
    assert "sh" not in EXTENSIONES_ADJUNTO_ORDENES
    assert {"pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"} == set(
        EXTENSIONES_ADJUNTO_ORDENES
    )


# ══════════════════════════════════════════════════════════════════════════════════
# Endpoint HTTP: /api/v1/ordenes/adjuntos
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api(tmp_path):  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(adjuntos_router, prefix="/api/v1/ordenes")
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path)
    yield TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_subir_y_descargar_pdf(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("odc.pdf", PDF_BYTES, "application/pdf")}
    r = api.post("/api/v1/ordenes/adjuntos?tipo=odc", files=files, headers=_hdr("ventas"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["nombre_archivo"] == "odc.pdf"
    assert body["ref"].startswith("ordenes/odc/")

    r = api.get(f"/api/v1/ordenes/adjuntos?ref={body['ref']}", headers=_hdr("ventas"))
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"] == "application/pdf"
    # El nombre de descarga es el ORIGINAL (sin el prefijo UUID de la clave interna).
    assert r.headers["content-disposition"] == 'inline; filename="odc.pdf"'


def test_prefijo_distinto_por_tipo(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("reporte.xlsx", b"PK\x03\x04" + b"\x00" * 20, "application/octet-stream")}
    r = api.post(
        "/api/v1/ordenes/adjuntos?tipo=reporte_reales", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 201
    assert r.json()["ref"].startswith("orden_estacion/reportes/reales/")


def test_rbac_nominas_no_puede_subir(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("odc.pdf", PDF_BYTES, "application/pdf")}
    r = api.post("/api/v1/ordenes/adjuntos?tipo=odc", files=files, headers=_hdr("nominas"))
    assert r.status_code == 403


def test_subir_exe_rechazado(api) -> None:  # type: ignore[no-untyped-def]
    files = {"archivo": ("virus.exe", b"MZ" + b"\x00" * 20, "application/octet-stream")}
    r = api.post("/api/v1/ordenes/adjuntos?tipo=odc", files=files, headers=_hdr("ventas"))
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_permitido"


def test_descargar_fuera_de_prefijos_permitidos_404(api) -> None:  # type: ignore[no-untyped-def]
    r = api.get(
        "/api/v1/ordenes/adjuntos?ref=contratos/otro/secreto.pdf", headers=_hdr("ventas")
    )
    assert r.status_code == 404
