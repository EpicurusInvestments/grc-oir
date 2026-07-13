/** Tipos de Contrato, alineados al backend (app/modules/catalogos/contrato.py).
 *
 * `porcentaje_comision_contrato` es PARÁMETRO SENSIBLE (auditado) y viaja como string
 * (nullable). `estado_contrato` es una máquina de estados independiente de `activo`.
 */

import type { CatalogoBase } from "@/shared/types";

export type EstadoContrato = "vigente" | "suspendido" | "finalizado" | "cancelado";

export interface Contrato extends CatalogoBase {
  contrato_id: string;
  anunciante_id: string;
  numero_contrato: string;
  nombre_contrato: string;
  fecha_inicio_contrato: string;
  fecha_fin_contrato: string;
  monto_contrato: string | null;
  porcentaje_comision_contrato: string | null;
  condiciones_comerciales: string | null;
  estado_contrato: EstadoContrato;
  archivo_contrato_path: string | null;
  observaciones_contrato: string | null;
  created_by: string | null;
  // Derivados (solo lectura):
  anunciante_nombre: string | null;
  anunciante_rfc: string | null;
}

export interface ContratoCreate {
  anunciante_id: string;
  numero_contrato: string;
  nombre_contrato: string;
  fecha_inicio_contrato: string;
  fecha_fin_contrato: string;
  monto_contrato?: string | null;
  porcentaje_comision_contrato?: string | null;
  condiciones_comerciales?: string | null;
  observaciones_contrato?: string | null;
}

export interface ContratoUpdate extends Partial<ContratoCreate> {
  /** Requerido por el backend si se modifica el % de comisión (sensible). */
  motivo_cambio?: string | null;
}

/** Transiciones permitidas desde cada estado (gemelo de `TRANSICIONES` del backend). */
export const TRANSICIONES: Record<EstadoContrato, EstadoContrato[]> = {
  vigente: ["suspendido", "finalizado", "cancelado"],
  suspendido: ["vigente", "cancelado"],
  finalizado: ["cancelado"],
  cancelado: [],
};

/** Etiqueta del botón de acción para transicionar a cada estado destino. */
export const ACCION_ESTADO: Record<EstadoContrato, string> = {
  vigente: "Reactivar",
  suspendido: "Suspender",
  finalizado: "Finalizar",
  cancelado: "Cancelar",
};

/** Clase de badge por estado (consistente con el mock aprobado). */
export const ESTADO_BADGE: Record<EstadoContrato, string> = {
  vigente: "b-green",
  suspendido: "b-amber",
  finalizado: "b-gray",
  cancelado: "b-red",
};
