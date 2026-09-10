"""MovimientoBancario (F3) — movimiento cargado por Tesorería, referencia para
conciliación manual.

Sin máquina de estados: `conciliado` es un `BIT` que solo cambia por el botón
"Conciliar" (confirmado contra el prototipo `Fase_3_-_Cobranza.html`: sin matching
automático en esta versión — el propio mockup lo deja como "sin coincidencias
automáticas"). Una vez `conciliado=True` no se puede desconciliar por este endpoint: es
un candado de una sola vía, igual que el mockup ("Marcar conciliado" desaparece del panel
en cuanto ya lo está).

**Primera vez que Tesorería pasa de solo-lectura a captura en el proyecto.** Resuelto
con el MISMO canal dedicado que ya usa la autorización de Dirección en `Requisicion`
(ADR-046), no dándole `WRITE` de módulo: `_nivel()` resuelve por MÓDULO, y este archivo
comparte la clave `pagos` con `Requisicion` (CxP). Si Tesorería tuviera `pagos:editar`,
también podría capturar/autorizar `Requisicion`, que la ficha reserva para CxP/Dirección.
Así que los endpoints de escritura de este archivo piden `pagos:leer` en el router (el
nivel que Tesorería SÍ tiene) y verifican `área in (TESORERIA, ADMIN)` dentro del
servicio — igual que `Requisicion.autorizar` verifica `área in (DIRECCION, ADMIN)`.

Valida duplicados antes de insertar (`CLAUDE.md`, regla de integraciones): mismo banco
—aquí no hay entidad Banco propia, así que se usa el mismo movimiento— identificado por
`(fecha_movimiento, monto_movimiento, referencia_bancaria)`. Con esos 3 iguales, 409.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.auth.identity import Area
from app.core.db import Base, datetime2, fecha_sql, get_db
from app.core.errors import ConflictError, PermissionDeniedError
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.schemas import ListParams, Page


class TipoMovimiento(StrEnum):
    CARGO = "cargo"
    ABONO = "abono"


_TIPOS_SQL = ", ".join(f"'{t.value}'" for t in TipoMovimiento)


# ── Modelo ────────────────────────────────────────────────────────────────────
class MovimientoBancario(Base):
    __tablename__ = "movimiento_bancario"
    __table_args__ = (
        CheckConstraint(f"tipo_movimiento IN ({_TIPOS_SQL})", name="ck_movimiento_bancario_tipo"),
        CheckConstraint("monto_movimiento > 0", name="ck_movimiento_bancario_monto"),
    )

    movimiento_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    fecha_movimiento: Mapped[date] = mapped_column(fecha_sql())
    tipo_movimiento: Mapped[str] = mapped_column(Unicode(20))
    monto_movimiento: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    referencia_bancaria: Mapped[str | None] = mapped_column(Unicode(100), default=None)
    descripcion_movimiento: Mapped[str | None] = mapped_column(Unicode(300), default=None)
    conciliado: Mapped[bool] = mapped_column(default=False)
    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "usuario.usuario_id", name="fk_movimiento_bancario_created_by", ondelete="NO ACTION"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


# ── Schemas ───────────────────────────────────────────────────────────────────
class MovimientoBancarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movimiento_id: uuid.UUID
    fecha_movimiento: date
    tipo_movimiento: TipoMovimiento
    monto_movimiento: Decimal
    referencia_bancaria: str | None = None
    descripcion_movimiento: str | None = None
    conciliado: bool
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime


class MovimientoBancarioListParams(ListParams):
    tipo_movimiento: str | None = None
    conciliado: bool | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


class MovimientoBancarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_movimiento: date
    tipo_movimiento: TipoMovimiento
    monto_movimiento: Decimal = Field(gt=0)
    referencia_bancaria: str | None = Field(default=None, max_length=100)
    descripcion_movimiento: str | None = Field(default=None, max_length=300)
    archivo_nombre: str | None = None
    archivo_path: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class MovimientoBancarioRepository(BaseRepository[MovimientoBancario]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        tipo = getattr(params, "tipo_movimiento", None)
        if tipo is not None:
            stmt = stmt.where(MovimientoBancario.tipo_movimiento == tipo)
        conciliado = getattr(params, "conciliado", None)
        if conciliado is not None:
            stmt = stmt.where(MovimientoBancario.conciliado == conciliado)
        desde = getattr(params, "fecha_desde", None)
        if desde is not None:
            stmt = stmt.where(MovimientoBancario.fecha_movimiento >= desde)
        hasta = getattr(params, "fecha_hasta", None)
        if hasta is not None:
            stmt = stmt.where(MovimientoBancario.fecha_movimiento <= hasta)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(
                MovimientoBancario.referencia_bancaria.ilike(patron)
                | MovimientoBancario.descripcion_movimiento.ilike(patron)
            )
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class MovimientoBancarioService:
    """Sin `BaseService`: la captura y el "Conciliar" exigen el canal dedicado de
    Tesorería (ver docstring del módulo), que `BaseService`/`requiere_permiso` de
    módulo no pueden expresar por sí solos."""

    entidad = "MovimientoBancario"

    def __init__(self, repo: MovimientoBancarioRepository) -> None:
        self._repo = repo

    def _requiere_tesoreria(self, usuario: CurrentUser) -> None:
        if usuario.area not in (Area.TESORERIA, Area.ADMIN):
            raise PermissionDeniedError(
                f"El área '{usuario.area.value}' no puede capturar movimientos "
                "bancarios — solo Tesorería."
            )

    def list(self, params: MovimientoBancarioListParams) -> Page[MovimientoBancarioRead]:
        items, total = self._repo.list(params)
        from math import ceil

        return Page[MovimientoBancarioRead](
            items=[MovimientoBancarioRead.model_validate(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def get(self, id_: uuid.UUID) -> MovimientoBancarioRead:
        from app.core.errors import NotFoundError

        obj = self._repo.db.get(MovimientoBancario, id_)
        if obj is None:
            raise NotFoundError(
                "MovimientoBancario no encontrado.", detalles={"movimiento_id": str(id_)}
            )
        return MovimientoBancarioRead.model_validate(obj)

    def crear(
        self, data: MovimientoBancarioCreate, usuario: CurrentUser
    ) -> MovimientoBancarioRead:
        self._requiere_tesoreria(usuario)
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        # Duplicados: mismo (fecha, monto, referencia) — regla de integraciones del
        # CLAUDE.md. `referencia_bancaria` puede ser NULL (cargos/abonos sin referencia
        # capturada); en ese caso solo se compara fecha+monto, que sigue siendo una señal
        # razonable de "esto ya se cargó dos veces".
        duplicado_stmt = select(MovimientoBancario.movimiento_id).where(
            MovimientoBancario.fecha_movimiento == data.fecha_movimiento,
            MovimientoBancario.monto_movimiento == data.monto_movimiento,
        )
        if data.referencia_bancaria is not None:
            duplicado_stmt = duplicado_stmt.where(
                MovimientoBancario.referencia_bancaria == data.referencia_bancaria
            )
        else:
            duplicado_stmt = duplicado_stmt.where(MovimientoBancario.referencia_bancaria.is_(None))
        if db.scalar(duplicado_stmt) is not None:
            raise ConflictError(
                "Ya existe un movimiento bancario con la misma fecha, monto y "
                "referencia — probable carga duplicada.",
                detalles={
                    "fecha_movimiento": str(data.fecha_movimiento),
                    "monto_movimiento": str(data.monto_movimiento),
                    "referencia_bancaria": data.referencia_bancaria,
                },
            )

        obj = MovimientoBancario(
            movimiento_id=uuid4(),
            **data.model_dump(),
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return MovimientoBancarioRead.model_validate(obj)

    def conciliar(self, movimiento_id: uuid.UUID, usuario: CurrentUser) -> MovimientoBancarioRead:
        """Botón "Conciliar" del mockup: SOLO manual, sin matching automático.
        Idempotente si ya estaba conciliado; sin transición de vuelta (una sola vía)."""
        self._requiere_tesoreria(usuario)
        db = self._repo.db
        obj = db.get(MovimientoBancario, movimiento_id)
        if obj is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(
                "MovimientoBancario no encontrado.", detalles={"movimiento_id": str(movimiento_id)}
            )
        if not obj.conciliado:
            obj.conciliado = True
            db.commit()
            db.refresh(obj)
        return MovimientoBancarioRead.model_validate(obj)


def get_movimiento_bancario_service(
    db: Session = Depends(get_db),
) -> MovimientoBancarioService:
    return MovimientoBancarioService(
        MovimientoBancarioRepository(
            db, MovimientoBancario, default_order_by=[MovimientoBancario.fecha_movimiento]
        )
    )


# ── Router ────────────────────────────────────────────────────────────────────
# Todo el archivo pide `pagos:leer` en el router (el mínimo común entre CxP y
# Tesorería) — el guardarraíl real de "solo Tesorería captura" vive en el servicio.
router = APIRouter(prefix="/movimientos-bancarios", tags=["pagos:movimientos-bancarios"])


@router.get("", response_model=Page[MovimientoBancarioRead])
def listar_movimientos_bancarios(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en referencia o descripción"),
    tipo_movimiento: str | None = Query(None),
    conciliado: bool | None = Query(None),
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: MovimientoBancarioService = Depends(get_movimiento_bancario_service),
) -> Page[MovimientoBancarioRead]:
    return svc.list(
        MovimientoBancarioListParams(
            page=page,
            size=size,
            q=q,
            tipo_movimiento=tipo_movimiento,
            conciliado=conciliado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    )


@router.get("/{item_id}", response_model=MovimientoBancarioRead)
def obtener_movimiento_bancario(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: MovimientoBancarioService = Depends(get_movimiento_bancario_service),
) -> MovimientoBancarioRead:
    return svc.get(item_id)


@router.post("", response_model=MovimientoBancarioRead, status_code=201)
def crear_movimiento_bancario(
    payload: MovimientoBancarioCreate,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: MovimientoBancarioService = Depends(get_movimiento_bancario_service),
) -> MovimientoBancarioRead:
    """Canal dedicado de Tesorería (ADR-046): permiso de router `pagos:leer`, el
    guardarraíl real (`área in (TESORERIA, ADMIN)`) se valida dentro del servicio."""
    return svc.crear(payload, usuario)


@router.post("/{item_id}/conciliar", response_model=MovimientoBancarioRead)
def conciliar_movimiento_bancario(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: MovimientoBancarioService = Depends(get_movimiento_bancario_service),
) -> MovimientoBancarioRead:
    """El botón "Conciliar" del mockup — sin matching automático, mismo canal
    dedicado de Tesorería que la creación."""
    return svc.conciliar(item_id, usuario)
