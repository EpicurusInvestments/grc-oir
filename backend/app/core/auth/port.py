"""Puerto de autenticación (patrón anti-corrupción, igual que el de almacenamiento S3).

El sistema depende SOLO de esta interfaz; el adaptador concreto lo elige
`get_auth_provider()` según `AUTH_PROVIDER` (ver `__init__.py`, espejo de
`get_almacenamiento()` de ADR-027). Activar Azure AD será implementar un adaptador y
cambiar una variable de entorno: los routers y servicios de negocio no se enteran.

Dos operaciones, en términos del dominio:

- `autenticar`: valida credenciales y emite una sesión (solo proveedores con login local).
- `resolver_usuario`: dice QUIÉN hace el request en curso (token, header, cookie… es
  asunto del adaptador). Es lo que consume el RBAC de `core/security.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth.identity import CurrentUser


@dataclass(frozen=True)
class SesionEmitida:
    """Resultado de un login correcto."""

    token: str
    expira_en: datetime
    usuario: CurrentUser


class AuthProviderPort(Protocol):
    """Operaciones de autenticación en términos del dominio."""

    #: Nombre del proveedor tal como se escribe en `AUTH_PROVIDER`.
    nombre: str
    #: True si acepta usuario/contraseña. El frontend lo usa para mostrar (o no) el
    #: formulario de login, y el servicio para rechazar `/auth/login` con un error claro.
    soporta_login_local: bool

    def autenticar(
        self,
        *,
        identificador: str,
        secreto: str,
        db: Session,
        ip: str | None = None,
    ) -> SesionEmitida:
        """Valida credenciales y devuelve la sesión emitida.

        Ante CUALQUIER fallo (usuario inexistente, contraseña incorrecta, usuario
        inactivo, usuario sin contraseña) debe lanzarse el MISMO error genérico: no se
        revela si el usuario existe.
        """
        ...

    def resolver_usuario(self, request: Request, db: Session) -> CurrentUser:
        """Identidad del request en curso. 401 si no hay sesión válida."""
        ...
