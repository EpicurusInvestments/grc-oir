"""Prueba del preflight CORS (ADR-013).

El frontend (SPA en otro origen) hace un preflight OPTIONS antes de POST/PUT. Verificamos
que un origen PERMITIDO reciba las cabeceras CORS (incluidos los headers de auth de
desarrollo) y que un origen NO permitido quede sin `access-control-allow-origin`.

Se ejercita sobre la app real (`app.main:app`): el CORS es middleware global y no depende
de las fixtures de catálogos (que montan una app aparte sobre SQLite).
"""

from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import settings
from app.main import app

client = TestClient(app)

_ORIGEN_PERMITIDO = settings.cors_origins_list[0]  # http://localhost:5173 en desarrollo


def _preflight(origin: str) -> Response:
    return cast(
        Response,
        client.options(
            "/api/v1/catalogos/plazas",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-dev-user, x-dev-area, content-type",
            },
        ),
    )


def test_cors_preflight() -> None:
    # Origen permitido: recibe las cabeceras CORS del preflight.
    permitido = _preflight(_ORIGEN_PERMITIDO)
    assert permitido.status_code == 200
    assert permitido.headers["access-control-allow-origin"] == _ORIGEN_PERMITIDO
    assert "POST" in permitido.headers["access-control-allow-methods"]
    # Los headers de auth de desarrollo deben quedar permitidos.
    headers_permitidos = permitido.headers["access-control-allow-headers"].lower()
    assert "x-dev-user" in headers_permitidos
    assert "x-dev-area" in headers_permitidos

    # Origen NO permitido: sin `access-control-allow-origin` el navegador bloquea la
    # petición real.
    bloqueado = _preflight("http://evil.example.com")
    assert "access-control-allow-origin" not in bloqueado.headers
