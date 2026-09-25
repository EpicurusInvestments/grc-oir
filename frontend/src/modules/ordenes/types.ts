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

/** Producto de TARIFA (spot/mención/control remoto/patrocinio, ADR-097 del catálogo
 * Tarifa) — NO confundir con `OrdenCliente.producto`/`OrdenEstacion.producto` ("Campaña",
 * texto libre heredado de la orden). Se elige por estación desde ADR-102. */
export type ProductoTarifa = "spot" | "mencion" | "control_remoto" | "patrocinio";

/** Duración del spot (catálogo Tarifa) — capturada POR ESTACIÓN (ADR-106), no heredada
 * de `OrdenCliente.duracion_spot`. */
export type DuracionSpot = "20s" | "30s" | "60s";

/** Fila desagregada de programación/transmisión: un día con su horario y spots. */
export interface PeriodoTransmisionRow {
  fecha: string;
  hora_inicio: string;
  hora_termino: string;
  spots_diarios: number;
  /** Solo presente si la fila ya existe en el backend (edición) — lo necesita la
   *  asignación de audio por día (ADR-103, `PUT .../dias/{id}/audio`), que es un
   *  endpoint dedicado, no parte de este objeto. */
  orden_estacion_dia_id?: string;
  /** ADR-103: audio de "Material a Transmitir" que usa ESTE día en particular. `null`/
   *  `undefined` = usa el audio DEFAULT (el primero subido, o el único que haya). */
  orden_estacion_audio_id?: string | null;
  /** ADR-104: `true` = este día ya se canceló ("Cancelar transmisión") — de solo
   *  lectura en la grid, no se vuelve a editar. */
  cancelada?: boolean;
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
  /** Spots que se transmiten y se asignan a OrdenEstacion igual que cualquier otro, pero
   *  no se cobran al cliente (ADR-067): descuentan del subtotal facturable, no de
   *  `total_spots`. Ver `totalesOC` (selectors.ts) para el desglose completo. */
  cantidad_spots_bonificables: number;
  precio_unitario: number;
  /** PARÁMETRO SENSIBLE (snapshot): se pre-llena del catálogo, editable, auditado. */
  porcentaje_comision_vendedor_principal_snap: number | null;
  porcentaje_comision_vendedor_secundario_snap: number | null;
  porcentaje_comision_agencia_snap: number | null;
  observaciones_predefinidas: string;
  observaciones_libres: string;
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

/** Un audio de "Material a Transmitir" (ADR-103). `orden === 0` es el DEFAULT que usa
 *  cualquier día sin override propio (ver `PeriodoTransmisionRow.orden_estacion_audio_id`). */
export interface OrdenEstacionAudio {
  id: string;
  nombre_archivo: string;
  orden: number;
}

/** Un audio de "Evidencias de lo Transmitido" (ADR-119, "Capturar Reales") — lista
 *  PLANA, sin `orden` ni concepto de default (a diferencia de `OrdenEstacionAudio`). */
export interface OrdenEstacionEvidencia {
  id: string;
  nombre_archivo: string;
}

/** ADR-123: "Formato de Horarios Reales" — junto a Evidencias en "Capturar Reales",
 *  misma lista PLANA, pero acepta cualquier formato salvo ejecutables/scripts. */
export interface OrdenEstacionFormatoReal {
  id: string;
  nombre_archivo: string;
}

/** ADR-105/ADR-120: un registro de la bitácora de envíos por correo de los PDFs de
 *  OrdenEstacion — un registro por INTENTO (exitoso o no). `"orden_transmision"` es el
 *  envío "bundle" (PDF Programados + Material a Transmitir, a todos los contactos
 *  activos del afiliado) que dispara el diálogo "Enviar por correo"/"Imprimir" al
 *  generar cualquiera de los 3 PDFs. */
export interface LogEnvioCorreo {
  id: string;
  tipoPdf: "servicio" | "programados" | "reales" | "orden_transmision";
  destinatarioEmail: string;
  usuario: string;
  exitoso: boolean;
  mensajeError: string | null;
  fechaEnvio: string;
}

export interface OrdenEstacion {
  id: string;
  folio_orden_interna: string;
  /** FK a OrdenCliente. */
  orden_id: string;
  estacion_id: string;
  plaza_id: string;
  /** Producto de TARIFA (ADR-102) — spot/mención/control remoto/patrocinio, elegido por
   *  estación. NO confundir con `producto` de OrdenCliente ("Campaña", texto libre): esta
   *  OE no tiene ese campo por separado, solo el heredado de la OC (ver selectors.ts). */
  producto_tarifa?: ProductoTarifa | null;
  /** ADR-106: capturada por estación (ya no heredada de `OrdenCliente.duracion_spot`). */
  duracion_spot: DuracionSpot;
  /** Tarifa pactada con la estación (por spot). */
  precio_spot: number;
  /** Spots que se asignan y transmiten igual que cualquier otro (cuentan para el balance
   *  de spots de la OC) pero no se cobran a la estación (ADR-068): reducen `Importe`, no
   *  los spots asignados. Ver `oiImporte`/`oiSpotsFacturables` (selectors.ts). */
  cantidad_spots_bonificables: number;
  /** % de participación de OIR: (precio_unitario_cliente − precio_spot) / precio_unitario_cliente × 100. */
  porcentaje_participacion_oir: number;
  /** Fuente de verdad de la programación asignada. */
  periodo_transmision: PeriodoTransmisionRow[];
  /** Solo las filas que se modificaron respecto a `periodo_transmision` (2.1 → 2.2). */
  horarios_programados?: PeriodoTransmisionRow[];
  /** Solo las filas que se modificaron respecto a lo programado (2.2 → 2.3). */
  horarios_reales?: PeriodoTransmisionRow[];
  notas_transmision?: string | null;
  /** Clave real del adjunto en el almacenamiento (ver `adapters/adjuntosApi.ts`). */
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
  /** `updated_at` (o `created_at` si no hay) de la OI de origen — no es la "Fecha" que se
   * muestra (esa es `fechaInicio`, de transmisión), es el momento en que la OI llegó a
   * 2.3/reales_conciliados; sirve para ordenar la lista de más reciente a más antigua por
   * cuándo se dio de alta la verificación, no por cuándo se transmitió. */
  actualizadaEn: string;
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
export type OrdenEstacionInput = Pick<
  OrdenEstacion,
  | "estacion_id"
  | "plaza_id"
  | "producto_tarifa"
  | "precio_spot"
  | "cantidad_spots_bonificables"
  | "periodo_transmision"
  | "observaciones_estacion"
> & {
  /** ADR-106: requerido solo al CREAR (el backend lo exige en `OrdenEstacionCreate`,
   *  opcional en `OrdenEstacionUpdate`) — mismo criterio que `producto_tarifa`, que por
   *  la misma razón tampoco se marca requerido aquí (una OE existente sigue editable sin
   *  forzar a volver a elegirlo). */
  duracion_spot?: DuracionSpot;
  /** ADR-102: transitorio (no persiste como campo propio) — requerido SOLO si
   * `precio_spot` no coincide con la tarifa sugerida del catálogo. */
  motivo_cambio_tarifa?: string;
  /** ADR-109: material a transmitir YA subido a S3 durante la captura (antes de que
   *  exista esta OE), vía `subirMaterialStagingApi` — solo lo manda `create()` (el
   *  backend no lo acepta en `update()`, que sigue usando el endpoint dedicado de
   *  siempre). El primero de la lista es el default. */
  audios_staging?: { ref: string; nombre_archivo: string }[];
  /** ADR-121: "Reporte del afiliado" — antes solo se capturaba en el paso manual 2.2
   *  ("Capturar Programados", ya retirado); ahora se adjunta/corrige desde el alta o
   *  edición de la OE, mientras siga en un estado editable (antes de 2.3 Reales). */
  reporte_programados_ref?: string | null;
};
