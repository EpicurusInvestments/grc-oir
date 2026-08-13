"""Seguridad: identidad del usuario y RBAC por área.

Dos piezas:

1. `get_current_user`: resuelve el usuario y su ÁREA delegando en el **proveedor de
   autenticación** configurado (`AUTH_PROVIDER` → `core/auth/get_auth_provider()`,
   ADR-041). Desde F5-00 el caso normal es un **token JWT** emitido por `/auth/login`; el
   modo `dev_headers` conserva los headers `X-Dev-User`/`X-Dev-Area` de ADR-008 para el
   trabajo local, y falla cerrado fuera de `APP_ENV=development`.

2. `requiere_permiso("<modulo>:<accion>")`: dependencia de FastAPI que valida el permiso
   contra la MATRIZ RBAC (datos, no ifs repartidos). El área se toma del usuario, jamás
   del cliente.

`Area` y `CurrentUser` viven ahora en `core/auth/identity.py` (evita el ciclo
`security ↔ auth`) y se **re-exportan** aquí: todo lo que ya importaba
`from app.core.security import Area, CurrentUser` sigue igual, sin cambios.
"""

from __future__ import annotations

from enum import IntEnum

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import get_auth_provider
from app.core.auth.identity import Area, CurrentUser
from app.core.db import get_db
from app.core.errors import PermissionDeniedError

# Esquema de seguridad SOLO para documentación: hace que OpenAPI publique el token de
# sesión y que `/docs` muestre el botón "Authorize" (sin esto, Swagger no ofrece dónde
# pegar el token y los endpoints protegidos se ven como "No parameters").
#
# `auto_error=False` es deliberado: quien decide si falta la sesión —y con qué mensaje— es
# el ADAPTADOR, no este esquema. Con `auto_error=True`, FastAPI respondería 403 con su
# propio formato antes de llegar al proveedor, rompería el sobre de error uniforme y
# dejaría inservible el modo `dev_headers` (que no usa Bearer).
_esquema_bearer = HTTPBearer(
    auto_error=False,
    description=(
        "Token de sesión emitido por POST /api/v1/auth/login. Pegue solo el valor de "
        "`access_token` (sin el prefijo 'Bearer')."
    ),
)


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
#
# NOTA (desviación explícita de la matriz de la propuesta, decisión del equipo): Admin
# es superusuario — WRITE en TODOS los módulos, presentes y futuros — resuelto de forma
# centralizada en `_nivel()`, no listado módulo por módulo aquí. La propuesta original
# (§9) le daba a Admin solo lectura sobre Órdenes; se decidió ampliarlo a acceso total
# para no bloquear pruebas/administración desde esa área.
_LECTURA_CATALOGOS = {
    Area.VENTAS: Acceso.READ,
    Area.FACTURACION: Acceso.READ,
    Area.TESORERIA: Acceso.READ,
    Area.CXC: Acceso.READ,
    Area.CXP: Acceso.READ,
    Area.DIRECCION: Acceso.READ,
}

# F1: matriz de la propuesta Pointwise (§9 "Roles y matriz de permisos"), columna
# "Órdenes" — Ventas captura (C); Facturación/Tesorería/CxC/CxP/Dirección solo leen (L);
# Nóminas sin acceso (—). Admin no se lista aquí: siempre WRITE vía `_nivel()`.
_LECTURA_ORDENES = {
    Area.FACTURACION: Acceso.READ,
    Area.TESORERIA: Acceso.READ,
    Area.CXC: Acceso.READ,
    Area.CXP: Acceso.READ,
    Area.DIRECCION: Acceso.READ,
}

RBAC: dict[str, dict[Area, Acceso]] = {
    "catalogos": _LECTURA_CATALOGOS,
    "ordenes": {Area.VENTAS: Acceso.WRITE, **_LECTURA_ORDENES},
    # F5-00: la gestión de usuarios es exclusiva de Admin, INCLUSO en lectura. El padrón
    # de usuarios (quién existe, con qué área) no es un catálogo consultable por el resto
    # de las áreas. El diccionario va VACÍO a propósito: no hay ningún área con acceso
    # además de Admin, que lo obtiene de `_nivel()` igual que en los demás módulos.
    "usuarios": {},
}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
) -> CurrentUser:
    """Resuelve el usuario actual delegando en el proveedor de autenticación.

    Este es el ÚNICO punto del sistema que pregunta "¿quién es?"; cambiar de login local
    a Azure AD no toca esta función, solo la variable `AUTH_PROVIDER`.

    `credenciales` NO se usa aquí a propósito: cada adaptador sabe de dónde sacar la
    identidad (header Bearer en `local`, X-Dev-* en `dev_headers`, y una cookie o un
    callback OIDC el día que exista `azure_ad`). Se declara para que el esquema aparezca
    en OpenAPI y `/docs` ofrezca el botón "Authorize" — el `request` completo es lo que
    viaja al proveedor.
    """
    return get_auth_provider().resolver_usuario(request, db)


def _nivel(modulo: str, area: Area) -> Acceso:
    if area is Area.ADMIN:
        return Acceso.WRITE
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


__all__ = [
    "RBAC",
    "Acceso",
    "Area",
    "CurrentUser",
    "get_current_user",
    "requiere_permiso",
]
