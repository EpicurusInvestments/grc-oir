/** Constantes centralizadas de la demo F1 — Órdenes.
 *
 * Ninguna fórmula/estado se escribe "a mano" en los componentes: todo sale de aquí.
 * Fuente: prototipo aprobado + tabla de decisiones del prompt de la demo.
 */

import type { EstadoOC, EstadoOI, RootBadgeKey } from "./types";

/** Única fuente del 16% de IVA (nunca escrito a mano en un cálculo). */
export const IVA_RATE = 0.16;

export const DURACIONES_SPOT = ["10s", "15s", "20s", "30s", "40s", "45s", "60s", "90s"] as const;

export const OBS_PREDEFINIDAS = [
  "Sujeto a disponibilidad de horarios prime",
  "No combinable con otros descuentos",
  "Tarifa especial por campaña anual",
] as const;

/* ─────────────────────────────────────────────────────────────────────────────
 * Modelo de estados v5 — jerarquía numerada de 5 raíces.
 * ───────────────────────────────────────────────────────────────────────────── */

export const STATUS_LABELS: Record<EstadoOC | EstadoOI, string> = {
  orden_cliente_sin_vobo: "1.1 ODC sin Vo.Bo.",
  orden_cliente_con_vobo: "1.2 Con Vo.Bo.",
  orden_interna: "2 Orden interna",
  orden_cerrada: "3 Orden cerrada",
  facturada_archivo_plano: "4.1 Archivo plano",
  facturada_timbrada: "4.2 Factura timbrada",
  cobrada: "5 Cobrada",
  cancelada: "Cancelada",
  asignada_afiliado: "2.1 Asignada al afiliado",
  programados_conciliados: "2.2 Programados conciliados",
  reales_conciliados: "2.3 Reales conciliados",
};

export const ROOT_STATE: Record<EstadoOC, number | null> = {
  orden_cliente_sin_vobo: 1,
  orden_cliente_con_vobo: 1,
  orden_interna: 2,
  orden_cerrada: 3,
  facturada_archivo_plano: 4,
  facturada_timbrada: 4,
  cobrada: 5,
  cancelada: null,
};

export const ROOT_LABEL: Record<number, string> = {
  1: "Orden cliente",
  2: "Orden interna",
  3: "Orden cerrada",
  4: "Facturada",
  5: "Cobrada",
};

export function rootState(estatus: EstadoOC): number | null {
  return ROOT_STATE[estatus] ?? null;
}

export function rootLabel(estatus: EstadoOC): string {
  const r = rootState(estatus);
  return r ? `${r} · ${ROOT_LABEL[r]}` : STATUS_LABELS[estatus];
}

/** Flujos para steppers/transiciones (orden fijo de la jerarquía v5). */
export const STATUS_FLOW_OC: EstadoOC[] = [
  "orden_cliente_sin_vobo",
  "orden_cliente_con_vobo",
  "orden_interna",
  "orden_cerrada",
  "facturada_archivo_plano",
  "facturada_timbrada",
  "cobrada",
];
export const STATUS_FLOW_OI: EstadoOI[] = [
  "asignada_afiliado",
  "programados_conciliados",
  "reales_conciliados",
];

/**
 * Estados en los que la OrdenCliente se muestra en modo lectura ("congelada").
 * Definidos por el prompt de la demo — NO copiados del prototipo HTML: el prototipo trae
 * `['orden_cerrada','facturada','cobrada']`, con `'facturada'` un valor que NI SIQUIERA
 * existe en `STATUS_LABELS`/`EstadoOC` (bug del HTML aprobado). Se reporta aparte; aquí se
 * usa la lista correcta.
 */
export const FROZEN_STATES: EstadoOC[] = [
  "orden_cerrada",
  "facturada_archivo_plano",
  "facturada_timbrada",
  "cobrada",
];

/* ─────────────────────────────────────────────────────────────────────────────
 * Badges — reutilizan las clases genéricas `.badge .b-*` de theme.css (no se
 * inventan clases `.st-*`/`.root-st-*` dedicadas, a diferencia del prototipo).
 * ───────────────────────────────────────────────────────────────────────────── */

export const ROOT_BADGE_CLASS: Record<RootBadgeKey, string> = {
  1: "b-red",
  2: "b-blue",
  3: "b-teal",
  4: "b-purple",
  5: "b-dark",
  cancel: "b-gray",
};

/** `rootState()` devuelve `number | null` (no un literal 1-5): esta función hace el puente
 * seguro hacia `ROOT_BADGE_CLASS` sin perder el chequeo de tipos de las claves conocidas. */
export function rootBadgeClass(root: number | null): string {
  const key = (root ?? "cancel") as RootBadgeKey;
  return ROOT_BADGE_CLASS[key] ?? "b-gray";
}

export const ESTADO_OC_BADGE_CLASS: Record<EstadoOC, string> = {
  orden_cliente_sin_vobo: "b-red",
  orden_cliente_con_vobo: "b-amber",
  orden_interna: "b-blue",
  orden_cerrada: "b-teal",
  facturada_archivo_plano: "b-purple",
  facturada_timbrada: "b-purple",
  cobrada: "b-dark",
  cancelada: "b-gray",
};

export const ESTADO_OI_BADGE_CLASS: Record<EstadoOI, string> = {
  asignada_afiliado: "b-blue",
  programados_conciliados: "b-amber",
  reales_conciliados: "b-teal",
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Checklist de revisión PO §2 — recepción de ODC del cliente (transición 1.1 → 1.2).
 * ───────────────────────────────────────────────────────────────────────────── */

export interface ChecklistItem {
  key: string;
  label: string;
}

export const ODC_REVIEW_CHECKLIST: ChecklistItem[] = [
  { key: "razon_social", label: "Razón social del cliente correcta" },
  { key: "plaza", label: "Plaza(s) solicitada(s)" },
  { key: "emisora", label: "Emisora(s) solicitada(s)" },
  { key: "duracion", label: "Duración del spot" },
  { key: "tarifa", label: "Tarifa negociada coincide" },
  { key: "distribucion", label: "Distribución de pauta clara" },
  { key: "horario", label: "Horario solicitado especificado" },
  { key: "importes", label: "Importes / IVA / Totales cuadran" },
  { key: "audio", label: "Audio del spot revisado (duración + audible)" },
  { key: "odc_firmada", label: "ODC firmada y devuelta con Vo.Bo." },
];

export function isChecklistComplete(checklist: Record<string, boolean> | undefined): boolean {
  if (!checklist) return false;
  return ODC_REVIEW_CHECKLIST.every((it) => checklist[it.key] === true);
}

export function checklistProgress(checklist: Record<string, boolean> | undefined): number {
  if (!checklist) return 0;
  return ODC_REVIEW_CHECKLIST.filter((it) => checklist[it.key] === true).length;
}
