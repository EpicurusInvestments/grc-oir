"""FacturaAfiliado + FacturaAfiliadoOrden (F2) — factura que OIR RECIBE del afiliado.

Es un COSTO, no un ingreso: la emisora factura a OIR por los servicios de transmisión.
La captura es de **CxP** (no de Facturación — ver la matriz de la ficha), por eso su
permiso es `costos:*` y no `facturacion:*`.

`FacturaAfiliadoOrden` es la tabla N:M que reparte el costo de UNA factura entre varias
`OrdenEstacion` **cerradas**. Vive en este archivo, junto a su padre, con el mismo
criterio que `OrdenEstacionDia` vive dentro de `orden_estacion.py` en F1.

La validación de que la OE esté `cerrada` es una regla de NEGOCIO: se implementa en el
servicio (Tanda 2), no en el esquema — un CHECK no puede leer otra tabla, y una FK no
puede condicionarse a un estado.

`updated_at` es ADITIVO: la spec solo pide `created_at` para esta entidad, pero el
CLAUDE.md §6 lo exige en toda entidad y F1 ya sentó el precedente (se agregó a las tres
entidades de F1 que la spec tampoco lo pedía). Decisión confirmada para F2.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


class EstatusFacturaProveedor(StrEnum):
    """Estados de las facturas que OIR RECIBE (spec: mismos 4 valores para afiliado y
    agencia). Se define UNA vez aquí y `factura_agencia.py` lo importa — mismo criterio
    que `EstatusOrden`, definido en `orden_cliente.py` y reutilizado por
    `orden_estacion.py` en F1.

    `en_revision → autorizada` NO lo ejecuta quien capturó: es de Dirección/Admin
    (regla de área explícita en el servicio, Tanda 2 — mismo patrón que el canal de
    comisiones de F1, que tampoco se resuelve con la matriz RBAC de módulo).
    """

    RECIBIDA = "recibida"
    EN_REVISION = "en_revision"
    AUTORIZADA = "autorizada"
    PAGADA = "pagada"


_ESTATUS_PROVEEDOR_SQL = ", ".join(f"'{e.value}'" for e in EstatusFacturaProveedor)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaAfiliado(Base):
    __tablename__ = "factura_afiliado"
    __table_args__ = (
        CheckConstraint(
            f"estatus_factura_afiliado IN ({_ESTATUS_PROVEEDOR_SQL})",
            name="ck_factura_afiliado_estatus",
        ),
        CheckConstraint("monto_factura_afiliado >= 0", name="ck_factura_afiliado_monto"),
        CheckConstraint("iva_factura_afiliado >= 0", name="ck_factura_afiliado_iva"),
        CheckConstraint("total_factura_afiliado >= 0", name="ck_factura_afiliado_total"),
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039): ver la
        # explicación completa en `factura_cliente.py`. Aquí el IVA es CAPTURADO (la
        # spec lo marca "Manual": la factura del afiliado puede traer un IVA que no sea
        # exactamente el 16% — retenciones, exentos), así que NO se agrega un CHECK
        # `iva = monto * 0.16` como sí lo lleva FacturaCliente.
        CheckConstraint(
            "ROUND(total_factura_afiliado, 2) = "
            "ROUND(monto_factura_afiliado + iva_factura_afiliado, 2)",
            name="ck_factura_afiliado_total_suma",
        ),
    )

    factura_afiliado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    afiliado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "afiliado.afiliado_id", name="fk_factura_afiliado_afiliado", ondelete="NO ACTION"
        )
    )
    # Heredado del catálogo Afiliado al capturar (spec: origen "Derivado").
    razon_social_afiliada: Mapped[str | None] = mapped_column(Unicode(200), default=None)
    factura_emisora: Mapped[str] = mapped_column(Unicode(50))
    fecha_factura_afiliado: Mapped[date] = mapped_column(fecha_sql())

    monto_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Calculado en el servicio: monto + iva.
    total_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_afiliado: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "usuario.usuario_id", name="fk_factura_afiliado_created_by", ondelete="NO ACTION"
        )
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver docstring del módulo.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class FacturaAfiliadoOrden(Base):
    """Reparto del costo de una factura de afiliado entre varias OrdenEstacion cerradas."""

    __tablename__ = "factura_afiliado_orden"
    __table_args__ = (
        # Una OE no puede asignarse dos veces a la MISMA factura (el reparto sería
        # ambiguo). Sí puede aparecer en facturas distintas: la spec no lo prohíbe y el
        # negocio lo permite (una emisora puede facturar en parcialidades).
        UniqueConstraint(
            "factura_afiliado_id",
            "orden_estacion_id",
            name="uq_factura_afiliado_orden_factura_oe",
        ),
        CheckConstraint("monto_asignado >= 0", name="ck_factura_afiliado_orden_monto"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    factura_afiliado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "factura_afiliado.factura_afiliado_id",
            name="fk_factura_afiliado_orden_factura",
            ondelete="NO ACTION",
        )
    )
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_factura_afiliado_orden_oe",
            ondelete="NO ACTION",
        )
    )
    monto_asignado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notas_asignacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaAfiliadoOrdenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_afiliado_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    monto_asignado: Decimal
    notas_asignacion: str | None = None


class FacturaAfiliadoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_afiliado_id: uuid.UUID
    afiliado_id: uuid.UUID
    razon_social_afiliada: str | None = None
    factura_emisora: str
    fecha_factura_afiliado: date
    monto_factura_afiliado: Decimal
    iva_factura_afiliado: Decimal
    total_factura_afiliado: Decimal
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    estatus_factura_afiliado: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class FacturaAfiliadoListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    afiliado_id: uuid.UUID | None = None
    estatus_factura_afiliado: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaAfiliadoRepository(BaseRepository[FacturaAfiliado]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        afiliado_id = getattr(params, "afiliado_id", None)
        if afiliado_id is not None:
            stmt = stmt.where(FacturaAfiliado.afiliado_id == afiliado_id)
        estatus = getattr(params, "estatus_factura_afiliado", None)
        if estatus is not None:
            stmt = stmt.where(FacturaAfiliado.estatus_factura_afiliado == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(
                FacturaAfiliado.factura_emisora.ilike(patron)
                | FacturaAfiliado.razon_social_afiliada.ilike(patron)
            )
        return stmt

    def listar_asignaciones(self, factura_afiliado_id: uuid.UUID) -> list[FacturaAfiliadoOrden]:
        from sqlalchemy import select

        return list(
            self.db.scalars(
                select(FacturaAfiliadoOrden)
                .where(FacturaAfiliadoOrden.factura_afiliado_id == factura_afiliado_id)
                .order_by(FacturaAfiliadoOrden.id)
            ).all()
        )


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaAfiliadoService(
    BaseService[FacturaAfiliado, BaseModel, BaseModel, FacturaAfiliadoRead]
):
    """Tanda 1: solo lectura. Captura, máquina de estados, autorización de
    Dirección/Admin y asignación a OE cerradas llegan en la Tanda 2."""

    read_schema = FacturaAfiliadoRead
    entidad = "FacturaAfiliado"

    def __init__(self, repo: FacturaAfiliadoRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def asignaciones(self, factura_afiliado_id: uuid.UUID) -> list[FacturaAfiliadoOrdenRead]:
        self._get_or_404(factura_afiliado_id)
        return [
            FacturaAfiliadoOrdenRead.model_validate(a)
            for a in self._repo.listar_asignaciones(factura_afiliado_id)
        ]


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_afiliado_service(db: Session = Depends(get_db)) -> FacturaAfiliadoService:
    return FacturaAfiliadoService(FacturaAfiliadoRepository(db, FacturaAfiliado))


router_afiliados = APIRouter(prefix="/afiliados", tags=["facturacion:afiliados"])


@router_afiliados.get("", response_model=Page[FacturaAfiliadoRead])
def listar_facturas_afiliado(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en folio de la emisora y razón social"),
    afiliado_id: uuid.UUID | None = Query(None),
    estatus_factura_afiliado: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> Page[FacturaAfiliadoRead]:
    return svc.list(
        FacturaAfiliadoListParams(
            page=page,
            size=size,
            q=q,
            afiliado_id=afiliado_id,
            estatus_factura_afiliado=estatus_factura_afiliado,
        )
    )


@router_afiliados.get("/{item_id}", response_model=FacturaAfiliadoRead)
def obtener_factura_afiliado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    return svc.get(item_id)


@router_afiliados.get("/{item_id}/ordenes", response_model=list[FacturaAfiliadoOrdenRead])
def listar_asignaciones_factura_afiliado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> list[FacturaAfiliadoOrdenRead]:
    """Reparto de esta factura entre las OrdenEstacion a las que se asignó."""
    return svc.asignaciones(item_id)
