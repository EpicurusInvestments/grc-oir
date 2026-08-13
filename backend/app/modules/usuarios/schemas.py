"""DTOs de la gestión de usuarios (F5-00). Solo Admin los consume.

Regla que atraviesa todo el archivo: `password_hash` **no aparece en ningún schema de
salida**, y la contraseña en claro solo existe como ENTRADA (alta y establecer contraseña),
nunca como campo editable del usuario. Cambiar la contraseña tiene su propio endpoint para
que sea un acto explícito y no un efecto colateral de editar el perfil.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.auth.identity import Area

# Política de contraseñas (decisión H-6): longitud mínima razonable, sin exigir mezcla de
# mayúsculas/símbolos (recomendación NIST: la longitud aporta más que la complejidad).
_MIN_CARACTERES = 10
_MAX_BYTES = 72


def _valida_password(valor: str) -> str:
    if len(valor) < _MIN_CARACTERES:
        raise ValueError(f"La contraseña debe tener al menos {_MIN_CARACTERES} caracteres.")
    if len(valor.encode("utf-8")) > _MAX_BYTES:
        # Se RECHAZA en vez de recortar: bcrypt ignora los bytes sobrantes, así que
        # aceptarla en silencio daría una falsa sensación de contraseña más larga.
        # Ojo: son BYTES, no caracteres — cada acento o 'ñ' cuenta doble en UTF-8.
        raise ValueError(
            f"La contraseña no puede exceder {_MAX_BYTES} bytes "
            "(los acentos y la 'ñ' cuentan como 2)."
        )
    return valor


PasswordNueva = Annotated[str, AfterValidator(_valida_password)]


class UsuarioCreate(BaseModel):
    nombre_usuario: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=160)
    area: Area
    roles_adicionales: str | None = Field(default=None, max_length=400)
    # Opcional: se puede dar de alta al usuario y establecerle la contraseña después.
    # Sin contraseña, el usuario existe pero NO puede iniciar sesión (fail-closed).
    password: PasswordNueva | None = None


class UsuarioUpdate(BaseModel):
    """Edición del perfil. La contraseña y el estado `activo` tienen endpoint propio."""

    nombre_usuario: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, min_length=3, max_length=160)
    area: Area | None = None
    roles_adicionales: str | None = Field(default=None, max_length=400)


class EstablecerPasswordIn(BaseModel):
    password: PasswordNueva


class UsuarioRead(BaseModel):
    """Salida. Sin `password_hash`: solo se informa SI tiene contraseña establecida."""

    model_config = ConfigDict(from_attributes=True)

    usuario_id: uuid.UUID
    nombre_usuario: str
    email: str
    area: str
    roles_adicionales: str | None = None
    activo: bool
    created_at: datetime
    #: Deriva de `password_hash`. Permite a la UI marcar "sin contraseña" (no puede entrar)
    #: sin exponer jamás el hash.
    tiene_password: bool
