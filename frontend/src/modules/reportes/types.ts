/** Tipos de F4-01 (Estado de resultados) — alineados a
 * `backend/app/modules/reportes/schemas.py`. Montos como `string` (precisión Decimal,
 * mismo criterio que el resto del backend). */

export interface RenglonFacturadoPagado {
  facturado: string;
  pagado: string;
}

export interface EstadoResultadosPeriodo {
  periodo: string; // "YYYY-MM"
  en_curso: boolean;

  ingresos_facturado: string;
  ingresos_cobrado: string;

  costos_afiliados: RenglonFacturadoPagado;
  costos_agencias: RenglonFacturadoPagado;
  costos_comisiones_vendedores: RenglonFacturadoPagado;
  costo_comisiones_agencias_pagado: string;

  costo_nominas: string;
  costo_overhead: string;

  utilidad_bruta: string;
  utilidad_neta: string;

  margen_bruto_pct: string | null;
  margen_neto_pct: string | null;
  pct_cobranza: string | null;
  costo_afiliados_pct_cobrado: string | null;
}

export interface TendenciaPct {
  ingresos_cobrado_pct: string | null;
  utilidad_bruta_pct: string | null;
  utilidad_neta_pct: string | null;
}

export interface EstadoResultadosRead {
  actual: EstadoResultadosPeriodo;
  anterior: EstadoResultadosPeriodo;
  tendencia: TendenciaPct;
  historico: EstadoResultadosPeriodo[];
}

export type FormatoExportacion = "xlsx" | "csv";

// ── Dashboard comercial (F4-02) ──────────────────────────────────────────────────
export type VentanaComercial = "ytd" | "mes" | "trimestre";

export interface VentaMensual {
  periodo: string;
  ventas: string;
}

export interface VentasPorVendedor {
  vendedor_id: string;
  nombre: string;
  ventas: string;
  ordenes: number;
  comision_total: string;
}

export interface VentasPorAnunciante {
  anunciante_id: string;
  nombre: string;
  ventas: string;
  ordenes: number;
}

export interface VentasPorCategoria {
  categoria_id: string | null;
  nombre: string;
  ventas: string;
  pct: string | null;
}

export interface VentasPorAgencia {
  agencia_id: string | null;
  nombre: string;
  ventas: string;
  comision_pct: string | null;
  comision: string;
}

export interface DashboardComercialRead {
  ventana: VentanaComercial;
  periodo: string;
  desde: string;
  hasta: string;

  ventas_total: string;
  ordenes_total: number;
  ticket_promedio: string | null;
  comisiones_vendedores_total: string;
  anunciantes_con_ventas: number;

  top_vendedores: VentasPorVendedor[];
  top_anunciantes: VentasPorAnunciante[];
  top_categorias: VentasPorCategoria[];
  top_agencias: VentasPorAgencia[];
  evolucion_mensual: VentaMensual[];
}

// ── Dashboard de cobranza (F4-03) ────────────────────────────────────────────────
export type AgingBucket = "corriente" | "1-30" | "31-60" | "61-90" | "90+";

export interface AgingCubeta {
  bucket: AgingBucket;
  importe: string;
  count: number;
}

export interface CobranzaPorAnunciante {
  anunciante_id: string;
  nombre: string;
  por_cobrar: string;
  vencido: string;
  dso: string | null;
}

export interface CobradoFacturadoMensual {
  periodo: string;
  facturado: string;
  cobrado: string;
}

export interface DashboardCobranzaRead {
  fecha_corte: string;
  mes_cobrado: string;
  ventana_dso_dias: number;

  total_por_cobrar: string;
  total_vencido: string;
  total_facturas: number;
  dso_promedio: string | null;
  cobrado_mes: string;

  aging: AgingCubeta[];
  por_anunciante: CobranzaPorAnunciante[];
  evolucion_mensual: CobradoFacturadoMensual[];
}

// ── Dashboard operativo (F4-04) ──────────────────────────────────────────────────
export type TipoIncidencia =
  | "faltante"
  | "excedente"
  | "cambio_horario"
  | "cambio_fecha"
  | "spot_no_emitido";

export interface CumplimientoEstacion {
  estacion_id: string;
  nombre_estacion: string;
  ordenado: number;
  ejecutado: number;
  pct_cumplimiento: string | null;
}

export interface IncidenciasPorTipo {
  tipo_incidencia: TipoIncidencia;
  total: number;
  pct: string | null;
}

export interface IncidenciasPorAfiliado {
  afiliado_id: string;
  nombre_afiliado: string;
  total: number;
  faltantes: number;
  excedentes: number;
  cambios_horario: number;
  cambios_fecha: number;
  spots_no_emitidos: number;
  oe_totales: number;
  tasa_pct: string | null;
  alerta: boolean;
}

export interface DashboardOperativoRead {
  ventana: VentanaComercial;
  periodo: string;
  desde: string;
  hasta: string;

  cumplimiento_general_pct: string | null;
  spots_ordenados_total: number;
  spots_transmitidos_total: number;
  incidencias_total: number;
  afiliados_activos: number;

  cumplimiento_por_estacion: CumplimientoEstacion[];
  incidencias_por_afiliado: IncidenciasPorAfiliado[];
  composicion_incidencias: IncidenciasPorTipo[];
}
