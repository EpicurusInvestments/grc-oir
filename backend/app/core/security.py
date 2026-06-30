"""Seguridad: identidad del usuario y RBAC por área.

Dos piezas:

1. `get_current_user`: resuelve el usuario y su ÁREA. Mientras el SSO corporativo está
   `[[POR LLENAR]]`, en `APP_ENV=development` se usa un stub que lee los headers de
   desarrollo `X-Dev-User` / `X-Dev-Area` (con un admin por defecto configurable en
   `.env`). En CUALQUIER otro entorno sin SSO, la autenticación FALLA CERRADA: rechaza,
   nunca asume admin.  # TODO(SSO): reemplazar este único punto por validación del token.

2. `requiere_permiso("<modulo>:<accion>")`: dependencia de FastAPI que valida el permiso
   contra la MATRIZ RBAC (datos, no ifs repartidos). El área se toma del usuario, jamás
   del cliente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from fastapi import Depends, Request

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError


class Area(StrEnum):
    VENTAS = "ventas"
    FACTURACION = "facturacion"
    TESORERIA = "tesoreria"
    CXC = "cxc"
    CXP = "cxp"
    DIRECCION = "direccion"
    NOMINAS = "nominas"
    ADMIN = "admin"


class Acceso(IntEnum):
    """Nivel de acceso de un área a un módulo. WRITE implica READ."""

    NONE = 0
    READ = 1  # "L" en la matriz de la propuesta
    WRITE = 2  # "C" (captura) en la matriz de la propuesta


# Acciones que un endpoint puede exigir y el nivel mínimo que requieren.
_ACCION_NIVEL: dict[str, Acceso] = {
    "leer": Acceso.READ,
    "crear": Acceso.WRITE,
    "editar": Acceso.WRITE,
}

# ── Matriz RBAC (módulo × área) ───────────────────────────────────────────────
# Fuente: matriz de la propuesta. F0-00: en catálogos solo Admin escribe; las demás
# áreas operativas solo leen (decisión confirmada, revisable cuando Ventas entre a
# afiliados/estaciones en F0-01).
_LECTURA_CATALOGOS = {
    Area.VENTAS: Acceso.READ,
    Area.FACTURACION: Acceso.READ,
    Area.TESORERIA: Acceso.READ,
    Area.CXC: Acceso.READ,
    Area.CXP: Acceso.READ,
    Area.DIRECCION: Acceso.READ,
}

RBAC: dict[str, dict[Area, Acceso]] = {
    "catalogos": {Area.ADMIN: Acceso.WRITE, **_LECTURA_CATALOGOS},
}


@dataclass(frozen=True)
class CurrentUser:
    username: str
    area: Area
    ip: str | None = None


def get_current_user(request: Request) -> CurrentUser:
    """Resuelve el usuario actual.

    development → stub por headers (default admin de `.env`).
    otro entorno sin SSO → falla cerrada (401).  # TODO(SSO)
    """
    ip = request.client.host if request.client else None

    if not settings.is_development:
        # TODO(SSO): validar el token del proveedor corporativo y mapear a área.
        raise AuthenticationError(
            "Autenticación no configurada: el SSO corporativo está pendiente y el "
            "acceso de desarrollo solo se permite con APP_ENV=development."
        )

    username = request.headers.get("X-Dev-User", settings.dev_user)
    area_raw = request.headers.get("X-Dev-Area", settings.dev_area)
    try:
        area = Area(area_raw.strip().lower())
    except ValueError as exc:
        raise AuthenticationError(
            f"Área de desarrollo inválida: '{area_raw}'.",
            detalles={"areas_validas": [a.value for a in Area]},
        ) from exc
    return CurrentUser(username=username, area=area, ip=ip)


def _nivel(modulo: str, area: Area) -> Acceso:
    return RBAC.get(modulo, {}).get(area, Acceso.NONE)


def requiere_permiso(permiso: str):  # type: ignore[no-untyped-def]
    """Factory de dependencia. `permiso` tiene forma '<modulo>:<accion>'.

    Uso: `dependencies=[Depends(requiere_permiso("catalogos:editar"))]`.
    """
    try:
        modulo, accion = permiso.split(":", 1)
    except ValueError as exc:  # pragma: no cover — error de programación
        raise ValueError(f"Permiso mal formado: '{permiso}' (esperado 'modulo:accion')") from exc

    requerido = _ACCION_NIVEL.get(accion)
    if requerido is None:  # pragma: no cover — error de programación
        raise ValueError(f"Acción desconocida en permiso: '{accion}'")

    def dependencia(usuario: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if _nivel(modulo, usuario.area) < requerido:
            raise PermissionDeniedError(
                f"El área '{usuario.area.value}' no tiene permiso '{permiso}'.",
            )
        return usuario

    return dependencia
