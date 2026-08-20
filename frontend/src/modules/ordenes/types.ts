/** Tipos de la DEMO VISUAL de F1 — Órdenes (prototipo navegable, sin backend).
 *
 * Basados en `docs/referencias/pantallas/Fase_1_-_Ordenes.html` (modelo de estados "v5")
 * y en la tabla de decisiones del prompt de la demo. Datos 100% dummy, en memoria.
 *
 * NO son DTOs reales del backend (a diferencia de los tipos de cada catálogo en
 * `modules/catalogos/`, que sí espejan sus módulos en `backend/app/modules/catalogos/`):
 * F1 real todavía no existe en `backend/`.
 */

/** Estado raíz + sub-estados de OrdenCliente (jerarquía numerada del prototipo aprobado). */
export type EstadoOC =
  | "orden_cliente_sin_vobo"
  | "orden_cliente_con_vobo"
  | "orden_interna"
  | "orden_cerrada"
  | "facturada_archivo_plano"
  | "facturada_timbrada"
  | "cobrada"
  | "cancelada";

/** Sub-estados de OrdenEstacion (viven DENTRO del estado raíz 2 "Orden interna"). */
export type EstadoOI = "asignada_afiliado" | "programados_conciliados" | "reales_conciliados";

export type EstatusPagoAfiliado = "pendiente" | "en_revision" | "pagado";
export type EstatusPagoAgencia = "pendiente" | "en_revision" | "pagado";

/** Fila desagregada de programación/transmisión: un día con su horario y spots. */
export interface PeriodoTransmisionRow {
  fecha: string;
  hora_inicio: string;
  hora_termino: string;
  spots_diarios: number;
}

export interface OrdenCliente {
  id: string;
  folio_orden: string;
  numero_orden_cliente: string;
  fecha_venta: string;
  empresa_facturadora_id: string;
  vendedor_principal_id: string;
  vendedor_secundario_id: string | null;
  anunciante_id: string;
  agencia_id: string | null;
  contrato_id: string | null;
  marca_id: string | null;
  producto: string;
  categoria_id: string | null;
  direccion_facturacion: string;
  facturacion_directa_cliente: boolean;
  afiliado_factura_directo_al_cliente: boolean;
  fecha_inicio_campania: string;
  fecha_fin_campania: string;
  duracion_spot: string;
  total_spots: number;
  precio_unitario: number;
  /** PARÁMETRO SENSIBLE (snapshot): se pre-llena del catálogo, editable, auditado. */
  porcentaje_comision_vendedor_principal_snap: number | null;
  porcentaje_comision_vendedor_secundario_snap: number | null;
  porcentaje_comision_agencia_snap: number | null;
  observaciones_predefinidas: string;
  observaciones_libres: string;
  /** Checklist de Vo.Bo. (PO §2) — claves de `ODC_REVIEW_CHECKLIST`. */
  revision_checklist: Record<string, boolean>;
  estatus_orden: EstadoOC;
  estatus_pago_afiliado: EstatusPagoAfiliado;
  estatus_pago_agencia: EstatusPagoAgencia;
  odc_pdf_ref?: string | null;
  audio_spot_ref?: string | null;
  odc_cerrada_ref?: string | null;
  carta_conciliacion_ref?: string | null;
  /** Qué faltó adjuntar al cierre (se permite cerrar sin ellos, con advertencia). */
  documentos_cierre_faltantes?: ("odc_cerrada" | "carta_conciliacion")[];
  created_by: string;
  created_at: string;
  fecha_cierre?: string | null;
  updated_at?: string | null;
}

export interface OrdenEstacion {
  id: string;
  folio_orden_interna: string;
  /** FK a OrdenCliente. */
  orden_id: string;
  estacion_id: string;
  plaza_id: string;
  /** Tarifa pactada con la estación (por spot). */
  precio_spot: number;
  /** % de participación de OIR: (precio_unitario_cliente − precio_spot) / precio_unitario_cliente × 100. */
  porcentaje_participacion_oir: number;
  /** Fuente de verdad de la programación asignada. */
  periodo_transmision: PeriodoTransmisionRow[];
  /** Solo las filas que se modificaron respecto a `periodo_transmision` (2.1 → 2.2). */
  horarios_programados?: PeriodoTransmisionRow[];
  /** Solo las filas que se modificaron respecto a lo programado (2.2 → 2.3). */
  horarios_reales?: PeriodoTransmisionRow[];
  testigos_url?: string | null;
  testigos_ubicacion_alterna?: string | null;
  notas_transmision?: string | null;
  /** Nombre de archivo simulado (no se sube ni se lee el contenido). */
  reporte_programados_ref?: string | null;
  reporte_reales_ref?: string | null;
  observaciones_estacion?: string;
  estatus: EstadoOI;
  created_at: string;
  updated_at?: string | null;
}

export interface Incidencia {
  id: string;
  orden_interna_id: string;
  tipo: "bonificacion" | "descuento";
  fecha_transmision: string;
  spots_asignados: number;
  spots_reales: number;
  diferencia: number;
  /** = diferencia × precio_spot de la OI. Positivo = bonificación, negativo = descuento. */
  monto_ajuste: number;
  nota_excepcion: string;
  created_at: string;
}

/** Fila de comparación día-a-día para la vista derivada de "Verificaciones" (ver Verificacion). */
export interface VerificacionDiaRow {
  fecha: string;
  programado: PeriodoTransmisionRow;
  real: PeriodoTransmisionRow;
  diferenciaSpots: number;
}

/**
 * "Verificación" — PROYECCIÓN derivada, NO una entidad persistida/mock.
 *
 * El prototipo aprobado trae una entidad "Verificación" completa (`renderVerifDetail`,
 * `captureVerifForm`) pero es código muerto: ningún flujo activo la alimenta y su propio
 * placeholder en pantalla dice que quedó reemplazada por el modelo v5, donde lo real se
 * captura directo en la OrdenEstacion (`horarios_reales`) y al llegar a 2.3 (reales
 * conciliados) ESO ya es la reconciliación.
 *
 * Para la demo, esta vista se CALCULA en `selectors.ts` a partir de cada OrdenEstacion que
 * llegó a 2.3 — no se guarda en `mocks/` ni en el reducer. `reconciliada` es siempre `true`
 * porque llegar a 2.3 ya implica la reconciliación en este modelo.
 *
 * Nota para el equipo (no aplica a la demo): en la especificación BD v2, `Verificacion` SÍ
 * es una tabla con campos propios. Que el prototipo la haya reemplazado por este flujo es
 * una divergencia real entre prototipo y spec que hay que resolver con negocio antes de
 * construir el módulo F1 de verdad.
 */
export interface VerificacionDerivada {
  /** OrdenEstacion de origen (no hay id propio: es una proyección). */
  ordenEstacionId: string;
  folioOrdenInterna: string;
  /** Primer día de transmisión (ISO `YYYY-MM-DD`); la OI puede abarcar varios días —
   * ver `dias` para el detalle completo. */
  fechaInicio: string;
  dias: VerificacionDiaRow[];
  totalProgramado: number;
  totalReal: number;
  reconciliada: true;
}

/** Badge de estado raíz (1–5) o "cancel" para `cancelada`. */
export type RootBadgeKey = 1 | 2 | 3 | 4 | 5 | "cancel";

/** Campos que captura el formulario de alta/edición (Tanda 2). Excluye lo que genera el
 * sistema (folio, id, estatus, auditoría) y lo que solo se llena en el cierre (Tanda 4). */
export type OrdenClienteInput = Omit<
  OrdenCliente,
  | "id"
  | "folio_orden"
  | "estatus_orden"
  | "estatus_pago_afiliado"
  | "estatus_pago_agencia"
  | "created_by"
  | "created_at"
  | "updated_at"
  | "fecha_cierre"
  | "odc_cerrada_ref"
  | "carta_conciliacion_ref"
  | "documentos_cierre_faltantes"
>;

/** Campos que captura el formulario de ALTA de OrdenEstacion (Tanda 3). Excluye lo que
 * genera el sistema (folio, id, orden_id, estatus, % OIR calculado) y lo que solo aparece
 * en Programados/Reales (Tanda 4). */
export type OrdenEstacionInput = Pick<OrdenEstacion, "estacion_id" | "plaza_id" | "precio_spot" | "periodo_transmision" | "observaciones_estacion">;
