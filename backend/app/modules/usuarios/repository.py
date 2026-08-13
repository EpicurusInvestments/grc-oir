"""Capa de datos de Usuario — ÚNICO punto que consulta la tabla `usuario`.

Hereda de `BaseRepository` (F0-00) para obtener list/get/create/update/baja lógica sin
reescribir SQL; la gestión de usuarios de F5-00 los aprovecha tal cual. Aquí solo se añade
la búsqueda por email, que es la credencial de login (decisión H-2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.usuarios.models import Usuario
from app.shared.base_repository import BaseRepository


class UsuarioRepository(BaseRepository[Usuario]):
    def __init__(self, db: Session) -> None:
        super().__init__(
            db,
            Usuario,
            search_columns=[Usuario.nombre_usuario, Usuario.email],
            default_order_by=[Usuario.nombre_usuario],
        )

    def get_by_email(self, email: str, excluir_id: uuid.UUID | None = None) -> Usuario | None:
        """Busca por email, case-insensitive.

        La collation de `GRC-OIR` ya es CI (ADR-017), pero `func.lower(...)` hace la
        comparación explícita y portable a SQLite, que es lo que usan las pruebas.
        `excluir_id` sirve para validar unicidad al EDITAR sin chocar con uno mismo.
        """
        stmt = select(Usuario).where(func.lower(Usuario.email) == email.strip().lower())
        if excluir_id is not None:
            stmt = stmt.where(Usuario.usuario_id != excluir_id)
        return self.db.scalars(stmt).first()
