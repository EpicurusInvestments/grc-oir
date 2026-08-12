"""Incidencia (F1) — diferencia entre lo solicitado y lo verificado (spec BD v2).

Modelo HÍBRIDO (ADR-031): la spec define `tipo_incidencia` con 5 valores y un flujo de
`resolucion` manual completo — pensado para que un humano revise y resuelva cada caso.
La demo de frontend (y el prototipo aprobado) generan incidencias 100% automáticas, con
solo 2 tipos (`descuento`/`bonificacion` ahí; aquí `faltante`/`excedente`). Se concilian
así:

- La generación AUTOMÁTICA (al capturar `Verificacion` de un día) solo puede inferir
  `faltante` (spots_ejecutados < spots_ordenados) o `excedente` (>). `monto_ajuste` se
  autocalcula igual que en la demo: `diferencia_spots * precio_spot` de la OE.
- Los otros 3 tipos (`cambio_horario`, `cambio_fecha`, `spot_no_emitido`) NO se pueden
  inferir de una comparación de spots — quedan disponibles para **alta manual** (un
  endpoint de creación directa, no solo el trigger automático de Verificacion).
- `resolucion` (spec) se agrega completo, con default `pendiente`: es el único agregado
  de esta tabla frente a la demo, y no se pierde nada de lo ya construido.

`spots_ordenados` es "copia de spots asignados" según la literal de la spec, pero con el
modelo de 3 capas (ADR-030) el service la llena con el **programado EFECTIVO** del día
(spots_programados si no es NULL, si no spots_asignados) — mismo criterio que ya prueba
la demo de frontend, no el valor asignado en crudo.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


class TipoIncidencia(StrEnum):
    FALTANTE = "faltante"
    EXCEDENTE = "excedente"
    CAMBIO_HORARIO = "cambio_horario"
    CAMBIO_FECHA = "cambio_fecha"
    SPOT_NO_EMITIDO = "spot_no_emitido"


class ResolucionIncidencia(StrEnum):
    PENDIENTE = "pendiente"
    ACEPTADA = "aceptada"
    CREDITO_CLIENTE = "credito_cliente"
    DESCUENTO_AFILIADO = "descuento_afiliado"
    SIN_RESOLUCION = "sin_resolucion"


class Incidencia(Base):
    __tablename__ = "incidencia"
    __table_args__ = (
        CheckConstraint(
            "tipo_incidencia IN ('faltante', 'excedente', 'cambio_horario', "
            "'cambio_fecha', 'spot_no_emitido')",
            name="ck_incidencia_tipo",
        ),
        CheckConstraint(
            "resolucion IN ('pendiente', 'aceptada', 'credito_cliente', "
            "'descuento_afiliado', 'sin_resolucion')",
            name="ck_incidencia_resolucion",
        ),
        # Auditoría de migración a RDS (F1, Tanda 4): spots_ordenados/spots_ejecutados
        # son cantidades, nunca negativas — `diferencia_spots`/`monto_ajuste` SÍ pueden
        # serlo (representan faltante vs. excedente) y se dejan libres a propósito.
        CheckConstraint("spots_ordenados >= 0", name="ck_incidencia_spots_ordenados"),
        CheckConstraint("spots_ejecutados >= 0", name="ck_incidencia_spots_ejecutados"),
    )

    incidencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "verificacion.verificacion_id", name="fk_incidencia_verificacion", ondelete="NO ACTION"
        ),
        index=True,
    )
    # Denormalizado (spec): permite filtrar incidencias por OE sin pasar por Verificacion.
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_incidencia_orden_estacion",
            ondelete="NO ACTION",
        ),
        index=True,
    )
    tipo_incidencia: Mapped[str] = mapped_column(Unicode(20))
    # Derivados: copia del programado EFECTIVO (ver docstring) y de spots_verificados.
    spots_ordenados: Mapped[int] = mapped_column()
    spots_ejecutados: Mapped[int] = mapped_column()
    # Calculado (spec) = spots_ejecutados - spots_ordenados. Persistido por el servicio.
    diferencia_spots: Mapped[int] = mapped_column()
    descripcion_incidencia: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    fecha_incidencia: Mapped[date] = mapped_column(fecha_sql())
    # Mutable (a diferencia de Verificacion): `resolucion` se edita después del alta
    # (aceptada/credito_cliente/descuento_afiliado/sin_resolucion) — por eso SÍ lleva
    # `updated_at`, a diferencia de Verificacion (inmutable). Ausentes en la spec (11
    # campos exactos) pero exigidos por CLAUDE.md §6 ("updated_at en toda entidad"),
    # mismo criterio aditivo que ya aplicó ADR-011 en F0-01.
    resolucion: Mapped[str] = mapped_column(
        Unicode(20), default=ResolucionIncidencia.PENDIENTE.value
    )
    # Manual (spec); el servicio la autocalcula para faltante/excedente (ver docstring).
    monto_ajuste: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schema de lectura (Tanda 3 — API de lectura; alta manual llega en Tanda 5) ────────
class IncidenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incidencia_id: uuid.UUID
    verificacion_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    tipo_incidencia: TipoIncidencia
    spots_ordenados: int
    spots_ejecutados: int
    diferencia_spots: int
    descripcion_incidencia: str | None = None
    fecha_incidencia: date
    resolucion: ResolucionIncidencia
    monto_ajuste: Decimal | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @field_serializer("monto_ajuste")
    def _serializa_decimal(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class IncidenciaListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo`, pero NUNCA se expone como query
    param: `Incidencia` no tiene baja lógica. Se hereda solo por compatibilidad de tipo
    con `BaseRepository`/`BaseService`. `q` SÍ se usa (búsqueda en descripcion_incidencia,
    ver `_apply_filters` — no la de la base, que busca en `search_columns`)."""

    orden_estacion_id: uuid.UUID | None = None
    tipo_incidencia: TipoIncidencia | None = None
    resolucion: ResolucionIncidencia | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class IncidenciaRepository(BaseRepository[Incidencia]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`, columna
        # que Incidencia no tiene (no es de baja lógica).
        q = (getattr(params, "q", None) or "").strip()
        if q:
            stmt = stmt.where(Incidencia.descripcion_incidencia.ilike(f"%{q}%"))
        orden_estacion_id = getattr(params, "orden_estacion_id", None)
        if orden_estacion_id is not None:
            stmt = stmt.where(Incidencia.orden_estacion_id == orden_estacion_id)
        tipo = getattr(params, "tipo_incidencia", None)
        if tipo is not None:
            stmt = stmt.where(Incidencia.tipo_incidencia == TipoIncidencia(tipo).value)
        resolucion = getattr(params, "resolucion", None)
        if resolucion is not None:
            stmt = stmt.where(Incidencia.resolucion == ResolucionIncidencia(resolucion).value)
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class IncidenciaService(BaseService[Incidencia, BaseModel, BaseModel, IncidenciaRead]):
    """Solo lectura por ahora: la generación automática y la resolución manual (ADR-031)
    llegan en la Tanda 5."""

    read_schema = IncidenciaRead
    entidad = "Incidencia"


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_incidencia_service(db: Session = Depends(get_db)) -> IncidenciaService:
    return IncidenciaService(IncidenciaRepository(db, Incidencia))


router = APIRouter(prefix="/incidencias", tags=["ordenes:incidencias"])


@router.get("", response_model=Page[IncidenciaRead])
def listar_incidencias(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Búsqueda de texto en la descripción"),
    orden_estacion_id: uuid.UUID | None = Query(None),
    tipo_incidencia: TipoIncidencia | None = Query(None),
    resolucion: ResolucionIncidencia | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: IncidenciaService = Depends(get_incidencia_service),
) -> Page[IncidenciaRead]:
    return svc.list(
        IncidenciaListParams(
            page=page,
            size=size,
            q=q,
            orden_estacion_id=orden_estacion_id,
            tipo_incidencia=tipo_incidencia,
            resolucion=resolucion,
        )
    )


@router.get("/{item_id}", response_model=IncidenciaRead)
def obtener_incidencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: IncidenciaService = Depends(get_incidencia_service),
) -> IncidenciaRead:
    return svc.get(item_id)
