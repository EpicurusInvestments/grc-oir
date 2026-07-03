"""Catálogo Estación (F0-01).

Emisora (FM/AM/TV) operada por un afiliado. Se administra ANIDADA dentro de la pantalla
de Afiliados (no es una entrada de sidebar propia), pero expone su CRUD completo.

Reglas propias en la capa de servicio:

- **Herencia de plaza (ADR-005):** `plaza_id` se asigna SIEMPRE = `Afiliado.plaza_id`; el
  cliente no la envía (los schemas Create/Update no la exponen).
- `tipo_senal` ∈ {fm, am, tv}: enum en Python + CHECK constraint en la BD.

Además, `GET /estaciones/afiliado/{afiliado_id}` lista las estaciones de un afiliado
(paginado, con filtro activo/q) para el panel anidado.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.afiliado import Afiliado, AfiliadoRepository
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase, ListParams, Page


class TipoSenal(StrEnum):
    FM = "fm"
    AM = "am"
    TV = "tv"


class Estacion(Base):
    __tablename__ = "estacion"
    __table_args__ = (
        CheckConstraint(
            "tipo_senal IN ('fm', 'am', 'tv')", name="ck_estacion_tipo_senal"
        ),
    )

    estacion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    afiliado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("afiliado.afiliado_id"), index=True
    )
    plaza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plaza.plaza_id"), index=True
    )
    nombre_estacion: Mapped[str] = mapped_column(Unicode(120), index=True)
    frecuencia: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    tipo_senal: Mapped[str] = mapped_column(Unicode(4))
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas (sin plaza_id: es derivada del afiliado) ────────────────────────────
class EstacionCreate(BaseModel):
    afiliado_id: uuid.UUID
    nombre_estacion: str = Field(min_length=1, max_length=120)
    frecuencia: str | None = Field(default=None, max_length=40)
    tipo_senal: TipoSenal


class EstacionUpdate(BaseModel):
    afiliado_id: uuid.UUID | None = None
    nombre_estacion: str | None = Field(default=None, min_length=1, max_length=120)
    frecuencia: str | None = Field(default=None, max_length=40)
    tipo_senal: TipoSenal | None = None


class EstacionRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    estacion_id: uuid.UUID
    afiliado_id: uuid.UUID
    plaza_id: uuid.UUID  # heredada del afiliado
    nombre_estacion: str
    frecuencia: str | None = None
    tipo_senal: TipoSenal


# ── Repositorio ───────────────────────────────────────────────────────────────
class EstacionRepository(BaseRepository[Estacion]):
    def contar_activas_por_afiliado(self, afiliado_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Estacion)
            # `== True` → `activo = 1`, portable a SQL Server (la variante IS-booleana no
            # lo es: IS solo compara con NULL en SQL Server). Ver ADR-014.
            .where(Estacion.afiliado_id == afiliado_id, Estacion.activo == True)  # noqa: E712
        )
        return int(total or 0)

    def contar_activas_por_plaza(self, plaza_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Estacion)
            .where(Estacion.plaza_id == plaza_id, Estacion.activo == True)  # noqa: E712
        )
        return int(total or 0)

    def contar_por_afiliados(self, afiliado_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Conteo de estaciones (TODAS, activas e inactivas) por afiliado, en UNA consulta.

        Se usa para enriquecer la lista de afiliados sin caer en N+1.
        """
        if not afiliado_ids:
            return {}
        rows = self.db.execute(
            select(Estacion.afiliado_id, func.count(Estacion.estacion_id))
            .where(Estacion.afiliado_id.in_(set(afiliado_ids)))
            .group_by(Estacion.afiliado_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def contar_por_plazas(self, plaza_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Conteo de estaciones (TODAS) por plaza, en UNA consulta (mismo criterio que
        el conteo por afiliado). Evita N+1 al enriquecer la lista de plazas."""
        if not plaza_ids:
            return {}
        rows = self.db.execute(
            select(Estacion.plaza_id, func.count(Estacion.estacion_id))
            .where(Estacion.plaza_id.in_(set(plaza_ids)))
            .group_by(Estacion.plaza_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def list_por_afiliado(
        self, afiliado_id: uuid.UUID, params: ListParams
    ) -> tuple[Sequence[Estacion], int]:
        base = select(Estacion).where(Estacion.afiliado_id == afiliado_id)
        if params.activo is not None:
            base = base.where(Estacion.activo == params.activo)
        if params.q:
            base = base.where(Estacion.nombre_estacion.ilike(f"%{params.q.strip()}%"))
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.order_by(Estacion.nombre_estacion)
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )
        return self.db.scalars(stmt).all(), int(total)


# ── Servicio ──────────────────────────────────────────────────────────────────
class EstacionService(BaseService[Estacion, EstacionCreate, EstacionUpdate, EstacionRead]):
    read_schema = EstacionRead
    entidad = "Estacion"

    def __init__(
        self, repo: EstacionRepository, *, afiliado_repo: AfiliadoRepository
    ) -> None:
        super().__init__(repo)
        self._estacion_repo = repo
        self._afiliado_repo = afiliado_repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        # ADR-005: la plaza se hereda del afiliado; nunca se confía en el cliente.
        payload["plaza_id"] = self._plaza_de_afiliado(payload["afiliado_id"])

    def _pre_update(
        self, obj: Estacion, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        # Si cambia el afiliado, se recalcula la plaza heredada.
        if "afiliado_id" in payload:
            payload["plaza_id"] = self._plaza_de_afiliado(payload["afiliado_id"])

    def _plaza_de_afiliado(self, afiliado_id: uuid.UUID) -> uuid.UUID:
        afiliado = self._afiliado_repo.get(afiliado_id)
        if afiliado is None:
            raise NotFoundError(
                "Afiliado no encontrado para derivar la plaza de la estación.",
                detalles={"afiliado_id": str(afiliado_id)},
            )
        return afiliado.plaza_id

    def list_por_afiliado(
        self, afiliado_id: uuid.UUID, params: ListParams
    ) -> Page[EstacionRead]:
        items, total = self._estacion_repo.list_por_afiliado(afiliado_id, params)
        return Page[EstacionRead](
            items=[self._to_read(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_estacion_service(db: Session = Depends(get_db)) -> EstacionService:
    repo = EstacionRepository(
        db, Estacion, search_columns=[Estacion.nombre_estacion, Estacion.frecuencia]
    )
    return EstacionService(repo, afiliado_repo=AfiliadoRepository(db, Afiliado))


router = build_crud_router(
    prefix="/estaciones",
    tags=["catalogos:estaciones"],
    permiso_base="catalogos",
    read_schema=EstacionRead,
    create_schema=EstacionCreate,
    update_schema=EstacionUpdate,
    get_service=get_estacion_service,
    id_type=uuid.UUID,
)


@router.get("/afiliado/{afiliado_id}", response_model=Page[EstacionRead])
def listar_por_afiliado(
    afiliado_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activas, false=inactivas"),
    q: str | None = Query(None, description="Búsqueda por nombre de estación"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: EstacionService = Depends(get_estacion_service),
) -> Page[EstacionRead]:
    """Estaciones de un afiliado (para el panel anidado de la pantalla de afiliados)."""
    return svc.list_por_afiliado(
        afiliado_id, ListParams(page=page, size=size, activo=activo, q=q)
    )
