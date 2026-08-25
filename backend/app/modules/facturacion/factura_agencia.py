"""FacturaAgencia (F2) — factura que OIR RECIBE de la agencia por su comisión.

Igual que `FacturaAfiliado`, es un COSTO y lo captura **CxP** (permiso `costos:*`).

Diferencia clave con `FacturaCliente`: la relación con `OrdenCliente` es **1:N** — una
misma OC puede tener varias facturas de agencia. Por eso `orden_id` NO lleva `UNIQUE`
aquí, a diferencia de `factura_cliente.orden_id`.

`comision_agencia = OrdenCliente.total * porcentaje_comision_agencia / 100` (spec). El
porcentaje se SUGIERE desde el catálogo Agencia pero es editable por operación, así que
se persiste en la factura: si el catálogo cambia después, esta factura conserva el que
se pactó. No lleva CHECK de igualdad contra la OC porque un CHECK no puede leer otra
tabla; la fórmula se valida en el servicio (Tanda 2) y en las pruebas.

`updated_at` es ADITIVO (la spec solo pide `created_at`) — ver `factura_afiliado.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db
from app.core.security import CurrentUser, requiere_permiso
from app.modules.facturacion.factura_afiliado import (
    _ESTATUS_PROVEEDOR_SQL,
    EstatusFacturaProveedor,
)
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaAgencia(Base):
    __tablename__ = "factura_agencia"
    __table_args__ = (
        CheckConstraint(
            f"estatus_factura_agencia IN ({_ESTATUS_PROVEEDOR_SQL})",
            name="ck_factura_agencia_estatus",
        ),
        CheckConstraint("monto_factura_agencia >= 0", name="ck_factura_agencia_monto"),
        CheckConstraint("iva_factura_agencia >= 0", name="ck_factura_agencia_iva"),
        CheckConstraint("total_factura_agencia >= 0", name="ck_factura_agencia_total"),
        CheckConstraint("comision_agencia >= 0", name="ck_factura_agencia_comision"),
        CheckConstraint(
            "porcentaje_comision_agencia >= 0 AND porcentaje_comision_agencia <= 100",
            name="ck_factura_agencia_pct_comision",
        ),
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039): ver la
        # explicación completa en `factura_cliente.py`. Como en FacturaAfiliado, el IVA
        # es CAPTURADO (spec: "Manual"), así que no se le impone la tasa del 16%.
        CheckConstraint(
            "ROUND(total_factura_agencia, 2) = "
            "ROUND(monto_factura_agencia + iva_factura_agencia, 2)",
            name="ck_factura_agencia_total_suma",
        ),
    )

    factura_agencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    agencia_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agencia.agencia_id", name="fk_factura_agencia_agencia", ondelete="NO ACTION")
    )
    # 1:N (a diferencia de FacturaCliente): SIN UniqueConstraint sobre orden_id.
    orden_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orden_cliente.orden_id", name="fk_factura_agencia_orden", ondelete="NO ACTION")
    )
    folio_factura_agencia: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_factura_agencia: Mapped[date] = mapped_column(fecha_sql())

    monto_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Calculado en el servicio: monto + iva.
    total_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # Sugerido desde el catálogo Agencia, editable por operación (spec: "Cat/Manual").
    porcentaje_comision_agencia: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    # Calculado en el servicio: OrdenCliente.total * porcentaje / 100.
    comision_agencia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_agencia: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_factura_agencia_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver `factura_afiliado.py`.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaAgenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_agencia_id: uuid.UUID
    agencia_id: uuid.UUID
    orden_id: uuid.UUID
    folio_factura_agencia: str | None = None
    fecha_factura_agencia: date
    monto_factura_agencia: Decimal
    iva_factura_agencia: Decimal
    total_factura_agencia: Decimal
    porcentaje_comision_agencia: Decimal | None = None
    comision_agencia: Decimal | None = None
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    estatus_factura_agencia: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class FacturaAgenciaListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    agencia_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    estatus_factura_agencia: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaAgenciaRepository(BaseRepository[FacturaAgencia]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        for campo in ("agencia_id", "orden_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(FacturaAgencia, campo) == valor)
        estatus = getattr(params, "estatus_factura_agencia", None)
        if estatus is not None:
            stmt = stmt.where(FacturaAgencia.estatus_factura_agencia == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(FacturaAgencia.folio_factura_agencia.ilike(patron))
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaAgenciaService(BaseService[FacturaAgencia, BaseModel, BaseModel, FacturaAgenciaRead]):
    """Tanda 1: solo lectura. Captura, cálculo de la comisión, máquina de estados y
    autorización de Dirección/Admin llegan en la Tanda 2."""

    read_schema = FacturaAgenciaRead
    entidad = "FacturaAgencia"


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_agencia_service(db: Session = Depends(get_db)) -> FacturaAgenciaService:
    return FacturaAgenciaService(FacturaAgenciaRepository(db, FacturaAgencia))


router_agencias = APIRouter(prefix="/agencias", tags=["facturacion:agencias"])


@router_agencias.get("", response_model=Page[FacturaAgenciaRead])
def listar_facturas_agencia(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en el folio externo de la agencia"),
    agencia_id: uuid.UUID | None = Query(None),
    orden_id: uuid.UUID | None = Query(None),
    estatus_factura_agencia: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> Page[FacturaAgenciaRead]:
    return svc.list(
        FacturaAgenciaListParams(
            page=page,
            size=size,
            q=q,
            agencia_id=agencia_id,
            orden_id=orden_id,
            estatus_factura_agencia=estatus_factura_agencia,
        )
    )


@router_agencias.get("/{item_id}", response_model=FacturaAgenciaRead)
def obtener_factura_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    return svc.get(item_id)
