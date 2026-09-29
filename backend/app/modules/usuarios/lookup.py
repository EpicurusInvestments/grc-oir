"""Resolución de `Usuario` real a partir del usuario autenticado (`CurrentUser`).

`CurrentUser.username` es texto libre (hoy, el header de dev-auth `X-Dev-User`); los
campos `created_by`/`usuario_id` de F1 son FK real a `usuario.usuario_id` — nunca se
aceptan del cliente, siempre se resuelven aquí desde la sesión. `nombre_usuario` funciona
como el "username" de este stub de desarrollo (el único dato ya sembrado por F0-04,
`dev.admin`, es username-style, no un nombre de pila — ver Tanda 5 F1).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.modules.usuarios.models import Usuario


def resolver_usuario_id(db: Session, username: str) -> uuid.UUID:
    """`Usuario.usuario_id` cuyo `nombre_usuario == username`, o 404 claro.

    No se auto-crea: si `X-Dev-User` no coincide con ningún usuario sembrado, es un
    error de configuración del entorno de desarrollo, no un caso de negocio a tolerar.
    """
    usuario_id = db.scalar(select(Usuario.usuario_id).where(Usuario.nombre_usuario == username))
    if usuario_id is None:
        raise NotFoundError(
            f"No existe un Usuario con nombre_usuario='{username}' — revisa el header "
            "X-Dev-User o siembra ese usuario (ver backend/scripts/seed_dev.py).",
            detalles={"username": username},
        )
    return usuario_id


def resolver_usuario_email(db: Session, username: str) -> str:
    """`Usuario.email` cuyo `nombre_usuario == username`, o 404 claro.

    ADR-137 (corrección de revisión del equipo): el remitente de cualquier correo/`.eml`
    que arma el sistema sale del usuario con la sesión abierta, nunca de un valor fijo
    capturado en el código — mismo criterio que `resolver_usuario_id`.
    """
    email = db.scalar(select(Usuario.email).where(Usuario.nombre_usuario == username))
    if email is None:
        raise NotFoundError(
            f"No existe un Usuario con nombre_usuario='{username}' — revisa el header "
            "X-Dev-User o siembra ese usuario (ver backend/scripts/seed_dev.py).",
            detalles={"username": username},
        )
    return email
