"""CostoAdicional (F2) — costos de nómina (formato NOI) y overhead libre.

Alimentan el Estado de Resultados de F4. Captura de **CxP** (permiso `costos:*`).

Sin máquina de estados: es un registro simple (la spec no le define ningún ENUM de
estatus, solo el `tipo_costo`).

`orden_id` es NULLABLE a propósito (spec): NULL = costo general del área, no ligado a
una venta concreta. Los costos con `orden_id` sí se imputan a una OrdenCliente.

`updated_at` es ADITIVO (la spec solo pide `created_at`) — ver `factura_afiliado.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


class TipoCosto(StrEnum):
    """`nomina` llega por carga del archivo NOI (integración de F2/F4); `overhead` es
    captura libre. Spec: origen "Catálogo" con estos dos valores fijos."""

    NOMINA = "nomina"
    OVERHEAD = "overhead"


_TIPOS_COSTO_SQL = ", ".join(f"'{t.value}'" for t in TipoCosto)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class CostoAdicional(Base):
    __tablename__ = "costo_adicional"
    __table_args__ = (
        CheckConstraint(f"tipo_costo IN ({_TIPOS_COSTO_SQL})", name="ck_costo_adicional_tipo"),
        CheckConstraint("monto_costo >= 0", name="ck_costo_adicional_monto"),
        # `periodo_contable` es VARCHAR(7) con formato YYYY-MM (spec).
        #
        # TRAMPA DE DIALECTO (misma clase que ADR-014 y ADR-036, encontrada por la prueba
        # `test_periodo_contable_*`): el patrón natural
        # `LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]'` es sintaxis de T-SQL y **SQLite no
        # soporta clases de caracteres en LIKE** — ahí `[0-9]` se compara literalmente y
        # el CHECK rechaza TODOS los valores, incluido el válido '2026-02' (verificado).
        # Habría pasado la revisión del DDL de SQL Server y roto todo el desarrollo local.
        #
        # Se usa `'____-__'`: el comodín de un carácter `_` sí es estándar en AMBOS
        # motores. Garantiza la FORMA (7 caracteres con guion en la 5ª posición: rechaza
        # 'feb-2026' y '2026-2'), pero no que sean dígitos — eso lo valida el schema
        # Pydantic en la captura (Tanda 2). Es la garantía más fuerte que se puede
        # expresar de forma portable en una constraint.
        CheckConstraint(
            "periodo_contable LIKE '____-__'",
            name="ck_costo_adicional_periodo",
        ),
    )

    costo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    tipo_costo: Mapped[str] = mapped_column(Unicode(20))
    # NULL = costo general, no ligado a una venta (spec).
    orden_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orden_cliente.orden_id", name="fk_costo_adicional_orden", ondelete="NO ACTION"),
        default=None,
    )
    descripcion_costo: Mapped[str] = mapped_column(Unicode(300))
    periodo_contable: Mapped[str] = mapped_column(Unicode(7))
    monto_costo: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_costo_adicional_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver `factura_afiliado.py`.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class CostoAdicionalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    costo_id: uuid.UUID
    tipo_costo: str
    orden_id: uuid.UUID | None = None
    descripcion_costo: str
    periodo_contable: str
    monto_costo: Decimal
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class CostoAdicionalListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    tipo_costo: str | None = None
    orden_id: uuid.UUID | None = None
    periodo_contable: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class CostoAdicionalRepository(BaseRepository[CostoAdicional]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        for campo in ("tipo_costo", "orden_id", "periodo_contable"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(CostoAdicional, campo) == valor)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(CostoAdicional.descripcion_costo.ilike(patron))
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class CostoAdicionalService(BaseService[CostoAdicional, BaseModel, BaseModel, CostoAdicionalRead]):
    """Tanda 1: solo lectura. La captura por CxP llega en la Tanda 2."""

    read_schema = CostoAdicionalRead
    entidad = "CostoAdicional"


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_costo_adicional_service(db: Session = Depends(get_db)) -> CostoAdicionalService:
    return CostoAdicionalService(CostoAdicionalRepository(db, CostoAdicional))


router_costos = APIRouter(prefix="/costos", tags=["facturacion:costos"])


@router_costos.get("", response_model=Page[CostoAdicionalRead])
def listar_costos_adicionales(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en la descripción del costo"),
    tipo_costo: str | None = Query(None, description="nomina | overhead"),
    orden_id: uuid.UUID | None = Query(None),
    periodo_contable: str | None = Query(None, description="YYYY-MM"),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: CostoAdicionalService = Depends(get_costo_adicional_service),
) -> Page[CostoAdicionalRead]:
    return svc.list(
        CostoAdicionalListParams(
            page=page,
            size=size,
            q=q,
            tipo_costo=tipo_costo,
            orden_id=orden_id,
            periodo_contable=periodo_contable,
        )
    )


@router_costos.get("/{item_id}", response_model=CostoAdicionalRead)
def obtener_costo_adicional(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: CostoAdicionalService = Depends(get_costo_adicional_service),
) -> CostoAdicionalRead:
    return svc.get(item_id)
