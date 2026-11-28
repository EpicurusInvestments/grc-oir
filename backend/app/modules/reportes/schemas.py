"""Schemas de salida del módulo `reportes` (F4-01 — Estado de resultados).

F4 es 100% lectura: no hay `Create`/`Update`, solo DTOs de respuesta. Los montos viajan
como `Decimal` (Pydantic los serializa como string, mismo criterio que el resto del
backend — precisión real, nunca float).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel


class RenglonFacturadoPagado(BaseModel):
    """Un costo directo con sus dos subrenglones (Facturado en el periodo / Pagado en
    el periodo). El subrenglón *Facturado* es informativo — no entra a la fórmula de
    utilidad bruta (que usa base caja, solo *Pagado*)."""

    facturado: Decimal
    pagado: Decimal


class EstadoResultadosPeriodo(BaseModel):
    """Un mes completo del Estado de Resultados — se reutiliza para el periodo
    solicitado, el periodo anterior (para la tendencia) y cada fila del histórico."""

    periodo: str  # "YYYY-MM"
    en_curso: bool

    ingresos_facturado: Decimal
    ingresos_cobrado: Decimal

    costos_afiliados: RenglonFacturadoPagado
    costos_agencias: RenglonFacturadoPagado
    costos_comisiones_vendedores: RenglonFacturadoPagado
    # Sin factura ligada (comision_agencia, sin factura_agencia_id): solo "Pagado".
    costo_comisiones_agencias_pagado: Decimal

    costo_nominas: Decimal
    costo_overhead: Decimal

    utilidad_bruta: Decimal
    utilidad_neta: Decimal

    margen_bruto_pct: Decimal | None
    margen_neto_pct: Decimal | None
    pct_cobranza: Decimal | None
    costo_afiliados_pct_cobrado: Decimal | None


class TendenciaPct(BaseModel):
    """% de cambio del periodo solicitado contra el periodo anterior. `None` si el
    periodo anterior fue 0 (no hay base para calcular un porcentaje)."""

    ingresos_cobrado_pct: Decimal | None
    utilidad_bruta_pct: Decimal | None
    utilidad_neta_pct: Decimal | None


class EstadoResultadosRead(BaseModel):
    actual: EstadoResultadosPeriodo
    anterior: EstadoResultadosPeriodo
    tendencia: TendenciaPct
    # 6 meses, orden cronológico ascendente, el periodo solicitado incluido al final.
    historico: list[EstadoResultadosPeriodo]


# ── Dashboard comercial (F4-02) ──────────────────────────────────────────────────
class VentaMensual(BaseModel):
    periodo: str
    ventas: Decimal


class VentasPorVendedor(BaseModel):
    vendedor_id: uuid.UUID
    nombre: str
    ventas: Decimal  # solo como PRINCIPAL (una orden no se cuenta dos veces)
    ordenes: int  # órdenes donde fue principal
    comision_total: Decimal  # principal + secundario (el vendedor es uno solo)


class VentasPorAnunciante(BaseModel):
    anunciante_id: uuid.UUID
    nombre: str
    ventas: Decimal
    ordenes: int


class VentasPorCategoria(BaseModel):
    categoria_id: uuid.UUID | None
    nombre: str  # "Sin categoría" si `categoria_id` es NULL
    ventas: Decimal
    pct: Decimal | None  # % del total de ventas de la ventana


class VentasPorAgencia(BaseModel):
    agencia_id: uuid.UUID | None
    nombre: str  # "Trato directo" si `agencia_id` es NULL
    ventas: Decimal
    comision_pct: Decimal | None  # promedio ponderado de `porcentaje_comision_agencia_snap`
    comision: Decimal  # 0 para "Trato directo"


class DashboardComercialRead(BaseModel):
    ventana: str  # "ytd" | "mes" | "trimestre"
    periodo: str  # "YYYY-MM" de referencia
    desde: str  # fecha ISO del inicio de la ventana
    hasta: str  # fecha ISO (exclusiva) del fin de la ventana

    ventas_total: Decimal
    ordenes_total: int
    ticket_promedio: Decimal | None
    comisiones_vendedores_total: Decimal
    anunciantes_con_ventas: int

    top_vendedores: list[VentasPorVendedor]
    top_anunciantes: list[VentasPorAnunciante]
    top_categorias: list[VentasPorCategoria]
    top_agencias: list[VentasPorAgencia]
    evolucion_mensual: list[VentaMensual]  # 6 meses


# ── Dashboard de cobranza (F4-03) ────────────────────────────────────────────────
class AgingCubeta(BaseModel):
    bucket: str  # "corriente" | "1-30" | "31-60" | "61-90" | "90+"
    importe: Decimal
    count: int


class CobranzaPorAnunciante(BaseModel):
    anunciante_id: uuid.UUID
    nombre: str
    por_cobrar: Decimal
    vencido: Decimal
    dso: Decimal | None


class CobradoFacturadoMensual(BaseModel):
    periodo: str
    facturado: Decimal
    cobrado: Decimal


class DashboardCobranzaRead(BaseModel):
    """"Al corte" de hoy — no es un periodo seleccionable como el P&L. Montos CON IVA
    (a diferencia del Estado de resultados): es dinero real a recibir."""

    fecha_corte: str  # ISO, hoy
    mes_cobrado: str  # "YYYY-MM" del KPI "Cobrado del mes"
    ventana_dso_dias: int  # default 90

    total_por_cobrar: Decimal
    total_vencido: Decimal
    total_facturas: int
    dso_promedio: Decimal | None
    cobrado_mes: Decimal

    aging: list[AgingCubeta]
    por_anunciante: list[CobranzaPorAnunciante]
    evolucion_mensual: list[CobradoFacturadoMensual]  # 6 meses


# ── Dashboard operativo (F4-04) ──────────────────────────────────────────────────
class CumplimientoEstacion(BaseModel):
    estacion_id: uuid.UUID
    nombre_estacion: str
    ordenado: int  # spots_asignados (sin bonificables), solo días ya verificados
    ejecutado: int  # spots_verificados de esos mismos días
    pct_cumplimiento: Decimal | None


class IncidenciasPorTipo(BaseModel):
    tipo_incidencia: str
    total: int
    pct: Decimal | None  # % del total de incidencias de la ventana


class IncidenciasPorAfiliado(BaseModel):
    afiliado_id: uuid.UUID
    nombre_afiliado: str
    total: int
    faltantes: int
    excedentes: int
    cambios_horario: int
    cambios_fecha: int
    spots_no_emitidos: int
    oe_totales: int  # OE con al menos un día verificado en la ventana
    tasa_pct: Decimal | None  # total / oe_totales * 100
    alerta: bool  # tasa_pct > 10


class DashboardOperativoRead(BaseModel):
    ventana: str  # "ytd" | "mes" | "trimestre"
    periodo: str  # "YYYY-MM" de referencia
    desde: str
    hasta: str

    cumplimiento_general_pct: Decimal | None
    spots_ordenados_total: int
    spots_transmitidos_total: int
    incidencias_total: int
    afiliados_activos: int  # con actividad (días verificados) en la ventana

    cumplimiento_por_estacion: list[CumplimientoEstacion]
    incidencias_por_afiliado: list[IncidenciasPorAfiliado]
    composicion_incidencias: list[IncidenciasPorTipo]
