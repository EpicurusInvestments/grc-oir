"""FacturaCliente (F2) — carátula de la factura al cliente.

El sistema **NUNCA timbra** (ADR-002): PREPARA emisor, receptor, conceptos, totales,
método de pago, cuenta contable y layout; exporta esa información al timbrador externo
(PAC) y REGISTRA lo que el PAC devuelve (folio fiscal, XML, PDF).

Relación 1:1 con `OrdenCliente` (spec): una OC tiene como máximo una factura VIGENTE. La
unicidad se garantiza en el ESQUEMA con un índice único FILTRADO que excluye las
canceladas (ADR-047), no solo en el servicio — así ninguna vía de escritura futura puede
violarla, y a la vez una OC cuya factura se canceló puede volver a facturarse.

Dos desviaciones aditivas aprobadas (ver `__init__.py` del módulo): `layout_factura`
como texto libre nullable y `metodo_pago_clave` como texto sin FK formal.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Unicode,
    Uuid,
    case,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import ConflictError, DomainError, StateTransitionError
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.timbrado import DatosTimbrado, DomicilioFiscal, get_timbrado_export
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

# Mismos helpers de dinero que F1 (`orden_cliente.py`): `Decimal` cuantizado a centavos y
# la tasa de IVA desde configuración central, nunca repetida como literal en el código.
CENTAVOS = Decimal("0.01")
IVA_RATE = Decimal(str(settings.iva_rate))


def _receptor_de(oc: Any) -> tuple[str, uuid.UUID]:
    """Quién recibe el CFDI de esta orden: el anunciante o la agencia (spec).

    Se devuelve como par comparable —(tipo, id)— para poder exigir que todas las órdenes de
    una factura múltiple coincidan. No basta con comparar `agencia_id`: dos órdenes de la
    misma agencia pueden diferir en `facturacion_directa_cliente`, y entonces una se factura
    al anunciante y la otra a la agencia.
    """
    if oc.facturacion_directa_cliente or oc.agencia_id is None:
        return ("anunciante", oc.anunciante_id)
    return ("agencia", oc.agencia_id)


def _tiene_factura_vigente(orden_id: Any) -> Any:
    """Subconsulta `EXISTS`: ¿esta orden está en alguna factura NO cancelada?

    Es la regla que dejó de poder expresar el esquema al pasar a N:M (ADR-064). La usan la
    bandeja y el combo de anunciantes; el alta hace la consulta equivalente pero devolviendo
    ADEMÁS qué factura ocupa cada orden, para poder nombrarla en el 409. Las tres deben
    ignorar las canceladas (ADR-047): si una las contara y otra no, una orden aparecería en
    la bandeja y sería rechazada al facturarla.
    """
    return (
        select(FacturaClienteOrden.orden_id)
        .join(
            FacturaCliente, FacturaCliente.factura_id == FacturaClienteOrden.factura_id
        )
        .where(
            FacturaClienteOrden.orden_id == orden_id,
            FacturaCliente.estado_facturacion != EstadoFacturacion.CANCELADA.value,
        )
        .exists()
    )


def _producto_comun(ordenes: list[Any]) -> str | None:
    """Producto de las órdenes si TODAS coinciden; `None` si difieren o no hay ninguno."""
    productos = {o.producto for o in ordenes if o.producto}
    return productos.pop() if len(productos) == 1 else None


def _serie_desde_numero(numero_factura: str) -> str | None:
    """`IdDoc.Serie` del PAC (ADR-060 bis): la letra/prefijo ANTES del guion en el propio
    número de factura ("A-0010890" → "A"), no una constante aparte que mantener — las
    facturas reales ya siguen esa convención. `None` si el número no trae guion (se
    reporta como faltante igual que antes)."""
    prefijo, guion, _resto = numero_factura.partition("-")
    return prefijo.strip() or None if guion else None


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaCliente(Base):
    __tablename__ = "factura_cliente"
    __table_args__ = (
        # La relación con OrdenCliente vive en `factura_cliente_orden` (N:M, ADR-064),
        # NO en una columna de esta tabla. Con ella se fue el índice único filtrado
        # `uq_factura_cliente_orden_vigente` que garantizaba "una OC no puede tener dos
        # facturas vigentes": esa regla no es expresable en la tabla puente, porque
        # `estado_facturacion` vive AQUÍ. Ahora la valida el servicio con un 409 que
        # nombra las órdenes en conflicto — consecuencia aceptada al autorizar la
        # desviación, y la razón por la que ese chequeo tiene pruebas propias.
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

    # Heredados de la OrdenCliente al preparar (spec: origen "Derivado").
    empresa_facturadora_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "empresa_facturadora.empresa_facturadora_id",
            name="fk_factura_cliente_empresa",
            ondelete="NO ACTION",
        )
    )
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "anunciante.anunciante_id", name="fk_factura_cliente_anunciante", ondelete="NO ACTION"
        )
    )
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
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
        Uuid(),
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
    # Serie/número del certificado de sello digital (CSD) del PAC — dato que a veces
    # devuelve el timbrador junto al folio fiscal, sin normativa fija de formato (ADR-051).
    serie_timbrado: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    # Guardan la CLAVE del almacenamiento (S3/local), no una ruta de disco, pese al
    # nombre heredado de la spec — mismo criterio que los `*_ref` de F1 (ADR-042).
    xml_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    pdf_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("usuario.usuario_id", name="fk_factura_cliente_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class FacturaClienteRelacionada(Base):
    """Relación N:N entre facturas del mismo anunciante (ADR-062).

    Reemplaza el self-FK único que tenía la spec: la pantalla de "Nueva factura" necesita
    marcar VARIAS facturas relacionadas (control de sustituciones/canceladas del cliente),
    y CFDI 4.0 soporta varios `CfdiRelacionado` bajo un mismo `TipoRelacion` — el PAC recibe
    una fila por cada una (ver `_relacionados()` en el adaptador V40).
    """

    __tablename__ = "factura_cliente_relacionada"
    __table_args__ = (
        CheckConstraint(
            "factura_id <> relacionada_id", name="ck_factura_cliente_relacionada_distinta"
        ),
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_cliente.factura_id", name="fk_fc_relacionada_factura", ondelete="NO ACTION"
        ),
        primary_key=True,
    )
    relacionada_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_cliente.factura_id",
            name="fk_fc_relacionada_relacionada",
            ondelete="NO ACTION",
        ),
        primary_key=True,
    )


class FacturaClienteOrden(Base):
    """Órdenes que cubre una factura al cliente — N:M (ADR-064).

    La spec BD v2 define `OrdenCliente → FacturaCliente` como 1:1 y lo resolvía con
    `factura_cliente.orden_id`. El equipo autorizó la desviación para poder emitir UNA
    factura que cubra VARIAS órdenes cerradas del mismo anunciante (facturación múltiple).

    Sin columna de monto, a diferencia de `FacturaAfiliadoOrden`: allá la factura del
    proveedor se REPARTE entre órdenes y hace falta saber cuánto toca a cada una; aquí
    cada orden aporta su subtotal íntegro, así que guardarlo sería duplicar un dato que ya
    vive en `orden_cliente.subtotal` y que podría quedar desincronizado.

    El índice sobre `orden_id` NO es decorativo: la bandeja "Listas para facturar" hace
    LEFT JOIN por esa columna contra todas las órdenes cerradas en cada carga.
    """

    __tablename__ = "factura_cliente_orden"
    __table_args__ = (Index("ix_factura_cliente_orden_orden", "orden_id"),)

    factura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_cliente.factura_id", name="fk_fc_orden_factura", ondelete="NO ACTION"
        ),
        primary_key=True,
    )
    orden_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("orden_cliente.orden_id", name="fk_fc_orden_orden", ondelete="NO ACTION"),
        primary_key=True,
    )


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class OrdenDeFactura(BaseModel):
    """Una de las órdenes que cubre la factura (ADR-064).

    Trae ya resueltos folio, periodo y subtotal para que la sección "Órdenes de esta
    factura" del panel de detalle no dispare una consulta por renglón.
    """

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    fecha_inicio_campania: date
    fecha_fin_campania: date
    subtotal: Decimal


class FacturaClienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_id: uuid.UUID
    numero_factura: str
    numero_pedido: str | None = None
    referencia_adicional: str | None = None
    # Órdenes que cubre la factura (ADR-064). Ya NO son columnas de la tabla: las rellena
    # `_aplicar_ordenes` desde `factura_cliente_orden`, por eso nada de esto lo encuentra
    # `from_attributes`.
    ordenes: list[OrdenDeFactura] = Field(default_factory=list)
    # Escalares de la PRIMERA orden (por folio). Se conservan porque la lista y el panel
    # los muestran como identificador corto de la factura; con varias órdenes la UI
    # completa con "+N" a partir de `ordenes`.
    orden_id: uuid.UUID | None = None
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
    serie_timbrado: str | None = None
    xml_path: str | None = None
    pdf_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    #: Nombre de la empresa emisora, DENORMALIZADO para la lista (la pantalla aprobada lo
    #: muestra como columna). Lo resuelve el servicio en una sola consulta por página; no
    #: es una columna de la tabla ni una relación del ORM, para no arrastrar un N+1.
    empresa_facturadora: str | None = None
    #: Folio de la OrdenCliente asociada, DENORMALIZADO para el badge del header del
    #: detalle (ADR-055) — mismo criterio que `empresa_facturadora`: se resuelve en el
    #: servicio, en una sola consulta por página, no es columna ni relación del ORM.
    folio_orden: str | None = None
    #: IDs de las facturas relacionadas (ADR-062: N:N, no columna de esta tabla). Se
    #: resuelve en el servicio con el mismo patrón por lote que `empresa_facturadora`.
    facturas_relacionadas_ids: list[uuid.UUID] = Field(default_factory=list)


class FacturaClienteListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo` pero NUNCA se expone como query
    param: `FacturaCliente` no tiene baja lógica (mismo criterio que F1, ADR-035). Se
    hereda solo por compatibilidad de tipo con `BaseRepository`/`BaseService`."""

    orden_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    empresa_facturadora_id: uuid.UUID | None = None
    estado_facturacion: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# Tanda 2 — escritura, máquina de estados y handoff con F1
# ══════════════════════════════════════════════════════════════════════════════

# Transiciones permitidas. Fuente única: el servicio NO decide con `if` sueltos.
# `cobrada` es alcanzable desde `entregada`, pero en F2 NADIE la dispara: es de F3
# (decisión confirmada — la transición existe, el disparador no).
TRANSICIONES: dict[str, set[str]] = {
    EstadoFacturacion.PREPARADA.value: {
        EstadoFacturacion.ENVIADA_A_TIMBRADO.value,
        EstadoFacturacion.CANCELADA.value,
    },
    EstadoFacturacion.ENVIADA_A_TIMBRADO.value: {
        EstadoFacturacion.TIMBRADA.value,
        EstadoFacturacion.CANCELADA.value,
    },
    EstadoFacturacion.TIMBRADA.value: {
        EstadoFacturacion.ENTREGADA.value,
        EstadoFacturacion.CANCELADA.value,
    },
    EstadoFacturacion.ENTREGADA.value: {
        EstadoFacturacion.COBRADA.value,  # la dispara F3, no F2
        EstadoFacturacion.CANCELADA.value,
    },
    EstadoFacturacion.COBRADA.value: set(),  # terminal
    EstadoFacturacion.CANCELADA.value: set(),  # terminal
}


class FacturaClienteCreate(BaseModel):
    """Lo que Facturación CAPTURA. Todo lo demás se hereda de la OrdenCliente o se
    calcula en el servicio: los campos derivados y calculados NO se aceptan del cliente
    (regla del `backend/CLAUDE.md`), por eso `extra="forbid"`."""

    model_config = ConfigDict(extra="forbid")

    # Órdenes que cubrirá la factura (ADR-064). Una sola = el flujo de siempre; varias =
    # facturación múltiple. El servicio exige que compartan emisora y receptor, porque un
    # CFDI tiene un único emisor y un único receptor.
    ordenes_ids: list[uuid.UUID] = Field(min_length=1)
    numero_factura: str = Field(min_length=1, max_length=30)
    # Receptor: se DERIVA de la orden, pero la pantalla aprobada lo muestra editable
    # (etiqueta "EDITABLE" en el panel de detalle). Si vienen, mandan sobre lo derivado;
    # si no, el servicio los resuelve como siempre. Los IMPORTES no son negociables por
    # esta vía: `subtotal` se hereda y el IVA y el total se calculan.
    razon_social_facturacion: str | None = Field(default=None, max_length=200)
    rfc_facturacion: str | None = Field(default=None, max_length=13)
    direccion_facturacion: str | None = None
    numero_pedido: str | None = Field(default=None, max_length=50)
    referencia_adicional: str | None = Field(default=None, max_length=150)
    #: N:N (ADR-062): facturas del mismo anunciante que esta factura marca como
    #: relacionadas (sustitución/control de canceladas). El servicio valida que existan.
    facturas_relacionadas_ids: list[uuid.UUID] = Field(default_factory=list)
    descripcion_factura: str = Field(min_length=1)
    observaciones_factura: str | None = None
    fecha_factura: date
    cuenta_contable_id: uuid.UUID
    # Clave de `ConstantesSistema` (grupo MetodoPago). Sin FK: el frontend sugiere desde
    # el catálogo, pero la base no valida la relación (desviación aditiva 2).
    metodo_pago_clave: str = Field(min_length=1, max_length=20)
    info_cuenta_pago: str | None = None
    layout_factura: str | None = Field(default=None, max_length=200)


class FacturaClienteUpdate(BaseModel):
    """Edición de los campos capturables. Los heredados y los calculados no se tocan
    aquí: para cambiarlos habría que re-derivarlos de la OC, que es otra operación."""

    model_config = ConfigDict(extra="forbid")

    numero_factura: str | None = Field(default=None, min_length=1, max_length=30)
    numero_pedido: str | None = Field(default=None, max_length=50)
    referencia_adicional: str | None = Field(default=None, max_length=150)
    descripcion_factura: str | None = Field(default=None, min_length=1)
    observaciones_factura: str | None = None
    fecha_factura: date | None = None
    cuenta_contable_id: uuid.UUID | None = None
    metodo_pago_clave: str | None = Field(default=None, min_length=1, max_length=20)
    info_cuenta_pago: str | None = None
    layout_factura: str | None = Field(default=None, max_length=200)


class TimbrarIn(BaseModel):
    """Datos que DEVUELVE el timbrador externo. El sistema no los genera (ADR-002)."""

    model_config = ConfigDict(extra="forbid")

    folio_fiscal_sat: str = Field(min_length=1, max_length=50)
    fecha_timbrado: date
    serie_timbrado: str | None = Field(default=None, max_length=50)
    # Claves de almacenamiento devueltas por el endpoint de adjuntos (no rutas de disco).
    xml_path: str | None = Field(default=None, max_length=500)
    pdf_path: str | None = Field(default=None, max_length=500)


class EntregarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_entrega_factura: date | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaClienteRepository(BaseRepository[FacturaCliente]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`, columna
        # que esta entidad no tiene.
        for campo in ("anunciante_id", "agencia_id", "empresa_facturadora_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(FacturaCliente, campo) == valor)
        # `orden_id` ya no es columna de esta tabla (ADR-064): se filtra por existencia en
        # la puente. `EXISTS` y no `JOIN` para no duplicar filas cuando la factura cubre
        # varias órdenes — con JOIN, una factura de 3 órdenes saldría 3 veces.
        orden_id = getattr(params, "orden_id", None)
        if orden_id is not None:
            stmt = stmt.where(
                select(FacturaClienteOrden.factura_id)
                .where(
                    FacturaClienteOrden.factura_id == FacturaCliente.factura_id,
                    FacturaClienteOrden.orden_id == orden_id,
                )
                .exists()
            )
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
class FacturaClienteService(
    BaseService[FacturaCliente, FacturaClienteCreate, FacturaClienteUpdate, FacturaClienteRead]
):
    """Captura, máquina de estados y handoff con F1.

    Las 4 transiciones son métodos dedicados (no un `PATCH estado` genérico), igual que
    en F1: cada una tiene su propia regla y su propio payload.
    """

    read_schema = FacturaClienteRead
    entidad = "FacturaCliente"

    def __init__(self, repo: FacturaClienteRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    # ── Enriquecido de lectura ────────────────────────────────────────────────
    def _nombres_emisoras(self, facturas: list[FacturaClienteRead]) -> dict[uuid.UUID, str]:
        """Nombres de las empresas emisoras de una página, en UNA consulta."""
        from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora

        ids = {f.empresa_facturadora_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(
                EmpresaFacturadora.empresa_facturadora_id, EmpresaFacturadora.nombre_empresa
            ).where(EmpresaFacturadora.empresa_facturadora_id.in_(ids))
        ).all()
        return {fila[0]: fila[1] for fila in filas}

    def _ordenes_de(
        self, facturas: list[FacturaClienteRead]
    ) -> dict[uuid.UUID, list[OrdenDeFactura]]:
        """Órdenes de cada factura, en UNA consulta (ADR-055, ADR-064).

        Antes esto resolvía el folio de LA orden desde `factura_cliente.orden_id`; ahora la
        relación es N:M y vive en `factura_cliente_orden`, así que devuelve una LISTA por
        factura. Ordenada por folio para que la salida sea estable entre llamadas y para
        que "la primera orden" signifique siempre lo mismo.
        """
        from app.modules.ordenes.orden_cliente import OrdenCliente

        ids = {f.factura_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(
                FacturaClienteOrden.factura_id,
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                OrdenCliente.fecha_inicio_campania,
                OrdenCliente.fecha_fin_campania,
                OrdenCliente.subtotal,
            )
            .join(OrdenCliente, OrdenCliente.orden_id == FacturaClienteOrden.orden_id)
            .where(FacturaClienteOrden.factura_id.in_(ids))
            .order_by(OrdenCliente.folio_orden)
        ).all()
        resultado: dict[uuid.UUID, list[OrdenDeFactura]] = {}
        for factura_id, *datos in filas:
            resultado.setdefault(factura_id, []).append(
                OrdenDeFactura(
                    orden_id=datos[0],
                    folio_orden=datos[1],
                    numero_orden_cliente=datos[2],
                    fecha_inicio_campania=datos[3],
                    fecha_fin_campania=datos[4],
                    subtotal=datos[5],
                )
            )
        return resultado

    def _ordenes_de_factura(self, factura_id: uuid.UUID) -> list[uuid.UUID]:
        """IDs de las órdenes que cubre una factura (ADR-064). Ordenado para que el
        handoff con F1 recorra siempre en el mismo orden y los errores sean reproducibles."""
        return list(
            self._repo.db.scalars(
                select(FacturaClienteOrden.orden_id)
                .where(FacturaClienteOrden.factura_id == factura_id)
                .order_by(FacturaClienteOrden.orden_id)
            ).all()
        )

    @staticmethod
    def _aplicar_ordenes(
        leida: FacturaClienteRead, ordenes: dict[uuid.UUID, list[OrdenDeFactura]]
    ) -> None:
        """Vuelca las órdenes de la factura sobre el schema de lectura.

        `orden_id`/`folio_orden` quedan como escalares de la PRIMERA orden: la lista y el
        encabezado del panel los usan como identificador corto. Con varias órdenes, la UI
        completa con "+N" leyendo `ordenes`.
        """
        de_esta = ordenes.get(leida.factura_id, [])
        leida.ordenes = de_esta
        leida.orden_id = de_esta[0].orden_id if de_esta else None
        leida.folio_orden = de_esta[0].folio_orden if de_esta else None

    def _relacionadas_de(
        self, facturas: list[FacturaClienteRead]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """IDs de facturas relacionadas de una página, en UNA consulta (ADR-062: N:N, no
        columna de esta tabla) — mismo patrón por lote que `_nombres_emisoras`."""
        ids = {f.factura_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(
                FacturaClienteRelacionada.factura_id, FacturaClienteRelacionada.relacionada_id
            ).where(FacturaClienteRelacionada.factura_id.in_(ids))
        ).all()
        resultado: dict[uuid.UUID, list[uuid.UUID]] = {}
        for factura_id, relacionada_id in filas:
            resultado.setdefault(factura_id, []).append(relacionada_id)
        return resultado

    def _enriquecida(self, leida: FacturaClienteRead) -> FacturaClienteRead:
        """Enriquece UNA lectura (alta/transiciones) con el folio de su orden y sus
        facturas relacionadas — mismos datos que `list()`/`get()` resuelven en lote, aquí
        en una sola consulta cada uno porque es un solo registro. Sin esto, la respuesta
        de una transición (enviar a timbrado, timbrar, entregar, cancelar) mostraría
        `facturas_relacionadas_ids` vacío aunque la relación exista, hasta el próximo GET
        — mismo tipo de bug que `folio_orden` ya resolvía (ADR-055)."""
        self._aplicar_ordenes(leida, self._ordenes_de([leida]))
        leida.facturas_relacionadas_ids = self._relacionadas_de([leida]).get(
            leida.factura_id, []
        )
        return leida

    def list(self, params: ListParams) -> Page[FacturaClienteRead]:
        pagina = super().list(params)
        nombres = self._nombres_emisoras(pagina.items)
        ordenes = self._ordenes_de(pagina.items)
        relacionadas = self._relacionadas_de(pagina.items)
        for f in pagina.items:
            f.empresa_facturadora = nombres.get(f.empresa_facturadora_id)
            self._aplicar_ordenes(f, ordenes)
            f.facturas_relacionadas_ids = relacionadas.get(f.factura_id, [])
        return pagina

    def get(self, id_: Any) -> FacturaClienteRead:
        leida = super().get(id_)
        leida.empresa_facturadora = self._nombres_emisoras([leida]).get(
            leida.empresa_facturadora_id
        )
        return self._enriquecida(leida)

    # ── Captura ───────────────────────────────────────────────────────────────
    def create(self, data: FacturaClienteCreate, usuario: CurrentUser) -> FacturaClienteRead:
        """Alta de la factura a partir de una OrdenCliente CERRADA.

        Hereda de la OC todo lo que la spec marca como "Derivado" y calcula IVA y total:
        el cliente no puede mandar ninguno de esos campos (`extra="forbid"` en el schema).
        """
        from app.modules.catalogos.agencia import Agencia
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.catalogos.cuenta_contable import CuentaContable
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db

        # Se deduplica conservando el orden de captura; luego se ordena por folio para que
        # "la primera orden" (de la que se heredan los datos) sea siempre la misma
        # independientemente de en qué orden las haya marcado el usuario.
        ordenes_ids = list(dict.fromkeys(data.ordenes_ids))
        ordenes: list[OrdenCliente] = []
        for oid in ordenes_ids:
            oc_i = db.get(OrdenCliente, oid)
            if oc_i is None:
                raise DomainError(
                    "La OrdenCliente indicada no existe.", detalles={"orden_id": str(oid)}
                )
            ordenes.append(oc_i)
        ordenes.sort(key=lambda o: o.folio_orden)

        # PRECONDICIÓN de la ficha: solo se factura lo que F1 ya cerró. Se reportan TODAS
        # las que fallan, no solo la primera: con diez órdenes marcadas, corregirlas de una
        # en una sería exasperante.
        no_cerradas = [
            o for o in ordenes if o.estatus_orden != EstatusOrden.ORDEN_CERRADA.value
        ]
        if no_cerradas:
            raise DomainError(
                "Solo se puede facturar una OrdenCliente en 'orden_cerrada'.",
                detalles={
                    "ordenes": [
                        {"folio_orden": o.folio_orden, "estatus_orden": o.estatus_orden}
                        for o in no_cerradas
                    ]
                },
            )

        # Una OC no puede estar en DOS facturas vigentes. Hasta ADR-064 esto lo garantizaba
        # el índice único filtrado del esquema y este chequeo solo daba un 409 legible;
        # ahora la relación vive en una tabla puente y `estado_facturacion` está en la otra
        # tabla, así que un índice no puede expresarlo: este chequeo es la ÚNICA garantía.
        # Ignora las CANCELADAS por el mismo motivo de negocio de siempre: una OC cuya
        # factura se canceló vuelve a ser facturable (ADR-047).
        ocupadas = db.execute(
            select(FacturaClienteOrden.orden_id, FacturaCliente.numero_factura)
            .join(
                FacturaCliente,
                FacturaCliente.factura_id == FacturaClienteOrden.factura_id,
            )
            .where(
                FacturaClienteOrden.orden_id.in_(ordenes_ids),
                FacturaCliente.estado_facturacion != EstadoFacturacion.CANCELADA.value,
            )
        ).all()
        if ocupadas:
            folios = {o.orden_id: o.folio_orden for o in ordenes}
            raise ConflictError(
                "Alguna de las órdenes ya tiene una factura de cliente vigente.",
                detalles={
                    "ordenes": [
                        {"folio_orden": folios[oid], "numero_factura": numero}
                        for oid, numero in ocupadas
                    ]
                },
            )

        # ── Un CFDI tiene UN emisor y UN receptor ──
        # Dos órdenes del mismo anunciante pueden salir por emisoras distintas, o una
        # facturarse directo al cliente y otra vía agencia. Timbrar eso junto es imposible,
        # así que se rechaza aquí en vez de fallar al exportar el archivo del PAC.
        oc = ordenes[0]
        distintas_emisoras = {o.empresa_facturadora_id for o in ordenes}
        if len(distintas_emisoras) > 1:
            raise DomainError(
                "Todas las órdenes de una misma factura deben salir por la misma empresa "
                "facturadora: un CFDI tiene un solo emisor.",
                detalles={"ordenes": [o.folio_orden for o in ordenes]},
            )
        if len({o.anunciante_id for o in ordenes}) > 1:
            raise DomainError(
                "Todas las órdenes de una misma factura deben ser del mismo anunciante.",
                detalles={"ordenes": [o.folio_orden for o in ordenes]},
            )
        if len({_receptor_de(o) for o in ordenes}) > 1:
            raise DomainError(
                "Todas las órdenes de una misma factura deben tener el mismo receptor: "
                "no se pueden mezclar órdenes facturadas a la agencia con otras facturadas "
                "directo al anunciante.",
                detalles={"ordenes": [o.folio_orden for o in ordenes]},
            )
        if db.get(CuentaContable, data.cuenta_contable_id) is None:
            raise DomainError(
                "La cuenta contable indicada no existe.",
                detalles={"cuenta_contable_id": str(data.cuenta_contable_id)},
            )
        # N:N (ADR-062): cada id debe existir. Se deduplica aquí (no en el schema) porque
        # el orden de captura no importa y el combo del front ya evita repetidos.
        relacionadas_ids = list(dict.fromkeys(data.facturas_relacionadas_ids))
        for rid in relacionadas_ids:
            if db.get(FacturaCliente, rid) is None:
                raise DomainError(
                    "Una de las facturas relacionadas indicadas no existe.",
                    detalles={"factura_relacionada_id": str(rid)},
                )

        # Receptor: anunciante o agencia según `facturacion_directa_cliente` (spec).
        if oc.facturacion_directa_cliente or oc.agencia_id is None:
            anunciante = db.get(Anunciante, oc.anunciante_id)
            if anunciante is None:  # pragma: no cover — la FK de la OC lo garantiza
                raise DomainError("El anunciante de la orden no existe.")
            razon_social, rfc = anunciante.nombre_fiscal, anunciante.rfc_anunciante
        else:
            agencia = db.get(Agencia, oc.agencia_id)
            if agencia is None:  # pragma: no cover — la FK de la OC lo garantiza
                raise DomainError("La agencia de la orden no existe.")
            razon_social, rfc = agencia.nombre_agencia, agencia.rfc_agencia

        # Suma de los SUBTOTALES (no de los totales): el IVA se recalcula sobre la suma,
        # que es lo que exigen los CHECK `ck_factura_cliente_iva_calculado` y
        # `ck_factura_cliente_total_suma`. Sumar totales ya con IVA los violaría.
        subtotal = sum(
            (Decimal(o.subtotal) for o in ordenes), Decimal("0")
        ).quantize(CENTAVOS)
        iva = (subtotal * IVA_RATE).quantize(CENTAVOS)
        # El periodo de transmisión de la factura ABARCA el de todas sus órdenes.
        periodo_inicio = min(o.fecha_inicio_campania for o in ordenes)
        periodo_fin = max(o.fecha_fin_campania for o in ordenes)

        capturado = data.model_dump(
            exclude={
                "razon_social_facturacion",
                "rfc_facturacion",
                "direccion_facturacion",
                "facturas_relacionadas_ids",
                # Ya no son columnas: se persisten como filas de `factura_cliente_orden`.
                "ordenes_ids",
            }
        )
        nuevo_id = uuid4()
        obj = FacturaCliente(
            factura_id=nuevo_id,
            **capturado,
            # ── heredados de la OC (spec: origen "Derivado") ──
            empresa_facturadora_id=oc.empresa_facturadora_id,
            anunciante_id=oc.anunciante_id,
            agencia_id=oc.agencia_id,
            razon_social_facturacion=data.razon_social_facturacion or razon_social,
            rfc_facturacion=data.rfc_facturacion or rfc,
            direccion_facturacion=data.direccion_facturacion or oc.direccion_facturacion,
            fecha_inicio_transmision=periodo_inicio,
            fecha_fin_transmision=periodo_fin,
            # ── calculados ──
            subtotal_factura=subtotal,
            iva_factura=iva,
            total_factura=(subtotal + iva).quantize(CENTAVOS),
            estado_facturacion=EstadoFacturacion.PREPARADA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        for o in ordenes:
            db.add(FacturaClienteOrden(factura_id=nuevo_id, orden_id=o.orden_id))
        for rid in relacionadas_ids:
            db.add(FacturaClienteRelacionada(factura_id=nuevo_id, relacionada_id=rid))
        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def update(
        self, id_: Any, data: FacturaClienteUpdate, usuario: CurrentUser
    ) -> FacturaClienteRead:
        """Edición de los campos capturables. Bloqueada una vez timbrada: a partir de ahí
        el contenido ya salió al SAT y cambiarlo aquí lo desincronizaría."""
        obj = self._get_or_404(id_)
        if obj.estado_facturacion not in (
            EstadoFacturacion.PREPARADA.value,
            EstadoFacturacion.ENVIADA_A_TIMBRADO.value,
        ):
            raise ConflictError(
                "Una factura timbrada, entregada, cobrada o cancelada ya no se edita.",
                detalles={"estado_facturacion": obj.estado_facturacion},
            )
        payload = data.model_dump(exclude_unset=True)
        return self._enriquecida(self._to_read(self._repo.update(obj, payload)))

    # ── Máquina de estados ────────────────────────────────────────────────────
    def _validar_transicion(self, obj: FacturaCliente, destino: str) -> bool:
        """`True` si hay que aplicarla; `False` si ya estaba ahí (idempotente).

        Transición no permitida → 409 `transicion_invalida`.
        """
        if obj.estado_facturacion == destino:
            return False
        if destino not in TRANSICIONES.get(obj.estado_facturacion, set()):
            raise StateTransitionError(
                f"No se puede pasar de '{obj.estado_facturacion}' a '{destino}'.",
                detalles={"estado_facturacion": obj.estado_facturacion, "destino": destino},
            )
        return True

    def _constante_unica(self, grupo: str) -> str | None:
        """Clave del grupo de `ConstantesSistema` **solo si hay exactamente una activa**.

        Con varias, elegir cuál es una decision FISCAL que nadie ha tomado (que UsoCFDI?
        que ClaveProdServ?), y adivinarla produciria un CFDI que timbra pero esta mal.
        Con cero, sencillamente no hay dato. En ambos casos se devuelve `None` y el campo
        acaba reportado como faltante.
        """
        from app.modules.catalogos.constantes_sistema import ConstanteSistema

        claves = list(
            self._repo.db.scalars(
                select(ConstanteSistema.clave).where(
                    ConstanteSistema.grupo == grupo,
                    ConstanteSistema.activo == True,  # noqa: E712 - BIT en SQL Server (ADR-014)
                )
            ).all()
        )
        return claves[0] if len(claves) == 1 else None

    def _domicilio_de(self, entidad: Any) -> DomicilioFiscal | None:
        """Domicilio estructurado (ADR-059) de un `Anunciante`/`EmpresaFacturadora`, o
        `None` si el registro no lo tiene capturado así todavía (registro viejo, o el
        objeto no existe) — el llamador cae al texto libre legacy en ese caso."""
        if entidad is None:
            return None
        return DomicilioFiscal(
            calle=entidad.calle,
            numero_exterior=entidad.numero_exterior,
            numero_interior=entidad.numero_interior,
            colonia=entidad.colonia,
            localidad=entidad.localidad,
            referencia=entidad.referencia_domicilio,
            municipio=entidad.municipio,
            estado=entidad.estado,
            pais=entidad.pais or "MEX",
            codigo_postal=entidad.codigo_postal,
        )

    def _datos_timbrado(self, obj: FacturaCliente) -> DatosTimbrado:
        """Resuelve TODO lo que el layout necesita. La integracion no consulta la base."""
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
        from app.modules.ordenes.orden_cliente import OrdenCliente

        db = self._repo.db
        emisor = db.get(EmpresaFacturadora, obj.empresa_facturadora_id)
        # TODAS las órdenes de la factura, ordenadas por folio. El receptor y los campos
        # de campaña se resuelven sobre este conjunto; el servicio ya garantizó en el alta
        # que comparten emisora y receptor, así que la primera es representativa de ambos.
        ordenes = [
            oc
            for oc in (
                db.get(OrdenCliente, oid) for oid in self._ordenes_de_factura(obj.factura_id)
            )
            if oc is not None
        ]
        ordenes.sort(key=lambda o: o.folio_orden)
        orden = ordenes[0] if ordenes else None

        # El receptor de ESTA factura puede ser el Anunciante (directo) o la Agencia —
        # mismo criterio que `create()` para elegir razón social/RFC. El domicilio
        # estructurado (ADR-059) solo existe hoy en Anunciante/EmpresaFacturadora, NO en
        # Agencia: si el receptor es la agencia, cae al texto libre de `direccion_facturacion`.
        receptor_domicilio = None
        if orden is not None and (orden.facturacion_directa_cliente or orden.agencia_id is None):
            receptor_domicilio = self._domicilio_de(db.get(Anunciante, obj.anunciante_id))

        # Folios fiscales de las facturas relacionadas (ADR-062: N:N): al PAC van los UUID
        # de los CFDI previos, no nuestros identificadores internos. Una relacionada sin
        # timbrar todavía (folio_fiscal_sat NULL) se omite: no hay UUID que mandar.
        relacionadas_ids = [
            r.relacionada_id
            for r in db.scalars(
                select(FacturaClienteRelacionada).where(
                    FacturaClienteRelacionada.factura_id == obj.factura_id
                )
            ).all()
        ]
        folios_relacionados = tuple(
            f.folio_fiscal_sat
            for f in db.scalars(
                select(FacturaCliente).where(FacturaCliente.factura_id.in_(relacionadas_ids))
            ).all()
            if f.folio_fiscal_sat
        )

        return DatosTimbrado(
            numero_factura=obj.numero_factura,
            # El layout pide fecha Y hora; el modelo guarda solo la fecha de emision, asi
            # que se combina con la hora de creacion del registro.
            fecha_emision=datetime.combine(obj.fecha_factura, obj.created_at.time()),
            fecha_factura=obj.fecha_factura,
            periodo_inicio=obj.fecha_inicio_transmision,
            periodo_fin=obj.fecha_fin_transmision,
            descripcion=obj.descripcion_factura,
            observaciones=obj.observaciones_factura,
            subtotal=Decimal(obj.subtotal_factura),
            iva=Decimal(obj.iva_factura),
            total=Decimal(obj.total_factura),
            tasa_iva=IVA_RATE,
            emisor_nombre=emisor.nombre_empresa if emisor else "",
            emisor_rfc=emisor.rfc_empresa if emisor else "",
            emisor_direccion=emisor.direccion_empresa if emisor else None,
            emisor_domicilio=self._domicilio_de(emisor),
            receptor_nombre=obj.razon_social_facturacion,
            receptor_rfc=obj.rfc_facturacion,
            receptor_direccion=obj.direccion_facturacion,
            receptor_domicilio=receptor_domicilio,
            # Detalle CONSOLIDADO (decisión del equipo): una sola línea de concepto por
            # el total de la factura, no una por orden. Los campos de campaña, que en el
            # layout son de una sola orden, se concatenan; van en la sección
            # `Personalizados`, que es clave-valor y no de ancho fijo, así que no los
            # trunca el formato. Queda abierto si el PAC les impone un largo máximo.
            orden_folio=", ".join(o.folio_orden for o in ordenes) or None,
            orden_numero_cliente=", ".join(
                o.numero_orden_cliente for o in ordenes if o.numero_orden_cliente
            )
            or None,
            # El producto solo se emite si TODAS coinciden; si no, describir una campaña
            # inventada sería peor que caer a la descripción que capturó Facturación.
            orden_producto=_producto_comun(ordenes) or obj.descripcion_factura,
            porcentaje_comision_agencia=(
                Decimal(orden.porcentaje_comision_agencia_snap)
                if orden and orden.porcentaje_comision_agencia_snap is not None
                else None
            ),
            info_cuenta_pago=obj.info_cuenta_pago,
            metodo_pago_clave=obj.metodo_pago_clave,
            folios_fiscales_relacionados=folios_relacionados,
            # Serie: del propio número de factura, no de un catálogo (ADR-060 bis).
            serie=_serie_desde_numero(obj.numero_factura),
            # Constantes fiscales: solo si el catalogo no deja lugar a dudas.
            regimen_fiscal_emisor=self._constante_unica("RegimenFiscal"),
            regimen_fiscal_receptor=self._constante_unica("RegimenFiscal"),
            uso_cfdi=self._constante_unica("UsoCFDI"),
            clave_prod_serv=self._constante_unica("ClaveProdServ"),
            clave_unidad=self._constante_unica("ClaveUnidad"),
            forma_pago_clave=self._constante_unica("FormaPago"),
            # AGREGADOS.LugarExpedicion = CP de dónde se expide el CFDI (catálogo SAT
            # c_CodigoPostal) — el del domicilio fiscal del emisor (ADR-059), no una
            # constante nueva que capturar aparte.
            codigo_postal_expedicion=emisor.codigo_postal if emisor else None,
        )

    # `Sequence[str]` y no `list[str]`: dentro de esta clase el nombre `list` refiere al
    # MÉTODO `list` de arriba, no al tipo (mismo motivo que `BaseService.historial`).
    def archivo_plano(self, factura_id: uuid.UUID) -> tuple[bytes, str, Sequence[str]]:
        """Exporta la factura al layout del PAC via el PUERTO.

        Devuelve `(contenido, nombre_archivo, campos_faltantes)`. El archivo se genera
        AUNQUE falten campos -para poder revisarlo- pero con campos faltantes el PAC lo
        rechazaria: quien lo descarga tiene que enterarse, y por eso la lista viaja de
        vuelta hasta la pantalla.
        """
        obj = self._get_or_404(factura_id)
        if obj.estado_facturacion == EstadoFacturacion.CANCELADA.value:
            raise ConflictError("Una factura cancelada no se exporta a timbrado.")
        exportador = get_timbrado_export()
        datos = self._datos_timbrado(obj)
        return (
            exportador.exportar(datos),
            exportador.nombre_archivo(datos),
            exportador.campos_faltantes(datos),
        )

    def enviar_a_timbrado(self, factura_id: uuid.UUID, usuario: CurrentUser) -> FacturaClienteRead:
        obj = self._get_or_404(factura_id)
        if self._validar_transicion(obj, EstadoFacturacion.ENVIADA_A_TIMBRADO.value):
            obj.estado_facturacion = EstadoFacturacion.ENVIADA_A_TIMBRADO.value
            self._repo.db.commit()
            self._repo.db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def timbrar(
        self, factura_id: uuid.UUID, input_: TimbrarIn, usuario: CurrentUser
    ) -> FacturaClienteRead:
        """Registra la respuesta del PAC y **promueve la OrdenCliente a `facturada`**.

        El handoff (ficha de F2): la OC pasa a `facturada` exactamente aquí — no con
        `preparada`/`enviada_a_timbrado`, ni esperando a `entregada`. Se invoca
        `OrdenClienteService.marcar_facturada`, que vive en F1 (dueño de esa máquina de
        estados), con la MISMA sesión y ANTES del commit: si la OC no admite la
        transición, la excepción aborta también el timbrado. Atómico por construcción.
        """
        from app.modules.ordenes.orden_cliente import (
            OrdenCliente,
            OrdenClienteRepository,
            OrdenClienteService,
        )

        obj = self._get_or_404(factura_id)
        db = self._repo.db
        if not self._validar_transicion(obj, EstadoFacturacion.TIMBRADA.value):
            # ya timbrada: idempotente, no re-dispara el handoff
            return self._enriquecida(self._to_read(obj))

        obj.folio_fiscal_sat = input_.folio_fiscal_sat
        obj.fecha_timbrado = input_.fecha_timbrado
        obj.serie_timbrado = input_.serie_timbrado
        if input_.xml_path is not None:
            obj.xml_path = input_.xml_path
        if input_.pdf_path is not None:
            obj.pdf_path = input_.pdf_path
        obj.estado_facturacion = EstadoFacturacion.TIMBRADA.value

        # ── handoff con F1, misma sesión, antes del commit ──
        # Sobre TODAS las órdenes de la factura: hoy es una, pero el bucle ya es la forma
        # correcta y evita que la facturación múltiple deje órdenes sin promover.
        servicio_oc = OrdenClienteService(OrdenClienteRepository(db, OrdenCliente))
        for orden_id in self._ordenes_de_factura(obj.factura_id):
            servicio_oc.marcar_facturada(orden_id)

        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def entregar(
        self, factura_id: uuid.UUID, input_: EntregarIn, usuario: CurrentUser
    ) -> FacturaClienteRead:
        obj = self._get_or_404(factura_id)
        if self._validar_transicion(obj, EstadoFacturacion.ENTREGADA.value):
            obj.estado_facturacion = EstadoFacturacion.ENTREGADA.value
            obj.fecha_entrega_factura = input_.fecha_entrega_factura or date.today()
            self._repo.db.commit()
            self._repo.db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def cancelar(self, factura_id: uuid.UUID, usuario: CurrentUser) -> FacturaClienteRead:
        """Cancelación desde los 4 primeros estados, **revirtiendo el handoff** (ADR-047).

        Si la OrdenCliente quedó en `facturada`, vuelve a `orden_cerrada` y puede
        facturarse de nuevo (el índice único es filtrado: ignora las canceladas). Si ya
        está en `cobrada`, `revertir_facturacion` lanza 400 y la cancelación NO ocurre:
        deshacer una venta cobrada exige una nota de crédito que el sistema no maneja.

        La reversión se invoca ANTES del commit y con la misma sesión, igual que el
        handoff hacia adelante: cancelar la factura y revertir la orden son atómicos.
        """
        from app.modules.ordenes.orden_cliente import (
            OrdenCliente,
            OrdenClienteRepository,
            OrdenClienteService,
        )

        obj = self._get_or_404(factura_id)
        db = self._repo.db
        if not self._validar_transicion(obj, EstadoFacturacion.CANCELADA.value):
            # ya cancelada: idempotente, no re-revierte
            return self._enriquecida(self._to_read(obj))

        obj.estado_facturacion = EstadoFacturacion.CANCELADA.value

        # ── reversión del handoff, misma transacción ──
        # Si CUALQUIERA de las órdenes está en `cobrada`, `revertir_facturacion` lanza 400
        # y la cancelación entera no ocurre: nunca quedan órdenes revertidas a medias.
        servicio_oc = OrdenClienteService(OrdenClienteRepository(db, OrdenCliente))
        for orden_id in self._ordenes_de_factura(obj.factura_id):
            servicio_oc.revertir_facturacion(orden_id)

        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))


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


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_clientes.post("", response_model=FacturaClienteRead, status_code=201)
def crear_factura_cliente(
    payload: FacturaClienteCreate,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:crear")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    """400 `error_dominio` si la OrdenCliente no está en `orden_cerrada`;
    409 `conflicto` si esa orden ya tiene factura (1:1)."""
    return svc.create(payload, usuario)


@router_clientes.put("/{item_id}", response_model=FacturaClienteRead)
def actualizar_factura_cliente(
    item_id: uuid.UUID,
    payload: FacturaClienteUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:editar")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    return svc.update(item_id, payload, usuario)


@router_clientes.get("/{item_id}/archivo-plano")
def descargar_archivo_plano(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:leer")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> Response:
    """Exporta la factura al layout real del PAC (V40).

    Devuelve además la cabecera `X-Campos-Faltantes` con los campos que el PAC exige y que
    el modelo todavía no puede llenar (régimen fiscal, ClaveProdServ, UsoCFDI, domicilios
    desglosados…). Si viene vacía, el archivo está completo.
    """
    contenido, nombre, faltantes = svc.archivo_plano(item_id)
    cabeceras = {
        "Content-Disposition": f'attachment; filename="{nombre}"',
        # La pantalla lee esta cabecera para advertir ANTES de que alguien envíe el
        # archivo. `Access-Control-Expose-Headers` es indispensable: sin ella el navegador
        # no deja que el frontend vea cabeceras propias en una respuesta con CORS.
        "X-Campos-Faltantes": "; ".join(faltantes),
        "Access-Control-Expose-Headers": "Content-Disposition, X-Campos-Faltantes",
    }
    return Response(
        content=contenido,
        media_type=f"text/plain; charset={settings.timbrado_encoding}",
        headers=cabeceras,
    )


@router_clientes.post("/{item_id}/enviar-a-timbrado", response_model=FacturaClienteRead)
def enviar_a_timbrado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:editar")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    return svc.enviar_a_timbrado(item_id, usuario)


@router_clientes.post("/{item_id}/timbrar", response_model=FacturaClienteRead)
def timbrar_factura(
    item_id: uuid.UUID,
    payload: TimbrarIn,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:editar")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    """Registra la respuesta del PAC. **Promueve la OrdenCliente a `facturada`** en la
    misma transacción (handoff con F1)."""
    return svc.timbrar(item_id, payload, usuario)


@router_clientes.post("/{item_id}/entregar", response_model=FacturaClienteRead)
def entregar_factura(
    item_id: uuid.UUID,
    payload: EntregarIn,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:editar")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    return svc.entregar(item_id, payload, usuario)


@router_clientes.post("/{item_id}/cancelar", response_model=FacturaClienteRead)
def cancelar_factura(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:editar")),
    svc: FacturaClienteService = Depends(get_factura_cliente_service),
) -> FacturaClienteRead:
    return svc.cancelar(item_id, usuario)


# ══════════════════════════════════════════════════════════════════════════════
# Bandeja "Listas para facturar" (pantalla aprobada `Fase_2_-_Facturacion.html`)
# ══════════════════════════════════════════════════════════════════════════════
# Órdenes en `orden_cerrada` que TODAVÍA no tienen FacturaCliente. Es el atajo operativo
# del día a día de Facturación: saber qué falta por facturar sin ir a rebuscar en la
# bandeja de Órdenes (F1).
#
# Vive en F2 y no en `ordenes`, aunque la entidad principal sea `OrdenCliente`: la
# pregunta que responde ("¿a qué le falta factura?") es de Facturación, y el criterio que
# la define (la AUSENCIA de una fila en `factura_cliente`) es un concepto de F2. `ordenes`
# no se toca: solo se LEE su modelo, sin importar nada de su servicio ni de su router.
#
# Cuelga de su propio prefijo y no de `/clientes/...` a propósito: `/clientes/{item_id}`
# ya está registrado antes en este archivo y capturaría cualquier segmento literal,
# devolviendo un 422 al intentar leerlo como UUID.


class AnuncianteFacturable(BaseModel):
    """Opción del combo de facturación múltiple: anunciante + cuántas órdenes tiene listas."""

    model_config = ConfigDict(from_attributes=True)

    anunciante_id: uuid.UUID
    anunciante: str
    ordenes: int


class OrdenPorFacturarRead(BaseModel):
    """Los datos que la tarjeta de la bandeja necesita, ya resueltos.

    Se devuelven los NOMBRES (anunciante, agencia, vendedor) y no solo sus IDs para que
    la pantalla no tenga que hacer tres consultas de catálogo por tarjeta.
    """

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    anunciante_id: uuid.UUID
    anunciante: str
    #: `None` = trato directo con el anunciante, sin agencia de por medio.
    agencia: str | None = None
    vendedor: str | None = None
    producto: str | None = None
    fecha_inicio_campania: date
    fecha_fin_campania: date
    subtotal: Decimal
    total: Decimal
    # ── Lo que el alta necesita para PRE-CARGAR el formulario (pantalla aprobada) ──
    empresa_emisora: str | None = None
    total_spots: int | None = None
    duracion_spot: str | None = None
    #: A quién se factura: agencia si la hay y no es facturación directa (misma regla que
    #: aplica el servicio al crear). Se resuelve aquí para que el formulario no la repita.
    facturacion_directa_cliente: bool = False
    receptor_razon_social: str | None = None
    receptor_rfc: str | None = None
    receptor_direccion: str | None = None


class OrdenesPorFacturarRepository:
    """Repositorio propio: la consulta cruza `orden_cliente` con `factura_cliente` y tres
    catálogos, así que no encaja en `BaseRepository` (que opera sobre un solo modelo)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def listar(
        self,
        page: int,
        size: int,
        q: str | None,
        anunciante_id: uuid.UUID | None = None,
    ) -> tuple[list[Any], int]:
        from app.modules.catalogos.agencia import Agencia
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        base = (
            select(
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                OrdenCliente.anunciante_id,
                Anunciante.nombre_comercial.label("anunciante"),
                Agencia.nombre_agencia.label("agencia"),
                Vendedor.nombre_vendedor.label("vendedor"),
                OrdenCliente.producto,
                OrdenCliente.fecha_inicio_campania,
                OrdenCliente.fecha_fin_campania,
                OrdenCliente.subtotal,
                OrdenCliente.total,
                EmpresaFacturadora.nombre_empresa.label("empresa_emisora"),
                OrdenCliente.total_spots,
                OrdenCliente.duracion_spot,
                OrdenCliente.facturacion_directa_cliente,
                OrdenCliente.direccion_facturacion.label("receptor_direccion"),
                # Receptor: agencia si la hay y no es facturación directa. `case` en vez de
                # resolverlo en Python para que salga en la MISMA consulta.
                case(
                    (
                        (OrdenCliente.facturacion_directa_cliente == True)  # noqa: E712 — BIT
                        | (OrdenCliente.agencia_id.is_(None)),
                        Anunciante.nombre_fiscal,
                    ),
                    else_=Agencia.nombre_agencia,
                ).label("receptor_razon_social"),
                case(
                    (
                        (OrdenCliente.facturacion_directa_cliente == True)  # noqa: E712 — BIT
                        | (OrdenCliente.agencia_id.is_(None)),
                        Anunciante.rfc_anunciante,
                    ),
                    else_=Agencia.rfc_agencia,
                ).label("receptor_rfc"),
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .join(
                EmpresaFacturadora,
                EmpresaFacturadora.empresa_facturadora_id == OrdenCliente.empresa_facturadora_id,
            )
            .outerjoin(Agencia, Agencia.agencia_id == OrdenCliente.agencia_id)
            .outerjoin(Vendedor, Vendedor.vendedor_id == OrdenCliente.vendedor_principal_id)
            # El corazón de la bandeja: "cerrada y sin factura VIGENTE".
            # Se expresa con NOT EXISTS y no con LEFT JOIN + IS NULL. Con la relación N:M
            # (ADR-064) el LEFT JOIN encadenado produce UNA FILA POR FACTURA de la orden,
            # y las canceladas no casan con la condición del segundo join: una OC ya
            # facturada que además tuviera dos facturas canceladas reaparecía en la bandeja
            # —dos veces— pese a tener su factura vigente. NOT EXISTS pregunta por la
            # existencia, no multiplica filas, y conserva la regla de ADR-047: las
            # canceladas NO cuentan, así que una OC cuya factura se canceló vuelve a la
            # bandeja.
            .where(
                OrdenCliente.estatus_orden == EstatusOrden.ORDEN_CERRADA.value,
                ~_tiene_factura_vigente(OrdenCliente.orden_id),
            )
        )
        if anunciante_id is not None:
            base = base.where(OrdenCliente.anunciante_id == anunciante_id)
        if q:
            patron = f"%{q.strip()}%"
            base = base.where(
                OrdenCliente.folio_orden.ilike(patron)
                | OrdenCliente.numero_orden_cliente.ilike(patron)
                | Anunciante.nombre_comercial.ilike(patron)
            )

        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        filas = self.db.execute(
            base.order_by(OrdenCliente.folio_orden).offset((page - 1) * size).limit(size)
        ).all()
        return list(filas), int(total)


    def anunciantes_facturables(self, minimo: int) -> list[Any]:
        """Anunciantes con al menos `minimo` órdenes DISPONIBLES para facturar.

        "Disponibles" y no "cerradas" a secas: si contara las ya facturadas, el combo
        ofrecería anunciantes cuya bandeja sale vacía al seleccionarlos. Reproduce por eso
        las mismas condiciones que `listar()`.
        """
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        stmt = (
            select(
                OrdenCliente.anunciante_id,
                Anunciante.nombre_comercial.label("anunciante"),
                func.count().label("ordenes"),
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .where(
                OrdenCliente.estatus_orden == EstatusOrden.ORDEN_CERRADA.value,
                ~_tiene_factura_vigente(OrdenCliente.orden_id),
            )
            .group_by(OrdenCliente.anunciante_id, Anunciante.nombre_comercial)
            .having(func.count() >= minimo)
            .order_by(Anunciante.nombre_comercial)
        )
        return list(self.db.execute(stmt).all())


class OrdenesPorFacturarService:
    """Solo lectura. No muta nada: el alta de la factura sigue siendo `POST /clientes`."""

    def __init__(self, repo: OrdenesPorFacturarRepository) -> None:
        self._repo = repo

    def listar(
        self,
        page: int,
        size: int,
        q: str | None,
        anunciante_id: uuid.UUID | None = None,
    ) -> Page[OrdenPorFacturarRead]:
        filas, total = self._repo.listar(page, size, q, anunciante_id)
        return Page[OrdenPorFacturarRead](
            items=[OrdenPorFacturarRead.model_validate(f._mapping) for f in filas],
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size else 0,
        )


    def anunciantes_facturables(self, minimo: int) -> list[AnuncianteFacturable]:
        return [
            AnuncianteFacturable.model_validate(f._mapping)
            for f in self._repo.anunciantes_facturables(minimo)
        ]


def get_ordenes_por_facturar_service(
    db: Session = Depends(get_db),
) -> OrdenesPorFacturarService:
    return OrdenesPorFacturarService(OrdenesPorFacturarRepository(db))


router_por_facturar = APIRouter(
    prefix="/ordenes-por-facturar", tags=["facturacion:por-facturar"]
)


@router_por_facturar.get("", response_model=Page[OrdenPorFacturarRead])
def listar_ordenes_por_facturar(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en folio, número de orden y anunciante"),
    anunciante_id: uuid.UUID | None = Query(
        None, description="Solo las órdenes de este anunciante (facturación múltiple)"
    ),
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:leer")),
    svc: OrdenesPorFacturarService = Depends(get_ordenes_por_facturar_service),
) -> Page[OrdenPorFacturarRead]:
    """Órdenes en `orden_cerrada` que aún no tienen `FacturaCliente`.

    El `total` de la respuesta SIN filtros es el contador que la pantalla muestra en el
    sidebar; con `anunciante_id` es la bandeja acotada de la facturación múltiple.
    """
    return svc.listar(page, size, q, anunciante_id)


@router_por_facturar.get("/anunciantes", response_model=list[AnuncianteFacturable])
def listar_anunciantes_facturables(
    minimo: int = Query(2, ge=1, description="Mínimo de órdenes disponibles para aparecer"),
    usuario: CurrentUser = Depends(requiere_permiso("facturacion:leer")),
    svc: OrdenesPorFacturarService = Depends(get_ordenes_por_facturar_service),
) -> list[AnuncianteFacturable]:
    """Llena el combo de facturación múltiple.

    Por defecto solo los anunciantes con **2 o más** órdenes disponibles: con una sola no
    hay nada que agrupar y ofrecerlo sería una vía muerta. Sin paginar a propósito — es un
    combo con búsqueda en el cliente, no una lista.
    """
    return svc.anunciantes_facturables(minimo)
