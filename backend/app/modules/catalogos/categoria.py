"""Catálogo Categoria (F0-04).

Categorías de industria para segmentar órdenes y reportes (Automotriz, Alimentos, etc.).
Catálogo simple montado sobre la base de F0-00: modelo + schemas + servicio (unicidad de
`nombre_categoria`, case-insensitive — decisión E-1) + router.

Portabilidad SQL Server: unicidad CI vía `func.lower(...)` (ADR-017); booleanos `== True`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Unicode, UnicodeText, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase


def _normaliza_nombre(valor: str) -> str:
    """Colapsa espacios internos y recorta extremos (la unicidad es case-insensitive)."""
    return " ".join(valor.split())


# ── Modelo ──────────────────────────────────────────────────────────────────────
class Categoria(Base):
    __tablename__ = "categoria"

    categoria_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_categoria: Mapped[str] = mapped_column(Unicode(160), unique=True, index=True)
    descripcion_categoria: Mapped[str | None] = mapped_column(UnicodeText(), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class CategoriaCreate(BaseModel):
    nombre_categoria: str = Field(min_length=1, max_length=160)
    descripcion_categoria: str | None = Field(default=None)


class CategoriaUpdate(BaseModel):
    nombre_categoria: str | None = Field(default=None, min_length=1, max_length=160)
    descripcion_categoria: str | None = Field(default=None)


class CategoriaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    categoria_id: uuid.UUID
    nombre_categoria: str
    descripcion_categoria: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class CategoriaRepository(BaseRepository[Categoria]):
    def get_by_nombre(
        self, nombre: str, excluir_id: uuid.UUID | None = None
    ) -> Categoria | None:
        # Comparación case-insensitive portable (LOWER); coincide con el índice único bajo
        # collation CI de SQL Server (ADR-017). `nombre` ya llega normalizado en espacios.
        stmt = select(Categoria).where(func.lower(Categoria.nombre_categoria) == nombre.lower())
        if excluir_id is not None:
            stmt = stmt.where(Categoria.categoria_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class CategoriaService(BaseService[Categoria, CategoriaCreate, CategoriaUpdate, CategoriaRead]):
    read_schema = CategoriaRead
    entidad = "Categoria"

    def __init__(self, repo: CategoriaRepository) -> None:
        super().__init__(repo)
        self._categoria_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["nombre_categoria"] = _normaliza_nombre(payload["nombre_categoria"])
        self._verificar_nombre_unico(payload["nombre_categoria"], excluir_id=None)

    def _pre_update(
        self, obj: Categoria, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "nombre_categoria" in payload:
            payload["nombre_categoria"] = _normaliza_nombre(payload["nombre_categoria"])
            self._verificar_nombre_unico(
                payload["nombre_categoria"], excluir_id=obj.categoria_id
            )

    def _verificar_nombre_unico(self, nombre: str, excluir_id: uuid.UUID | None) -> None:
        if self._categoria_repo.get_by_nombre(nombre, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una categoría con el nombre «{nombre}».",
                detalles={"campo": "nombre_categoria", "valor": nombre},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_categoria_service(db: Session = Depends(get_db)) -> CategoriaService:
    repo = CategoriaRepository(
        db, Categoria, search_columns=[Categoria.nombre_categoria, Categoria.descripcion_categoria]
    )
    return CategoriaService(repo)


router = build_crud_router(
    prefix="/categorias",
    tags=["catalogos:categorias"],
    permiso_base="catalogos",
    read_schema=CategoriaRead,
    create_schema=CategoriaCreate,
    update_schema=CategoriaUpdate,
    get_service=get_categoria_service,
    id_type=uuid.UUID,
)
