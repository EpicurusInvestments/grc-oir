"""Catálogo TarifaPlaza (F0-02).

Tarifa de referencia por **plaza + tipo de señal + duración de spot**, con vigencia y un
campo CALCULADO (`tarifa_neta`). Se sugiere al capturar órdenes (F1). Monta la base de
F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`) y añade sus reglas en la capa de
servicio:

- **Campo calculado (spec):** `tarifa_neta = tarifa_bruta * (1 - descuento_pct / 100)`.
  Lo calcula el servicio con `Decimal` y se persiste; NO se acepta en el request (no está
  en los schemas Create/Update).
- **Vigencia:** `vigencia_hasta >= vigencia_desde`; ambas obligatorias (el negocio no maneja
  tarifas abiertas — decisión E-1).
- **Sin solapamiento:** para la misma combinación (plaza + tipo_senal + duracion_spot) no
  puede existir otra tarifa ACTIVA cuyo rango `[vigencia_desde, vigencia_hasta]` se solape
  con la nueva → 409 `conflicto`.
- **`created_by`:** se guarda el username (texto), no FK: la tabla `Usuario` llega en F0-04
  (decisión E-2).

Además, la lista soporta el filtro derivado **Vigentes/Expiradas** (según `vigencia_hasta`
vs hoy), que el CRUD genérico no cubre: se reemplaza SOLO la ruta `listar` que arma la
factory, SIN tocar `crud_router.py` (decisión E-3).

Portabilidad SQL Server: las comparaciones booleanas usan `== True` (→ `activo = 1`), nunca
la variante booleana de `.is_` (ver ADR-014); las de fecha se hacen contra parámetros `date`
de Python, sin funciones de fecha del motor.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from math import ceil
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Unicode,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.schemas import CatalogoReadBase, ListParams, Page


class TipoSenal(StrEnum):
    FM = "fm"
    AM = "am"
    TV = "tv"


class DuracionSpot(StrEnum):
    S20 = "20s"
    S30 = "30s"
    S60 = "60s"
    MENCION = "mencion"


CENTAVOS = Decimal("0.01")


def calcular_tarifa_neta(tarifa_bruta: Decimal, descuento_pct: Decimal) -> Decimal:
    """Fórmula de la spec: `neta = bruta * (1 - descuento/100)`, con Decimal a 2 decimales."""
    factor = (Decimal(100) - descuento_pct) / Decimal(100)
    return (tarifa_bruta * factor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class TarifaPlaza(Base):
    __tablename__ = "tarifa_plaza"
    __table_args__ = (
        CheckConstraint(
            "tipo_senal IN ('fm', 'am', 'tv')", name="ck_tarifa_plaza_tipo_senal"
        ),
        CheckConstraint(
            "duracion_spot IN ('20s', '30s', '60s', 'mencion')",
            name="ck_tarifa_plaza_duracion_spot",
        ),
        CheckConstraint(
            "descuento_pct >= 0 AND descuento_pct <= 100",
            name="ck_tarifa_plaza_descuento_pct",
        ),
        CheckConstraint(
            "vigencia_hasta >= vigencia_desde", name="ck_tarifa_plaza_vigencia"
        ),
        # Acelera el filtrado por combinación y la consulta de solapamiento.
        Index("ix_tarifa_plaza_combo", "plaza_id", "tipo_senal", "duracion_spot"),
    )

    tarifa_plaza_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    plaza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plaza.plaza_id"), index=True
    )
    tipo_senal: Mapped[str] = mapped_column(Unicode(4))
    duracion_spot: Mapped[str] = mapped_column(Unicode(10))
    tarifa_bruta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # Calculado por el servicio (no se acepta del cliente) y persistido.
    tarifa_neta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    vigencia_desde: Mapped[date] = mapped_column(Date())
    vigencia_hasta: Mapped[date] = mapped_column(Date())
    notas: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # Username del capturista (texto, no FK: no hay tabla Usuario hasta F0-04). Ver E-2.
    created_by: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class TarifaPlazaCreate(BaseModel):
    plaza_id: uuid.UUID
    tipo_senal: TipoSenal
    duracion_spot: DuracionSpot
    tarifa_bruta: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    descuento_pct: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )
    vigencia_desde: date
    vigencia_hasta: date
    notas: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _valida_vigencia(self) -> TarifaPlazaCreate:
        if self.vigencia_hasta < self.vigencia_desde:
            raise ValueError("vigencia_hasta debe ser mayor o igual que vigencia_desde.")
        return self


class TarifaPlazaUpdate(BaseModel):
    plaza_id: uuid.UUID | None = None
    tipo_senal: TipoSenal | None = None
    duracion_spot: DuracionSpot | None = None
    tarifa_bruta: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    descuento_pct: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    notas: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _valida_vigencia(self) -> TarifaPlazaUpdate:
        # Solo se puede validar aquí si vienen AMBAS fechas; si viene una, el servicio
        # completa con el valor actual del registro y valida con los valores efectivos.
        if (
            self.vigencia_desde is not None
            and self.vigencia_hasta is not None
            and self.vigencia_hasta < self.vigencia_desde
        ):
            raise ValueError("vigencia_hasta debe ser mayor o igual que vigencia_desde.")
        return self


class TarifaPlazaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    tarifa_plaza_id: uuid.UUID
    plaza_id: uuid.UUID
    tipo_senal: TipoSenal
    duracion_spot: DuracionSpot
    tarifa_bruta: Decimal
    descuento_pct: Decimal
    tarifa_neta: Decimal  # Calculado por el servicio (solo lectura)
    vigencia_desde: date
    vigencia_hasta: date
    notas: str | None = None
    created_by: str | None = None
    # Derivados (solo lectura; NO se aceptan en Create/Update):
    plaza_nombre: str | None = None  # nombre_plaza de la plaza referenciada
    plaza_estado: str | None = None  # estado (geográfico) de la plaza

    # Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4).
    @field_serializer("tarifa_bruta", "descuento_pct", "tarifa_neta")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Parámetros de lista (extienden los genéricos con el filtro de vigencia) ──────
class TarifaListParams(ListParams):
    """`ListParams` + filtro por plaza + filtro derivado por vigencia.

    `hoy` lo fija el servidor. `plaza_id` acota a una plaza (lo usa el panel de detalle de
    Plaza para listar sus tarifas vigentes).
    """

    plaza_id: uuid.UUID | None = None
    vigencia: Literal["todas", "vigente", "expirada"] = "todas"
    hoy: date | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class TarifaRepository(BaseRepository[TarifaPlaza]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # La base aplica `activo`; `q` NO (search_columns vacío) porque la búsqueda de
        # tarifas abarca campos de la PLAZA (nombre/estado) además de notas → requiere JOIN.
        stmt = super()._apply_filters(stmt, params)
        plaza_id = getattr(params, "plaza_id", None)
        if plaza_id is not None:
            stmt = stmt.where(TarifaPlaza.plaza_id == plaza_id)
        q = (getattr(params, "q", None) or "").strip()
        if q:
            patron = f"%{q}%"
            # Un solo JOIN con plaza (relación N:1, no duplica filas). Coincidencia parcial
            # case-insensitive en cualquiera de los tres campos. `ilike` es portable a SQL
            # Server (compila a lower(...) LIKE lower(...)); `estado` puede ser NULL y
            # simplemente no coincide.
            stmt = stmt.join(Plaza, TarifaPlaza.plaza_id == Plaza.plaza_id).where(
                or_(
                    Plaza.nombre_plaza.ilike(patron),
                    Plaza.estado.ilike(patron),
                    TarifaPlaza.notas.ilike(patron),
                )
            )
        vigencia = getattr(params, "vigencia", "todas")
        hoy = getattr(params, "hoy", None)
        if hoy is not None and vigencia == "vigente":
            stmt = stmt.where(TarifaPlaza.vigencia_hasta >= hoy)
        elif hoy is not None and vigencia == "expirada":
            stmt = stmt.where(TarifaPlaza.vigencia_hasta < hoy)
        return stmt

    def existe_solapamiento(
        self,
        *,
        plaza_id: uuid.UUID,
        tipo_senal: str,
        duracion_spot: str,
        desde: date,
        hasta: date,
        excluir_id: uuid.UUID | None = None,
    ) -> TarifaPlaza | None:
        """Devuelve la primera tarifa ACTIVA que se solapa con [desde, hasta] para la misma
        combinación, o None. Solapamiento de intervalos cerrados: `a_desde <= b_hasta AND
        b_desde <= a_hasta` (bordes inclusivos: tocarse un día ya cuenta como solape)."""
        stmt = select(TarifaPlaza).where(
            TarifaPlaza.plaza_id == plaza_id,
            TarifaPlaza.tipo_senal == tipo_senal,
            TarifaPlaza.duracion_spot == duracion_spot,
            TarifaPlaza.activo == True,  # noqa: E712  (portable a SQL Server; ver ADR-014)
            TarifaPlaza.vigencia_desde <= hasta,
            TarifaPlaza.vigencia_hasta >= desde,
        )
        if excluir_id is not None:
            stmt = stmt.where(TarifaPlaza.tarifa_plaza_id != excluir_id)
        return self.db.scalars(stmt).first()

    def datos_de_plazas(
        self, plaza_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str | None]]:
        """(nombre, estado) de cada plaza por id, en UNA consulta (evita N+1 al enriquecer)."""
        if not plaza_ids:
            return {}
        rows = self.db.execute(
            select(Plaza.plaza_id, Plaza.nombre_plaza, Plaza.estado).where(
                Plaza.plaza_id.in_(set(plaza_ids))
            )
        ).all()
        return {row[0]: (row[1], row[2]) for row in rows}


# ── Servicio ──────────────────────────────────────────────────────────────────
class TarifaService(
    BaseService[TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate, TarifaPlazaRead]
):
    read_schema = TarifaPlazaRead
    entidad = "TarifaPlaza"

    def __init__(
        self, repo: TarifaRepository, *, plaza_repo: BaseRepository[Plaza]
    ) -> None:
        super().__init__(repo)
        self._tarifa_repo = repo
        self._plaza_repo = plaza_repo

    # ── enriquecimiento (plaza_nombre + plaza_estado) ───────────────────────────
    def _read(
        self, obj: TarifaPlaza, plaza_nombre: str | None, plaza_estado: str | None
    ) -> TarifaPlazaRead:
        return TarifaPlazaRead.model_validate(obj).model_copy(
            update={"plaza_nombre": plaza_nombre, "plaza_estado": plaza_estado}
        )

    def _to_read(self, obj: TarifaPlaza) -> TarifaPlazaRead:
        datos = self._tarifa_repo.datos_de_plazas([obj.plaza_id]).get(obj.plaza_id)
        nombre, estado = datos if datos else (None, None)
        return self._read(obj, nombre, estado)

    def list(self, params: ListParams) -> Page[TarifaPlazaRead]:
        # Enriquecimiento por LOTE: 2 consultas por página (lista + datos de plazas).
        items, total = self.repo.list(params)
        datos = self._tarifa_repo.datos_de_plazas([t.plaza_id for t in items])
        return Page[TarifaPlazaRead](
            items=[self._read(t, *(datos.get(t.plaza_id) or (None, None))) for t in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    # ── reglas de negocio ────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_plaza(payload["plaza_id"])
        payload["tarifa_neta"] = calcular_tarifa_neta(
            payload["tarifa_bruta"], payload["descuento_pct"]
        )
        payload["created_by"] = usuario.username
        # Una tarifa se crea ACTIVA → siempre se valida el solapamiento.
        self._verificar_sin_solapamiento(
            plaza_id=payload["plaza_id"],
            tipo_senal=payload["tipo_senal"],
            duracion_spot=payload["duracion_spot"],
            desde=payload["vigencia_desde"],
            hasta=payload["vigencia_hasta"],
            excluir_id=None,
        )

    def _pre_update(
        self, obj: TarifaPlaza, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "plaza_id" in payload:
            self._verificar_plaza(payload["plaza_id"])

        # Valores EFECTIVOS: lo que trae el payload o, si no, el valor actual del registro.
        plaza_id = payload.get("plaza_id", obj.plaza_id)
        tipo_senal = payload.get("tipo_senal", obj.tipo_senal)
        duracion_spot = payload.get("duracion_spot", obj.duracion_spot)
        bruta = payload.get("tarifa_bruta", obj.tarifa_bruta)
        descuento = payload.get("descuento_pct", obj.descuento_pct)
        desde = payload.get("vigencia_desde", obj.vigencia_desde)
        hasta = payload.get("vigencia_hasta", obj.vigencia_hasta)

        if hasta < desde:
            raise DomainError(
                "vigencia_hasta debe ser mayor o igual que vigencia_desde.",
                detalles={"vigencia_desde": str(desde), "vigencia_hasta": str(hasta)},
            )

        # Recalcular siempre la neta a partir de los valores efectivos (nunca del cliente).
        payload["tarifa_neta"] = calcular_tarifa_neta(bruta, descuento)

        # Solo tiene sentido revalidar el solapamiento si la tarifa está ACTIVA.
        if obj.activo:
            self._verificar_sin_solapamiento(
                plaza_id=plaza_id,
                tipo_senal=tipo_senal,
                duracion_spot=duracion_spot,
                desde=desde,
                hasta=hasta,
                excluir_id=obj.tarifa_plaza_id,
            )

    def cambiar_estado(
        self, id_: Any, activo: bool, usuario: CurrentUser, forzar: bool = False
    ) -> TarifaPlazaRead:
        obj = self._get_or_404(id_)
        # Al REACTIVAR, revalidar el solapamiento (otra tarifa pudo cubrir ese rango).
        if activo and not obj.activo:
            self._verificar_sin_solapamiento(
                plaza_id=obj.plaza_id,
                tipo_senal=obj.tipo_senal,
                duracion_spot=obj.duracion_spot,
                desde=obj.vigencia_desde,
                hasta=obj.vigencia_hasta,
                excluir_id=obj.tarifa_plaza_id,
            )
        # TarifaPlaza no tiene dependientes: la baja lógica no se bloquea (no usa `forzar`).
        return self._to_read(self.repo.set_activo(obj, activo))

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _verificar_plaza(self, plaza_id: uuid.UUID) -> None:
        if self._plaza_repo.get(plaza_id) is None:
            raise NotFoundError(
                "Plaza no encontrada para la tarifa.",
                detalles={"plaza_id": str(plaza_id)},
            )

    def _verificar_sin_solapamiento(
        self,
        *,
        plaza_id: uuid.UUID,
        tipo_senal: str,
        duracion_spot: str,
        desde: date,
        hasta: date,
        excluir_id: uuid.UUID | None,
    ) -> None:
        conflicto = self._tarifa_repo.existe_solapamiento(
            plaza_id=plaza_id,
            tipo_senal=tipo_senal,
            duracion_spot=duracion_spot,
            desde=desde,
            hasta=hasta,
            excluir_id=excluir_id,
        )
        if conflicto is not None:
            raise ConflictError(
                "Ya existe una tarifa activa cuyo periodo se solapa con esta vigencia para "
                "la misma plaza, tipo de señal y duración.",
                detalles={
                    "tarifa_en_conflicto": str(conflicto.tarifa_plaza_id),
                    "vigencia_desde": str(conflicto.vigencia_desde),
                    "vigencia_hasta": str(conflicto.vigencia_hasta),
                },
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_tarifa_service(db: Session = Depends(get_db)) -> TarifaService:
    # Sin `search_columns`: la búsqueda `q` se maneja en TarifaRepository._apply_filters con
    # un JOIN a plaza (abarca nombre/estado de la plaza + notas).
    repo = TarifaRepository(db, TarifaPlaza)
    return TarifaService(repo, plaza_repo=BaseRepository(db, Plaza))


router = build_crud_router(
    prefix="/tarifas",
    tags=["catalogos:tarifas"],
    permiso_base="catalogos",
    read_schema=TarifaPlazaRead,
    create_schema=TarifaPlazaCreate,
    update_schema=TarifaPlazaUpdate,
    get_service=get_tarifa_service,
    id_type=uuid.UUID,
)

# La factory arma un `listar` genérico (page/size/activo/q). La tarifa necesita ADEMÁS el
# filtro derivado Vigentes/Expiradas (vigencia_hasta vs hoy). Se retira SOLO esa ruta y se
# registra una equivalente que acepta `vigencia`, sin tocar `crud_router.py` (decisión E-3).
# El resto de endpoints (get/create/update/estado) de la factory quedan intactos.
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[TarifaPlazaRead])
def listar_tarifas(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todas, true=activas, false=inactivas"),
    q: str | None = Query(None, description="Búsqueda de texto en notas"),
    plaza_id: uuid.UUID | None = Query(None, description="Acota a una plaza"),
    vigencia: Literal["todas", "vigente", "expirada"] = Query(
        "todas", description="Filtro derivado por vigencia_hasta vs la fecha actual"
    ),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: TarifaService = Depends(get_tarifa_service),
) -> Page[TarifaPlazaRead]:
    """Lista de tarifas con filtros: plaza, activo/inactivo, texto y vigencia.

    `hoy` se fija en el servidor (no se confía al cliente) para el filtro de vigencia.
    """
    return svc.list(
        TarifaListParams(
            page=page,
            size=size,
            activo=activo,
            q=q,
            plaza_id=plaza_id,
            vigencia=vigencia,
            hoy=date.today(),
        )
    )
