"""Entidad de JUGUETE para probar la base genérica de catálogos sin tocar SQL Server.

No es parte del sistema: solo existe en las pruebas. Replica las convenciones de un
catálogo (PK tipo UUID-string, `activo`, `created_at`, `updated_at`) para ejercitar
`BaseRepository`, `BaseService` y `build_crud_router` sobre SQLite en memoria.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.schemas import CatalogoReadBase


class CatalogoDemo(Base):
    __tablename__ = "catalogo_demo"

    demo_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    nombre: Mapped[str] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(default=None, onupdate=datetime.now)


class DemoCreate(BaseModel):
    nombre: str


class DemoUpdate(BaseModel):
    nombre: str | None = None


class DemoRead(CatalogoReadBase):
    demo_id: str
    nombre: str


class DemoService(BaseService[CatalogoDemo, DemoCreate, DemoUpdate, DemoRead]):
    read_schema = DemoRead
    entidad = "CatalogoDemo"
