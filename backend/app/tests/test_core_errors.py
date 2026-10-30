"""Pruebas de `app/core/errors.py`: sobre uniforme + red de seguridad de CORS.

Bug reportado 2026-10-30: una excepción sin handler registrado (p.ej. un error crudo de
BD) la resolvía Starlette con `ServerErrorMiddleware`, que queda FUERA de
`CORSMiddleware` en el stack — la respuesta salía sin headers CORS, el navegador la
bloqueaba y el frontend la mostraba como "Network Error" sin mensaje útil.
`CatchAllErrorMiddleware` debe registrarse ANTES que `CORSMiddleware` (`app.main`) para
quedar DENTRO de CORS; estas pruebas arman ese mismo orden en una app mínima y verifican
que la respuesta trae tanto el sobre uniforme como el header CORS.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.errors import CatchAllErrorMiddleware, DomainError, register_error_handlers


def _build_app() -> FastAPI:
    app = FastAPI()

    # Mismo orden que `app/main.py`: CatchAll ANTES que CORS.
    app.add_middleware(CatchAllErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/explota")
    def _explota() -> None:
        raise RuntimeError("boom")

    @app.get("/dominio")
    def _dominio() -> None:
        raise DomainError("mensaje de dominio", detalles={"x": 1})

    return app


def test_excepcion_no_manejada_regresa_500_con_sobre_uniforme_y_cors() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/explota", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 500
    assert resp.json()["error"]["codigo"] == "error_interno"
    # Esta aserción es la que hubiera fallado ANTES del fix: sin `CatchAllErrorMiddleware`
    # dentro de CORS, Starlette resuelve la excepción con `ServerErrorMiddleware` y la
    # respuesta sale sin este header — el navegador la bloquea (-> "Network Error").
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_domain_error_sigue_regresando_su_status_y_mensaje_propios() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/dominio", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 400
    assert resp.json()["error"]["mensaje"] == "mensaje de dominio"
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
