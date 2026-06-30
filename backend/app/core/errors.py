"""Errores de dominio y manejo central de errores.

Todas las respuestas de error siguen el sobre uniforme del `docs/API-CONTRACT.md`:

    { "error": { "codigo": "...", "mensaje": "...", "detalles": ... } }

Las excepciones de dominio se lanzan desde la capa de servicio; los handlers las
traducen a HTTP en la capa API, para que el router no contenga lógica de errores.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Error de negocio. Subclasear para casos concretos."""

    codigo = "error_dominio"
    status_code = 400

    def __init__(self, mensaje: str, detalles: Any = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles


class NotFoundError(DomainError):
    codigo = "no_encontrado"
    status_code = 404


class PermissionDeniedError(DomainError):
    codigo = "sin_permiso"
    status_code = 403


class AuthenticationError(DomainError):
    codigo = "no_autenticado"
    status_code = 401


class StateTransitionError(DomainError):
    """Transición de estado no permitida por la máquina de estados del servicio."""

    codigo = "transicion_invalida"
    status_code = 409


def _envelope(codigo: str, mensaje: str, detalles: Any = None) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensaje": mensaje, "detalles": detalles}}


def register_error_handlers(app: FastAPI) -> None:
    """Registra los handlers que producen el sobre uniforme."""

    @app.exception_handler(DomainError)
    def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.codigo, exc.mensaje, exc.detalles),
        )

    @app.exception_handler(RequestValidationError)
    def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope("validacion", "Datos de entrada inválidos", exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )
