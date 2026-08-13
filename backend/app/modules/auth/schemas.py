"""DTOs del módulo de autenticación (F5-00).

Nota deliberada: NO se usa `EmailStr` de Pydantic para no arrastrar la dependencia
`email-validator` por un campo que solo sirve para buscar en la tabla. El email se
normaliza (trim + minúsculas) y la unicidad la garantiza el índice de `usuario.email`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    """Credenciales de login local."""

    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normaliza_email(cls, valor: str) -> str:
        return valor.strip().lower()


class UsuarioSesion(BaseModel):
    """Identidad del usuario en sesión. NUNCA incluye `password_hash`."""

    usuario_id: uuid.UUID | None = None
    nombre_usuario: str
    email: str | None = None
    area: str


class SesionOut(BaseModel):
    """Sesión emitida por `/auth/login`."""

    access_token: str
    token_type: str = "bearer"
    expira_en: datetime
    usuario: UsuarioSesion
