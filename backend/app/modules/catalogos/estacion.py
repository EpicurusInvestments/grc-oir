"""Catálogo Estación / Emisora (F0-01).

Emisora (FM/AM/TV) operada por un afiliado. **Pantalla propia** (entrada de sidebar
independiente, ADR-094) — ya no se administra anidada dentro de Afiliados.

Reglas propias en la capa de servicio:

- **Plaza de selección libre (ADR-094, reemplaza a ADR-005):** antes `plaza_id` se
  heredaba SIEMPRE del afiliado y no se capturaba. El usuario pidió que la nueva pantalla
  de Estaciones permita elegir la plaza de forma independiente del afiliado (una emisora
  puede estar en una plaza distinta a la de su afiliado). `plaza_id` ahora es un campo
  normal, capturado y validado (existe la plaza) igual que `afiliado_id`.
- `siglas` (NUEVO, fuera de la spec BD v2 — petición del usuario): identificador corto de
  la emisora (p.ej. "XEW"), opcional.
- `tipo_senal` ∈ {fm, am, tv}: enum en Python + CHECK constraint en la BD.

`GET /estaciones` acepta filtros opcionales `afiliado_id`/`plaza_id` (además de
`activo`/`q` genéricos) para la pantalla independiente; `GET /estaciones/afiliado/{id}`
sigue existiendo para quien solo necesite las de un afiliado (p.ej. el combo de
Facturación/Órdenes).
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
from app.modules.catalogos.plaza import Plaza
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase, ListParams, Page


class TipoSenal(StrEnum):
    FM = "fm"
    AM = "am"
    TV = "tv"


class Estacion(Base):
    __tablename__ = "estacion"
    __table_args__ = (
        CheckConstraint("tipo_senal IN ('fm', 'am', 'tv')", name="ck_estacion_tipo_senal"),
    )

    estacion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    afiliado_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("afiliado.afiliado_id"), index=True)
    plaza_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plaza.plaza_id"), index=True)
    nombre_estacion: Mapped[str] = mapped_column(Unicode(120), index=True)
    siglas: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    frecuencia: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    tipo_senal: Mapped[str] = mapped_column(Unicode(4))
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ─────────────────────────────────────────────────────────────────────
class EstacionCreate(BaseModel):
    afiliado_id: uuid.UUID
    plaza_id: uuid.UUID
    nombre_estacion: str = Field(min_length=1, max_length=120)
    siglas: str | None = Field(default=None, max_length=20)
    frecuencia: str | None = Field(default=None, max_length=40)
    tipo_senal: TipoSenal


class EstacionUpdate(BaseModel):
    afiliado_id: uuid.UUID | None = None
    plaza_id: uuid.UUID | None = None
    nombre_estacion: str | None = Field(default=None, min_length=1, max_length=120)
    siglas: str | None = Field(default=None, max_length=20)
    frecuencia: str | None = Field(default=None, max_length=40)
    tipo_senal: TipoSenal | None = None


class EstacionRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    estacion_id: uuid.UUID
    afiliado_id: uuid.UUID
    plaza_id: uuid.UUID
    nombre_estacion: str
    siglas: str | None = None
    frecuencia: str | None = None
    tipo_senal: TipoSenal
    # Derivados (solo lectura; NO se aceptan en Create/Update):
    afiliado_nombre: str | None = None
    plaza_nombre: str | None = None


class EstacionListParams(ListParams):
    """`ListParams` + filtros opcionales por afiliado/plaza, para la pantalla propia."""

    afiliado_id: uuid.UUID | None = None
    plaza_id: uuid.UUID | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class EstacionRepository(BaseRepository[Estacion]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        stmt = super()._apply_filters(stmt, params)  # activo + q sobre search_columns
        afiliado_id = getattr(params, "afiliado_id", None)
        if afiliado_id is not None:
            stmt = stmt.where(Estacion.afiliado_id == afiliado_id)
        plaza_id = getattr(params, "plaza_id", None)
        if plaza_id is not None:
            stmt = stmt.where(Estacion.plaza_id == plaza_id)
        return stmt

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

    def nombres_de_afiliados(self, afiliado_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nombre de afiliado por id, en UNA consulta (evita N+1 al enriquecer la lista)."""
        if not afiliado_ids:
            return {}
        rows = self.db.execute(
            select(Afiliado.afiliado_id, Afiliado.nombre_afiliado).where(
                Afiliado.afiliado_id.in_(set(afiliado_ids))
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    def nombres_de_plazas(self, plaza_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nombre de plaza por id, en UNA consulta (evita N+1 al enriquecer la lista)."""
        if not plaza_ids:
            return {}
        rows = self.db.execute(
            select(Plaza.plaza_id, Plaza.nombre_plaza).where(Plaza.plaza_id.in_(set(plaza_ids)))
        ).all()
        return {row[0]: row[1] for row in rows}

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
        self,
        repo: EstacionRepository,
        *,
        afiliado_repo: AfiliadoRepository,
        plaza_repo: BaseRepository[Plaza],
    ) -> None:
        super().__init__(repo)
        self._estacion_repo = repo
        self._afiliado_repo = afiliado_repo
        self._plaza_repo = plaza_repo

    # ── enriquecimiento (afiliado_nombre + plaza_nombre) ────────────────────────
    def _read(
        self, obj: Estacion, afiliado_nombre: str | None, plaza_nombre: str | None
    ) -> EstacionRead:
        return EstacionRead.model_validate(obj).model_copy(
            update={"afiliado_nombre": afiliado_nombre, "plaza_nombre": plaza_nombre}
        )

    def _to_read(self, obj: Estacion) -> EstacionRead:
        afiliado_nombre = self._estacion_repo.nombres_de_afiliados([obj.afiliado_id]).get(
            obj.afiliado_id
        )
        plaza_nombre = self._estacion_repo.nombres_de_plazas([obj.plaza_id]).get(obj.plaza_id)
        return self._read(obj, afiliado_nombre, plaza_nombre)

    def list(self, params: ListParams) -> Page[EstacionRead]:
        items, total = self.repo.list(params)
        afiliados = self._estacion_repo.nombres_de_afiliados([e.afiliado_id for e in items])
        plazas = self._estacion_repo.nombres_de_plazas([e.plaza_id for e in items])
        return Page[EstacionRead](
            items=[
                self._read(e, afiliados.get(e.afiliado_id), plazas.get(e.plaza_id)) for e in items
            ],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_afiliado(payload["afiliado_id"])
        self._verificar_plaza(payload["plaza_id"])

    def _pre_update(self, obj: Estacion, payload: dict[str, Any], usuario: CurrentUser) -> None:
        if "afiliado_id" in payload:
            self._verificar_afiliado(payload["afiliado_id"])
        if "plaza_id" in payload:
            self._verificar_plaza(payload["plaza_id"])

    def _verificar_afiliado(self, afiliado_id: uuid.UUID) -> None:
        if self._afiliado_repo.get(afiliado_id) is None:
            raise NotFoundError(
                "Afiliado no encontrado para la estación.",
                detalles={"afiliado_id": str(afiliado_id)},
            )

    def _verificar_plaza(self, plaza_id: uuid.UUID) -> None:
        if self._plaza_repo.get(plaza_id) is None:
            raise NotFoundError(
                "Plaza no encontrada para la estación.",
                detalles={"plaza_id": str(plaza_id)},
            )

    def list_por_afiliado(self, afiliado_id: uuid.UUID, params: ListParams) -> Page[EstacionRead]:
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
        db,
        Estacion,
        search_columns=[Estacion.nombre_estacion, Estacion.siglas, Estacion.frecuencia],
    )
    return EstacionService(
        repo,
        afiliado_repo=AfiliadoRepository(db, Afiliado),
        plaza_repo=BaseRepository(db, Plaza),
    )


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

# La factory arma un `listar` genérico; la pantalla propia necesita ADEMÁS los filtros
# `afiliado_id`/`plaza_id`. Se retira SOLO esa ruta y se registra una equivalente con esos
# query params, sin tocar `crud_router.py` (mismo patrón que Anunciante, ADR-015 E-3).
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[EstacionRead])
def listar_estaciones(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todas, true=activas, false=inactivas"),
    q: str | None = Query(None, description="Búsqueda por nombre, siglas o frecuencia"),
    afiliado_id: uuid.UUID | None = Query(None, description="Filtra por afiliado"),
    plaza_id: uuid.UUID | None = Query(None, description="Filtra por plaza"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: EstacionService = Depends(get_estacion_service),
) -> Page[EstacionRead]:
    return svc.list(
        EstacionListParams(
            page=page, size=size, activo=activo, q=q, afiliado_id=afiliado_id, plaza_id=plaza_id
        )
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
    """Estaciones de un afiliado (lectura acotada, p.ej. combos de Órdenes/Facturación)."""
    return svc.list_por_afiliado(afiliado_id, ListParams(page=page, size=size, activo=activo, q=q))
