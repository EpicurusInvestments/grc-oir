"""Errores de dominio y manejo central de errores.

Todas las respuestas de error siguen el sobre uniforme del `docs/API-CONTRACT.md`:

    { "error": { "codigo": "...", "mensaje": "...", "detalles": ... } }

Las excepciones de dominio se lanzan desde la capa de servicio; los handlers las
traducen a HTTP en la capa API, para que el router no contenga lógica de errores.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


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


class ConfiguracionError(DomainError):
    """El servidor está mal configurado (no es culpa del cliente) → 500.

    P.ej. `AUTH_PROVIDER` con un valor desconocido, `azure_ad` todavía no implementado, o
    `SECRET_KEY` con la llave de ejemplo fuera de desarrollo. Se distingue de un 400
    porque el operador debe arreglar el entorno, no el usuario su petición.
    """

    codigo = "configuracion_invalida"
    status_code = 500


class StateTransitionError(DomainError):
    """Transición de estado no permitida por la máquina de estados del servicio."""

    codigo = "transicion_invalida"
    status_code = 409


class ConflictError(DomainError):
    """Conflicto con el estado actual de los datos (p.ej. unicidad violada)."""

    codigo = "conflicto"
    status_code = 409


class DependenciasActivasError(DomainError):
    """Baja lógica bloqueada: la entidad tiene dependientes activos.

    Se resuelve confirmando desde el cliente y reintentando con `forzar=True`.
    `detalles` lleva el conteo de dependientes por tipo.
    """

    codigo = "dependencias_activas"
    status_code = 409


def _envelope(codigo: str, mensaje: str, detalles: Any = None) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensaje": mensaje, "detalles": detalles}}


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """Red de seguridad para excepciones que ningún handler de abajo cubre (p.ej. un
    error crudo de SQLAlchemy/DB).

    Bug reportado 2026-10-30: una excepción sin handler registrado la termina
    resolviendo Starlette con `ServerErrorMiddleware`, que en el stack de middlewares
    queda FUERA de `CORSMiddleware` — la respuesta sale sin headers CORS, el navegador
    la bloquea y el frontend la reporta como "Network Error" sin mensaje útil. Este
    middleware debe registrarse ANTES que `CORSMiddleware` en `main.py` (con
    `app.add_middleware`, el orden de registro invierte el orden de envoltura) para
    quedar DENTRO de CORS y que su respuesta sí lleve los headers.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            return await call_next(request)
        except Exception:
            logger.exception(
                "Error no manejado en %s %s", request.method, request.url.path
            )
            return JSONResponse(
                status_code=500,
                content=_envelope(
                    "error_interno",
                    "Ocurrió un error interno. Intenta de nuevo o contacta a soporte.",
                ),
            )


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
        # `exc.errors()` puede incluir en `ctx` el objeto ValueError original (lo agregan
        # los validadores propios que hacen `raise ValueError(...)`, p.ej. RFC o vigencia);
        # ese objeto NO es serializable a JSON y rompía el handler con un 500. Se pasa por
        # `jsonable_encoder` (igual que el handler por defecto de FastAPI) para obtener un
        # 422 legible; el mensaje humano queda en el campo `msg` de cada error.
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validacion", "Datos de entrada inválidos", jsonable_encoder(exc.errors())
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )
