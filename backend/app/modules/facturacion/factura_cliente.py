"""FacturaCliente (F2) — carátula de la factura al cliente.

El sistema **NUNCA timbra** (ADR-002): PREPARA emisor, receptor, conceptos, totales,
método de pago, cuenta contable y layout; exporta esa información al timbrador externo
(PAC) y REGISTRA lo que el PAC devuelve (folio fiscal, XML, PDF).

Relación 1:1 con `OrdenCliente` (spec): una OC genera como máximo una factura de cliente.
La unicidad se garantiza en el ESQUEMA (`UNIQUE` sobre `orden_id`), no solo en el
servicio — así ninguna vía de escritura futura puede violarla.

Tanda 1 (esta): modelo + migración + API de lectura. La escritura, la máquina de estados
y el handoff con F1 llegan en la Tanda 2; el enum y los CHECK de estado ya se declaran
aquí para no encadenar una migración extra solo por eso.

Dos desviaciones aditivas aprobadas (ver `__init__.py` del módulo): `layout_factura`
como texto libre nullable y `metodo_pago_clave` como texto sin FK formal.
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


class EstadoFacturacion(StrEnum):
    """Máquina de estados propia de la factura (spec + CLAUDE.md §6).

    `preparada` = lista para enviarse al timbrado externo; `timbrada` = se recibió el
    folio fiscal de vuelta. `cobrada` es el estado terminal que **F3 (Cobranza)** hará
    avanzar: F2 lo declara y construirá la transición, pero en F2 nadie la invoca
    (decisión confirmada — no se saca del enum para no encadenar una migración cuando
    llegue F3).
    """

    PREPARADA = "preparada"
    ENVIADA_A_TIMBRADO = "enviada_a_timbrado"
    TIMBRADA = "timbrada"
    ENTREGADA = "entregada"
    COBRADA = "cobrada"
    CANCELADA = "cancelada"


# CHECK del estado derivado del enum: una sola fuente de verdad para el DDL del modelo
# (mismo patrón que `_GRUPOS_SQL` en `catalogos/constantes_sistema.py`).
_ESTADOS_SQL = ", ".join(f"'{e.value}'" for e in EstadoFacturacion)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaCliente(Base):
    __tablename__ = "factura_cliente"
    __table_args__ = (
        # 1:1 con OrdenCliente (spec). En el ESQUEMA, no solo en el servicio.
        UniqueConstraint("orden_id", name="uq_factura_cliente_orden"),
        CheckConstraint(
            f"estado_facturacion IN ({_ESTADOS_SQL})", name="ck_factura_cliente_estado"
        ),
        # Montos: ninguno es legítimamente negativo (mismo criterio que F1).
        CheckConstraint("subtotal_factura >= 0", name="ck_factura_cliente_subtotal"),
        CheckConstraint("iva_factura >= 0", name="ck_factura_cliente_iva"),
        CheckConstraint("total_factura >= 0", name="ck_factura_cliente_total"),
        # ── Invariantes de suma exacta (ADR-039, aplicado desde el día 1 en F2) ──
        # `ROUND(x, 2)` en AMBOS lados, no comparación directa: en SQLite (desarrollo
        # local) `NUMERIC` se almacena como float64, así que sumar dos montos ya
        # redondeados puede diferir por 1 ULP del total guardado por separado. En SQL
        # Server `NUMERIC(14,2)` es de punto fijo real y `ROUND` es un no-op inofensivo.
        # No enmascara una violación real: una diferencia de 1 centavo sigue fallando.
        CheckConstraint(
            "ROUND(total_factura, 2) = ROUND(subtotal_factura + iva_factura, 2)",
            name="ck_factura_cliente_total_suma",
        ),
        # El IVA se deriva del subtotal con la tasa central (`settings.iva_rate`). Aquí
        # se escribe la tasa LITERAL 0.16 de la spec porque un CHECK no puede leer
        # configuración: si la tasa cambiara, este CHECK obliga a una migración
        # explícita — que es justo el aviso que se querría tener.
        CheckConstraint(
            "ROUND(iva_factura, 2) = ROUND(subtotal_factura * 0.16, 2)",
            name="ck_factura_cliente_iva_calculado",
        ),
        CheckConstraint(
            "fecha_fin_transmision >= fecha_inicio_transmision",
            name="ck_factura_cliente_periodo",
        ),
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    numero_factura: Mapped[str] = mapped_column(Unicode(30))
    numero_pedido: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    referencia_adicional: Mapped[str | None] = mapped_column(Unicode(150), default=None)

    orden_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orden_cliente.orden_id", name="fk_factura_cliente_orden", ondelete="NO ACTION")
    )
    # Self-FK (spec): nota de crédito / complemento de una factura previa.
    factura_relacionada_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "factura_cliente.factura_id",
            name="fk_factura_cliente_relacionada",
            ondelete="NO ACTION",
        ),
        default=None,
    )

    # Heredados de la OrdenCliente al preparar (spec: origen "Derivado").
    empresa_facturadora_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "empresa_facturadora.empresa_facturadora_id",
            name="fk_factura_cliente_empresa",
            ondelete="NO ACTION",
        )
    )
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "anunciante.anunciante_id", name="fk_factura_cliente_anunciante", ondelete="NO ACTION"
        )
    )
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agencia.agencia_id", name="fk_factura_cliente_agencia", ondelete="NO ACTION"),
        default=None,
    )
    razon_social_facturacion: Mapped[str] = mapped_column(Unicode(200))
    rfc_facturacion: Mapped[str] = mapped_column(Unicode(13))
    direccion_facturacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)

    descripcion_factura: Mapped[str] = mapped_column(texto_largo())
    observaciones_factura: Mapped[str | None] = mapped_column(texto_largo(), default=None)

    fecha_inicio_transmision: Mapped[date] = mapped_column(fecha_sql())
    fecha_fin_transmision: Mapped[date] = mapped_column(fecha_sql())
    fecha_factura: Mapped[date] = mapped_column(fecha_sql())
    fecha_entrega_factura: Mapped[date | None] = mapped_column(fecha_sql(), default=None)

    # Calculados en el SERVICIO (Tanda 2), nunca aceptados del cliente:
    # iva_factura = subtotal_factura * IVA_RATE; total_factura = subtotal + iva.
    subtotal_factura: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_factura: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    cuenta_contable_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "cuenta_contable.cuenta_contable_id",
            name="fk_factura_cliente_cuenta",
            ondelete="NO ACTION",
        )
    )
    # Desviación aditiva 2: clave de `ConstantesSistema` (grupo MetodoPago), sin FK.
    metodo_pago_clave: Mapped[str] = mapped_column(Unicode(20))
    info_cuenta_pago: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    # Desviación aditiva 1: texto libre nullable, sin catálogo LayoutFactura.
    layout_factura: Mapped[str | None] = mapped_column(Unicode(200), default=None)

    estado_facturacion: Mapped[str] = mapped_column(
        Unicode(30), default=EstadoFacturacion.PREPARADA.value
    )
    # NULL hasta timbrar; los llena la transición a `timbrada` (Tanda 2).
    folio_fiscal_sat: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_timbrado: Mapped[date | None] = mapped_column(fecha_sql(), default=None)
    # Guardan la CLAVE del almacenamiento (S3/local), no una ruta de disco, pese al
    # nombre heredado de la spec — mismo criterio que los `*_ref` de F1 (ADR-042).
    xml_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    pdf_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_factura_cliente_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaClienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_id: uuid.UUID
    numero_factura: str
    numero_pedido: str | None = None
    referencia_adicional: str | None = None
    orden_id: uuid.UUID
    factura_relacionada_id: uuid.UUID | None = None
    empresa_facturadora_id: uuid.UUID
    anunciante_id: uuid.UUID
    agencia_id: uuid.UUID | None = None
    razon_social_facturacion: str
    rfc_facturacion: str
    direccion_facturacion: str | None = None
    descripcion_factura: str
    observaciones_factura: str | None = None
    fecha_inicio_transmision: date
    fecha_fin_transmision: date
    fecha_factura: date
    fecha_entrega_factura: date | None = None
    subtotal_factura: Decimal
    iva_factura: Decimal
    total_factura: Decimal
    cuenta_contable_id: uuid.UUID
    metodo_pago_clave: str
    info_cuenta_pago: str | None = None
    layout_factura: str | None = None
    estado_facturacion: str
    folio_fiscal_sat: str | None = None
    fecha_timbrado: date | None = None
    xml_path: str | None = None
    pdf_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class FacturaClienteListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo` pero NUNCA se expone como query
    param: `FacturaCliente` no tiene baja lógica (mismo criterio que F1, ADR-035). Se
    hereda solo por compatibilidad de tipo con `BaseRepository`/`BaseService`."""

    orden_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    empresa_facturadora_id: uuid.UUID | None = None
    estado_facturacion: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaClienteRepository(BaseRepository[FacturaCliente]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`, columna
        # que esta entidad no tiene.
        for campo in ("orden_id", "anunciante_id", "agencia_id", "empresa_facturadora_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(FacturaCliente, campo) == valor)
        estado = getattr(params, "estado_facturacion", None)
        if estado is not None:
            stmt = stmt.where(FacturaCliente.estado_facturacion == estado)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(
                FacturaCliente.numero_factura.ilike(patron)
                | FacturaCliente.razon_social_facturacion.ilike(patron)
                | FacturaCliente.folio_fiscal_sat.ilike(patron)
            )
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaClienteService(BaseService[FacturaCliente, BaseModel, BaseModel, FacturaClienteRead]):
    """Tanda 1: solo lectura. La captura (con la precondición `orden_cerrada`), la
    máquina de estados y el handoff `timbrada → OrdenCliente.facturada` llegan en la
    Tanda 2."""

    read_schema = FacturaClienteRead
    entidad = "FacturaCliente"


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_cliente_service(db: Session = Depends(get_db)) -> FacturaClienteService:
    return FacturaClienteService(FacturaClienteRepository(db, FacturaCliente))


router_clientes = APIRouter(prefix="/clientes", tags=["facturacion:clientes"])


@router_clientes.get("", response_model=Page[FacturaClienteRead])
def listar_facturas_cliente(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(
        None, description="Busca en número de factura, razón social y folio fiscal"
    ),
    orden_id: uuid.UUID | None = Query(None),
    anunciante_id: uuid.UUID | None = Query(None),
    agencia_id: uuid.UUID | None = Query(None),
    empresa_facturadora_id: uuid.UUID | None = Query(None),
    estado_facturacion: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:leer")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> Page[FacturaClienteRead]:
    return svc.list(
        FacturaClienteListParams(
            page=page,
            size=size,
            q=q,
            orden_id=orden_id,
            anunciante_id=anunciante_id,
            agencia_id=agencia_id,
            empresa_facturadora_id=empresa_facturadora_id,
            estado_facturacion=estado_facturacion,
        )
    )


@router_clientes.get("/{item_id}", response_model=FacturaClienteRead)
def obtener_factura_cliente(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:leer")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    return svc.get(item_id)
