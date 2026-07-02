"""Catálogo Plaza (F0-01).

Plaza geográfica donde operan los afiliados. Catálogo simple (solo baja lógica) montado
sobre la base de F0-00: modelo + schemas + servicio (con la regla de baja con
dependientes) + router vía `build_crud_router`.

Regla de baja (E-2): no se puede desactivar una plaza que tenga AFILIADOS activos o
ESTACIONES activas, salvo confirmación (`forzar=True`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import DependenciasActivasError
from app.core.security import CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase


class Plaza(Base):
    __tablename__ = "plaza"

    plaza_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_plaza: Mapped[str] = mapped_column(Unicode(120), index=True)
    estado: Mapped[str | None] = mapped_column(Unicode(120), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # updated_at en toda entidad (CLAUDE.md §6); ver nota de unificación de criterio.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class PlazaCreate(BaseModel):
    nombre_plaza: str = Field(min_length=1, max_length=120)
    estado: str | None = Field(default=None, max_length=120)


class PlazaUpdate(BaseModel):
    nombre_plaza: str | None = Field(default=None, min_length=1, max_length=120)
    estado: str | None = Field(default=None, max_length=120)


class PlazaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    plaza_id: uuid.UUID
    nombre_plaza: str
    estado: str | None = None


# ── Servicio ──────────────────────────────────────────────────────────────────
class PlazaService(BaseService[Plaza, PlazaCreate, PlazaUpdate, PlazaRead]):
    read_schema = PlazaRead
    entidad = "Plaza"

    def __init__(
        self,
        repo: BaseRepository[Plaza],
        *,
        afiliado_repo: Any,
        estacion_repo: Any,
    ) -> None:
        super().__init__(repo)
        self._afiliado_repo = afiliado_repo
        self._estacion_repo = estacion_repo

    def _pre_desactivar(self, obj: Plaza, forzar: bool, usuario: CurrentUser) -> None:
        if forzar:
            return
        afiliados = self._afiliado_repo.contar_activos_por_plaza(obj.plaza_id)
        estaciones = self._estacion_repo.contar_activas_por_plaza(obj.plaza_id)
        if afiliados or estaciones:
            raise DependenciasActivasError(
                "No se puede desactivar la plaza porque tiene dependientes activos. "
                "Confirma para desactivarla de todos modos.",
                detalles={"afiliados_activos": afiliados, "estaciones_activas": estaciones},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_plaza_service(db: Session = Depends(get_db)) -> PlazaService:
    # Import perezoso para evitar ciclos entre los módulos de catálogos operativos.
    from app.modules.catalogos.afiliado import Afiliado, AfiliadoRepository
    from app.modules.catalogos.estacion import Estacion, EstacionRepository

    return PlazaService(
        BaseRepository(db, Plaza, search_columns=[Plaza.nombre_plaza, Plaza.estado]),
        afiliado_repo=AfiliadoRepository(db, Afiliado),
        estacion_repo=EstacionRepository(db, Estacion),
    )


router = build_crud_router(
    prefix="/plazas",
    tags=["catalogos:plazas"],
    permiso_base="catalogos",
    read_schema=PlazaRead,
    create_schema=PlazaCreate,
    update_schema=PlazaUpdate,
    get_service=get_plaza_service,
    id_type=uuid.UUID,
)
