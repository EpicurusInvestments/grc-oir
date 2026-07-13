/** Tipos de Agencia, alineados a los schemas del backend (app/modules/catalogos/agencia.py).
 *
 * `porcentaje_comision_agencia_default` es un DECIMAL que viaja como STRING (precisión,
 * criterio E-4) y es PARÁMETRO SENSIBLE (auditado).
 */

import type { CatalogoBase } from "@/shared/types";

export interface Agencia extends CatalogoBase {
  agencia_id: string;
  nombre_agencia: string;
  rfc_agencia: string;
  contacto_nombre: string | null;
  contacto_email: string | null;
  contacto_telefono: string | null;
  /** DECIMAL como string (p.ej. "15.00"). Sensible: audit log al modificarlo. */
  porcentaje_comision_agencia_default: string;
  /** Derivado (solo lectura): nº de anunciantes de la agencia (todos). */
  anunciantes_count: number;
}

/** Anunciante mínimo para la sección "Anunciantes representados" del panel de Agencia.
 * (El módulo Anunciante completo llega en la Tanda 5; aquí solo lo que se muestra.) */
export interface AgenciaAnunciante {
  anunciante_id: string;
  nombre_comercial: string;
  rfc_anunciante: string;
  activo: boolean;
}

/** Entrada del historial de auditoría (gemela de `LogCambioParametroRead` del backend). */
export interface HistorialCambio {
  log_cambio_parametro_id: string;
  entidad: string;
  entidad_id: string;
  campo: string;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  usuario: string;
  ip: string | null;
  motivo_cambio: string | null;
  fecha_cambio: string;
}

export interface AgenciaCreate {
  nombre_agencia: string;
  rfc_agencia: string;
  contacto_nombre?: string | null;
  contacto_email?: string | null;
  contacto_telefono?: string | null;
  porcentaje_comision_agencia_default: string;
}

export interface AgenciaUpdate extends Partial<AgenciaCreate> {
  /** Requerido por el backend si se modifica el % (parámetro sensible). */
  motivo_cambio?: string | null;
}
