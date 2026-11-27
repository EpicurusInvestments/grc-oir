"""Repositorio de F4-01 (Estado de resultados) — SOLO consultas agregadas.

Cada método recibe una ventana `[inicio, fin)` ya resuelta por el service (nunca hace
aritmética de fechas aquí, ADR-014/036). Los renglones que se prorratean a "sin IVA"
(Cobrado y los "Pagado" de costos directos) regresan las filas CRUDAS de una sola
consulta (JOIN acotado a la ventana del mes, nunca todo el histórico) — el cálculo
`ROUND(monto × razón, 2)` fila por fila vive en el `service` (ADR-039: la aritmética de
dinero se corrobora contra SQL Server real, no solo SQLite).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.vendedor import Vendedor
from app.modules.cobranza.cobranza_factura import (
    CobranzaFactura,
    EstatusCobro,
    EstatusPago,
    PagoCliente,
)
from app.modules.cobranza.requisicion import EstatusRequisicion, Requisicion, TipoRequisicion
from app.modules.facturacion.costo_adicional import CostoAdicional, TipoCosto
from app.modules.facturacion.factura_afiliado import FacturaAfiliado
from app.modules.facturacion.factura_agencia import FacturaAgencia
from app.modules.facturacion.factura_cliente import EstadoFacturacion, FacturaCliente
from app.modules.facturacion.factura_vendedor import FacturaVendedor
from app.modules.ordenes.incidencia import Incidencia
from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente
from app.modules.ordenes.orden_estacion import OrdenEstacion, OrdenEstacionDia
from app.modules.ordenes.verificacion import Verificacion

# Un CFDI no emitido (preparada/enviada_a_timbrado) no es un ingreso real todavía; una
# factura cancelada tampoco. Las Notas de Crédito (tipo_comprobante='E') se netean
# SOLAS dentro del mismo SUM: su subtotal_factura ya se persiste en negativo (CHECK
# condicional de ADR-293), así que no necesitan ningún filtro aparte aquí.
_ESTADOS_FACTURADO = (
    EstadoFacturacion.TIMBRADA.value,
    EstadoFacturacion.ENTREGADA.value,
    EstadoFacturacion.COBRADA.value,
)


@dataclass(frozen=True)
class FilaProrrateable:
    """Una fila cruda lista para que el service calcule `ROUND(monto * sin_iva /
    con_iva, 2)` y la sume. `sin_iva`/`con_iva` son los campos de LA FACTURA de
    referencia (de cliente o de proveedor, según el renglón)."""

    monto: Decimal
    sin_iva: Decimal
    con_iva: Decimal


@dataclass(frozen=True)
class FilaVendedorRol:
    """Una orden vista desde el rol de UN vendedor (principal o secundario) —
    `porcentaje` es el `%_snap` congelado en la orden para ESE rol, puede ser `None`."""

    vendedor_id: uuid.UUID
    total: Decimal
    porcentaje: Decimal | None


@dataclass(frozen=True)
class FilaCobranzaAbierta:
    """Una `CobranzaFactura` NO `cobrada`, con su saldo (con IVA) ya resuelto en SQL."""

    cobranza_id: uuid.UUID
    anunciante_id: uuid.UUID
    fecha_estimada_cobro: date
    total_factura: Decimal
    cobrado: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.total_factura - self.cobrado


@dataclass(frozen=True)
class FilaCumplimientoEstacion:
    """Una estación con sus spots agregados — SOLO días ya con `Verificacion` y NO
    `cancelada` (decisión 2 de Tanda 3: un día futuro/no verificado no penaliza el %;
    un día cancelado no es un incumplimiento, nunca se pactó transmitir)."""

    estacion_id: uuid.UUID
    nombre_estacion: str
    ordenado: int
    ejecutado: int


@dataclass(frozen=True)
class FilaIncidenciaAfiliado:
    """Una fila por (afiliado, tipo_incidencia) con su conteo — el service arma el
    desglose completo por afiliado a partir de varias de estas filas."""

    afiliado_id: uuid.UUID
    nombre_afiliado: str
    tipo_incidencia: str
    total: int


class ReportesRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Ingresos ────────────────────────────────────────────────────────────────
    def facturado_clientes(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(FacturaCliente.subtotal_factura), 0)).where(
            FacturaCliente.fecha_factura >= inicio,
            FacturaCliente.fecha_factura < fin,
            FacturaCliente.estado_facturacion.in_(_ESTADOS_FACTURADO),
        )
        return Decimal(self.db.scalar(stmt) or 0)

    def filas_cobrado(self, inicio: date, fin: date) -> list[FilaProrrateable]:
        """Pagos de cliente `pagado`, asignados (no huérfanos) y que NO sean el pago
        SINTÉTICO de una Nota de Crédito (ADR-293: no es efectivo real, su efecto ya
        se reconoció al reducir `facturado_clientes`)."""
        stmt = (
            select(
                PagoCliente.monto_aplicado,
                FacturaCliente.subtotal_factura,
                FacturaCliente.total_factura,
            )
            .join(CobranzaFactura, CobranzaFactura.cobranza_id == PagoCliente.cobranza_id)
            .join(FacturaCliente, FacturaCliente.factura_id == CobranzaFactura.factura_id)
            .where(
                PagoCliente.fecha_pago_cliente >= inicio,
                PagoCliente.fecha_pago_cliente < fin,
                PagoCliente.estatus_pago == EstatusPago.PAGADO.value,
                PagoCliente.cobranza_id.is_not(None),
                PagoCliente.factura_egreso_id.is_(None),
            )
        )
        return [FilaProrrateable(m, s, t) for m, s, t in self.db.execute(stmt).all()]

    # ── Costos directos: Facturado (SUM directo, sin prorrateo) ──────────────────
    def facturado_afiliados(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(FacturaAfiliado.monto_factura_afiliado), 0)).where(
            FacturaAfiliado.fecha_factura_afiliado >= inicio,
            FacturaAfiliado.fecha_factura_afiliado < fin,
        )
        return Decimal(self.db.scalar(stmt) or 0)

    def facturado_agencias(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(FacturaAgencia.monto_factura_agencia), 0)).where(
            FacturaAgencia.fecha_factura_agencia >= inicio,
            FacturaAgencia.fecha_factura_agencia < fin,
        )
        return Decimal(self.db.scalar(stmt) or 0)

    def facturado_vendedores(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(FacturaVendedor.monto_factura_vendedor), 0)).where(
            FacturaVendedor.fecha_factura_vendedor >= inicio,
            FacturaVendedor.fecha_factura_vendedor < fin,
        )
        return Decimal(self.db.scalar(stmt) or 0)

    # ── Costos directos: Pagado (filas crudas, prorrateadas por el service) ──────
    def filas_pagado_afiliados(self, inicio: date, fin: date) -> list[FilaProrrateable]:
        stmt = (
            select(
                Requisicion.monto_requisicion,
                FacturaAfiliado.monto_factura_afiliado,
                FacturaAfiliado.total_factura_afiliado,
            )
            .join(
                FacturaAfiliado,
                FacturaAfiliado.factura_afiliado_id == Requisicion.factura_afiliado_id,
            )
            .where(
                Requisicion.tipo_requisicion == TipoRequisicion.PAGO_AFILIADO.value,
                Requisicion.estatus_requisicion == EstatusRequisicion.PAGADA.value,
                Requisicion.fecha_pago_requisicion >= inicio,
                Requisicion.fecha_pago_requisicion < fin,
            )
        )
        return [FilaProrrateable(m, s, t) for m, s, t in self.db.execute(stmt).all()]

    def filas_pagado_agencias(self, inicio: date, fin: date) -> list[FilaProrrateable]:
        stmt = (
            select(
                Requisicion.monto_requisicion,
                FacturaAgencia.monto_factura_agencia,
                FacturaAgencia.total_factura_agencia,
            )
            .join(
                FacturaAgencia,
                FacturaAgencia.factura_agencia_id == Requisicion.factura_agencia_id,
            )
            .where(
                Requisicion.tipo_requisicion == TipoRequisicion.PAGO_AGENCIA.value,
                Requisicion.estatus_requisicion == EstatusRequisicion.PAGADA.value,
                Requisicion.fecha_pago_requisicion >= inicio,
                Requisicion.fecha_pago_requisicion < fin,
            )
        )
        return [FilaProrrateable(m, s, t) for m, s, t in self.db.execute(stmt).all()]

    def filas_pagado_comisiones_vendedores(self, inicio: date, fin: date) -> list[FilaProrrateable]:
        stmt = (
            select(
                Requisicion.monto_requisicion,
                FacturaVendedor.monto_factura_vendedor,
                FacturaVendedor.total_factura_vendedor,
            )
            .join(
                FacturaVendedor,
                FacturaVendedor.factura_vendedor_id == Requisicion.factura_vendedor_id,
            )
            .where(
                Requisicion.tipo_requisicion == TipoRequisicion.COMISION_VENDEDOR.value,
                Requisicion.estatus_requisicion == EstatusRequisicion.PAGADA.value,
                Requisicion.fecha_pago_requisicion >= inicio,
                Requisicion.fecha_pago_requisicion < fin,
            )
        )
        return [FilaProrrateable(m, s, t) for m, s, t in self.db.execute(stmt).all()]

    def filas_pagado_comisiones_agencias(self, inicio: date, fin: date) -> list[FilaProrrateable]:
        """`comision_agencia` no tiene factura ligada (usa `orden_id` directo) — se
        prorratea contra la `OrdenCliente` referenciada."""
        stmt = (
            select(Requisicion.monto_requisicion, OrdenCliente.subtotal, OrdenCliente.total)
            .join(OrdenCliente, OrdenCliente.orden_id == Requisicion.orden_id)
            .where(
                Requisicion.tipo_requisicion == TipoRequisicion.COMISION_AGENCIA.value,
                Requisicion.estatus_requisicion == EstatusRequisicion.PAGADA.value,
                Requisicion.fecha_pago_requisicion >= inicio,
                Requisicion.fecha_pago_requisicion < fin,
            )
        )
        return [FilaProrrateable(m, s, t) for m, s, t in self.db.execute(stmt).all()]

    # ── Costos indirectos (sin IVA, sin prorrateo — confirmado con el equipo) ────
    def costo_por_tipo(self, periodo: str, tipo_costo: TipoCosto) -> Decimal:
        stmt = select(func.coalesce(func.sum(CostoAdicional.monto_costo), 0)).where(
            CostoAdicional.tipo_costo == tipo_costo.value,
            CostoAdicional.periodo_contable == periodo,
        )
        return Decimal(self.db.scalar(stmt) or 0)

    # ── Dashboard comercial (F4-02) ───────────────────────────────────────────────
    def _no_cancelada(self, inicio: date, fin: date) -> tuple[ColumnElement[bool], ...]:
        return (
            OrdenCliente.estatus_orden != EstatusOrden.CANCELADA.value,
            OrdenCliente.fecha_venta >= inicio,
            OrdenCliente.fecha_venta < fin,
        )

    def filas_ventas_principal(self, inicio: date, fin: date) -> list[FilaVendedorRol]:
        """Una fila por orden — el vendedor PRINCIPAL. "Ventas" solo cuenta aquí (nunca
        se duplica el total de una orden por tener 2 vendedores)."""
        stmt = select(
            OrdenCliente.vendedor_principal_id,
            OrdenCliente.total,
            OrdenCliente.porcentaje_comision_vendedor_principal_snap,
        ).where(*self._no_cancelada(inicio, fin))
        return [FilaVendedorRol(v, t, p) for v, t, p in self.db.execute(stmt).all()]

    def filas_comision_secundario(self, inicio: date, fin: date) -> list[FilaVendedorRol]:
        """Una fila por orden con vendedor SECUNDARIO — solo para sumar su comisión al
        mismo `Vendedor` (nunca cuenta como "Ventas" propias, evita duplicar el total
        de la orden)."""
        stmt = select(
            OrdenCliente.vendedor_secundario_id,
            OrdenCliente.total,
            OrdenCliente.porcentaje_comision_vendedor_secundario_snap,
        ).where(*self._no_cancelada(inicio, fin), OrdenCliente.vendedor_secundario_id.is_not(None))
        return [FilaVendedorRol(v, t, p) for v, t, p in self.db.execute(stmt).all()]

    def ventas_totales(self, inicio: date, fin: date) -> tuple[Decimal, int]:
        stmt = select(func.coalesce(func.sum(OrdenCliente.total), 0), func.count()).where(
            *self._no_cancelada(inicio, fin)
        )
        total, cuenta = self.db.execute(stmt).one()
        return Decimal(total or 0), int(cuenta)

    def anunciantes_con_ventas(self, inicio: date, fin: date) -> int:
        stmt = select(func.count(func.distinct(OrdenCliente.anunciante_id))).where(
            *self._no_cancelada(inicio, fin)
        )
        return int(self.db.scalar(stmt) or 0)

    def ventas_por_anunciante(
        self, inicio: date, fin: date
    ) -> list[tuple[uuid.UUID, Decimal, int]]:
        stmt = (
            select(
                OrdenCliente.anunciante_id,
                func.sum(OrdenCliente.total),
                func.count(),
            )
            .where(*self._no_cancelada(inicio, fin))
            .group_by(OrdenCliente.anunciante_id)
            .order_by(func.sum(OrdenCliente.total).desc())
        )
        return [(a, Decimal(v), int(c)) for a, v, c in self.db.execute(stmt).all()]

    def ventas_por_categoria(
        self, inicio: date, fin: date
    ) -> list[tuple[uuid.UUID | None, Decimal]]:
        stmt = (
            select(OrdenCliente.categoria_id, func.sum(OrdenCliente.total))
            .where(*self._no_cancelada(inicio, fin))
            .group_by(OrdenCliente.categoria_id)
            .order_by(func.sum(OrdenCliente.total).desc())
        )
        return [(c, Decimal(v)) for c, v in self.db.execute(stmt).all()]

    def filas_ventas_agencia(
        self, inicio: date, fin: date
    ) -> list[tuple[uuid.UUID | None, Decimal, Decimal | None]]:
        """Una fila por orden (agencia_id, total, % de comisión snap — NULL = Trato
        directo o agencia sin comisión capturada en esa orden). Se prorratea/promedia
        en el service, no aquí (precisión Decimal, ADR-039)."""
        stmt = select(
            OrdenCliente.agencia_id,
            OrdenCliente.total,
            OrdenCliente.porcentaje_comision_agencia_snap,
        ).where(*self._no_cancelada(inicio, fin))
        return [(a, t, p) for a, t, p in self.db.execute(stmt).all()]

    def ventas_por_mes(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(OrdenCliente.total), 0)).where(
            OrdenCliente.estatus_orden != EstatusOrden.CANCELADA.value,
            OrdenCliente.fecha_venta >= inicio,
            OrdenCliente.fecha_venta < fin,
        )
        return Decimal(self.db.scalar(stmt) or 0)

    # ── Dashboard de cobranza (F4-03) ─────────────────────────────────────────────
    def filas_cobranza_abierta(self) -> list[FilaCobranzaAbierta]:
        """Una fila por `CobranzaFactura` NO `cobrada` — saldo (con IVA) ya agregado en
        SQL (SUM de pagos `pagado` vía LEFT JOIN + GROUP BY), nunca una consulta por
        factura (a diferencia de `CobranzaFacturaService.adeudo_vencido`, ADR-277, que
        la ficha pide explícitamente NO reutilizar aquí)."""
        cobrado_expr = func.coalesce(
            func.sum(
                case(
                    (
                        PagoCliente.estatus_pago == EstatusPago.PAGADO.value,
                        PagoCliente.monto_aplicado,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        stmt = (
            select(
                CobranzaFactura.cobranza_id,
                CobranzaFactura.anunciante_id,
                CobranzaFactura.fecha_estimada_cobro,
                FacturaCliente.total_factura,
                cobrado_expr,
            )
            .select_from(CobranzaFactura)
            .join(FacturaCliente, FacturaCliente.factura_id == CobranzaFactura.factura_id)
            .outerjoin(PagoCliente, PagoCliente.cobranza_id == CobranzaFactura.cobranza_id)
            .where(CobranzaFactura.estatus_cobro != EstatusCobro.COBRADA.value)
            .group_by(
                CobranzaFactura.cobranza_id,
                CobranzaFactura.anunciante_id,
                CobranzaFactura.fecha_estimada_cobro,
                FacturaCliente.total_factura,
            )
        )
        return [
            FilaCobranzaAbierta(cid, aid, fec, Decimal(tot), Decimal(cob))
            for cid, aid, fec, tot, cob in self.db.execute(stmt).all()
        ]

    def facturado_con_iva(self, inicio: date, fin: date) -> Decimal:
        """Como `facturado_clientes`, pero con IVA (`total_factura`) — este dashboard,
        a diferencia del P&L, es con IVA (es dinero real a recibir). Usado como
        denominador del DSO global."""
        stmt = select(func.coalesce(func.sum(FacturaCliente.total_factura), 0)).where(
            FacturaCliente.fecha_factura >= inicio,
            FacturaCliente.fecha_factura < fin,
            FacturaCliente.estado_facturacion.in_(_ESTADOS_FACTURADO),
        )
        return Decimal(self.db.scalar(stmt) or 0)

    def facturado_con_iva_por_anunciante(self, inicio: date, fin: date) -> dict[uuid.UUID, Decimal]:
        """Denominador del DSO por anunciante."""
        stmt = (
            select(FacturaCliente.anunciante_id, func.sum(FacturaCliente.total_factura))
            .where(
                FacturaCliente.fecha_factura >= inicio,
                FacturaCliente.fecha_factura < fin,
                FacturaCliente.estado_facturacion.in_(_ESTADOS_FACTURADO),
            )
            .group_by(FacturaCliente.anunciante_id)
        )
        return {aid: Decimal(v) for aid, v in self.db.execute(stmt).all()}

    def cobrado_en_mes(self, inicio: date, fin: date) -> Decimal:
        """Cobrado del mes — CON IVA (este dashboard no es "sin IVA" como el P&L).
        Sin prorrateo: es simplemente lo que entró de efectivo real en el mes. Excluye
        pagos `cancelado` y el pago sintético de una Nota de Crédito (ADR-293, no es
        efectivo real) — pero a propósito NO excluye huérfanos (`cobranza_id IS NULL`,
        ADR-229): a diferencia del "Cobrado" del P&L (que sí los excluye porque
        necesita una factura de la que derivar el sin-IVA), un pago sin asignar sigue
        siendo dinero real ya recibido, y por eso cuenta aquí."""
        stmt = select(func.coalesce(func.sum(PagoCliente.monto_aplicado), 0)).where(
            PagoCliente.fecha_pago_cliente >= inicio,
            PagoCliente.fecha_pago_cliente < fin,
            PagoCliente.estatus_pago == EstatusPago.PAGADO.value,
            PagoCliente.factura_egreso_id.is_(None),
        )
        return Decimal(self.db.scalar(stmt) or 0)

    def facturado_en_mes(self, inicio: date, fin: date) -> Decimal:
        stmt = select(func.coalesce(func.sum(FacturaCliente.subtotal_factura), 0)).where(
            FacturaCliente.fecha_factura >= inicio,
            FacturaCliente.fecha_factura < fin,
            FacturaCliente.estado_facturacion.in_(_ESTADOS_FACTURADO),
        )
        return Decimal(self.db.scalar(stmt) or 0)

    # ── Dashboard operativo (F4-04) ───────────────────────────────────────────────
    def _dias_verificados(self, inicio: date, fin: date) -> tuple[ColumnElement[bool], ...]:
        """El conjunto "día de transmisión ya medido" que comparten cumplimiento e
        incidencias (decisión 2 de Tanda 3): tiene `Verificacion` Y no está
        `cancelada` — mismo filtro `cancelada == False` que usa el resto del sistema
        al sumar spots (`orden_estacion.py`)."""
        return (
            OrdenEstacionDia.cancelada.is_(False),
            OrdenEstacionDia.fecha_transmision >= inicio,
            OrdenEstacionDia.fecha_transmision < fin,
        )

    def cumplimiento_por_estacion(self, inicio: date, fin: date) -> list[FilaCumplimientoEstacion]:
        stmt = (
            select(
                Estacion.estacion_id,
                Estacion.nombre_estacion,
                func.sum(OrdenEstacionDia.spots_asignados),
                func.sum(Verificacion.spots_verificados),
            )
            .select_from(OrdenEstacionDia)
            .join(
                Verificacion,
                Verificacion.orden_estacion_dia_id == OrdenEstacionDia.orden_estacion_dia_id,
            )
            .join(
                OrdenEstacion, OrdenEstacion.orden_estacion_id == OrdenEstacionDia.orden_estacion_id
            )
            .join(Estacion, Estacion.estacion_id == OrdenEstacion.estacion_id)
            .where(*self._dias_verificados(inicio, fin))
            .group_by(Estacion.estacion_id, Estacion.nombre_estacion)
        )
        return [
            FilaCumplimientoEstacion(eid, nombre, int(o), int(e))
            for eid, nombre, o, e in self.db.execute(stmt).all()
        ]

    def oe_verificadas_por_afiliado(self, inicio: date, fin: date) -> dict[uuid.UUID, int]:
        """Denominador de "tasa de incidencias" (ficha: "OE totales del afiliado") y
        también el universo de "Afiliados activos" (su cantidad de llaves) — mismo
        conjunto "día verificado" que `cumplimiento_por_estacion`, para que numerador y
        denominador midan exactamente lo mismo."""
        stmt = (
            select(
                Afiliado.afiliado_id,
                func.count(func.distinct(OrdenEstacion.orden_estacion_id)),
            )
            .select_from(OrdenEstacionDia)
            .join(
                Verificacion,
                Verificacion.orden_estacion_dia_id == OrdenEstacionDia.orden_estacion_dia_id,
            )
            .join(
                OrdenEstacion, OrdenEstacion.orden_estacion_id == OrdenEstacionDia.orden_estacion_id
            )
            .join(Estacion, Estacion.estacion_id == OrdenEstacion.estacion_id)
            .join(Afiliado, Afiliado.afiliado_id == Estacion.afiliado_id)
            .where(*self._dias_verificados(inicio, fin))
            .group_by(Afiliado.afiliado_id)
        )
        return {aid: int(c) for aid, c in self.db.execute(stmt).all()}

    def incidencias_por_afiliado_y_tipo(
        self, inicio: date, fin: date
    ) -> list[FilaIncidenciaAfiliado]:
        stmt = (
            select(
                Afiliado.afiliado_id,
                Afiliado.nombre_afiliado,
                Incidencia.tipo_incidencia,
                func.count(),
            )
            .select_from(Incidencia)
            .join(OrdenEstacion, OrdenEstacion.orden_estacion_id == Incidencia.orden_estacion_id)
            .join(Estacion, Estacion.estacion_id == OrdenEstacion.estacion_id)
            .join(Afiliado, Afiliado.afiliado_id == Estacion.afiliado_id)
            .where(
                Incidencia.fecha_incidencia >= inicio,
                Incidencia.fecha_incidencia < fin,
            )
            .group_by(Afiliado.afiliado_id, Afiliado.nombre_afiliado, Incidencia.tipo_incidencia)
        )
        return [
            FilaIncidenciaAfiliado(aid, nombre, tipo, int(c))
            for aid, nombre, tipo, c in self.db.execute(stmt).all()
        ]

    def composicion_incidencias(self, inicio: date, fin: date) -> dict[str, int]:
        stmt = (
            select(Incidencia.tipo_incidencia, func.count())
            .where(
                Incidencia.fecha_incidencia >= inicio,
                Incidencia.fecha_incidencia < fin,
            )
            .group_by(Incidencia.tipo_incidencia)
        )
        return {t: int(c) for t, c in self.db.execute(stmt).all()}

    # ── Resolución de nombres en lote (sin N+1) ──────────────────────────────────
    def nombres_vendedores(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        stmt = select(Vendedor.vendedor_id, Vendedor.nombre_vendedor).where(
            Vendedor.vendedor_id.in_(ids)
        )
        return {i: n for i, n in self.db.execute(stmt).all()}

    def nombres_anunciantes(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        stmt = select(Anunciante.anunciante_id, Anunciante.nombre_comercial).where(
            Anunciante.anunciante_id.in_(ids)
        )
        return {i: n for i, n in self.db.execute(stmt).all()}

    def nombres_categorias(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        stmt = select(Categoria.categoria_id, Categoria.nombre_categoria).where(
            Categoria.categoria_id.in_(ids)
        )
        return {i: n for i, n in self.db.execute(stmt).all()}

    def nombres_agencias(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        stmt = select(Agencia.agencia_id, Agencia.nombre_agencia).where(Agencia.agencia_id.in_(ids))
        return {i: n for i, n in self.db.execute(stmt).all()}
