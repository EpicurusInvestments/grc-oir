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
  /** Domicilio ESTRUCTURADO (ADR-175, mismo mecanismo que ADR-059 en Anunciante):
   * autocompletado por código postal contra `asentamiento_postal`. */
  calle: string | null;
  numero_exterior: string | null;
  numero_interior: string | null;
  colonia: string | null;
  localidad: string | null;
  referencia_domicilio: string | null;
  municipio: string | null;
  estado: string | null;
  pais: string | null;
  codigo_postal: string | null;
  /** Clave SAT (c_RegimenFiscal) cuando la agencia es RECEPTORA (trato vía agencia),
   * sugerida desde ConstantesSistema; sin FK. */
  regimen_fiscal: string | null;
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

/** Historial de auditoría: DTO compartido (movido a shared/types en la Tanda 5). */
export type { HistorialCambio } from "@/shared/types";

export interface AgenciaCreate {
  nombre_agencia: string;
  rfc_agencia: string;
  calle?: string | null;
  numero_exterior?: string | null;
  numero_interior?: string | null;
  colonia?: string | null;
  localidad?: string | null;
  referencia_domicilio?: string | null;
  municipio?: string | null;
  estado?: string | null;
  pais?: string | null;
  codigo_postal?: string | null;
  regimen_fiscal?: string | null;
  porcentaje_comision_agencia_default: string;
}

export interface AgenciaUpdate extends Partial<AgenciaCreate> {
  /** Requerido por el backend si se modifica el % (parámetro sensible). */
  motivo_cambio?: string | null;
}

// ── ContactoAgencia (anidado en Agencia — entidad nueva) ───────────────────────────
// ADR-174: el contacto único legado (`contacto_nombre`/`contacto_email`/
// `contacto_telefono`) se eliminó por completo. Este es el "varios contactos", mismo
// patrón anidado que `ContactoAnunciante`.
export interface ContactoAgencia extends CatalogoBase {
  contacto_agencia_id: string;
  agencia_id: string;
  nombre_contacto: string;
  puesto_contacto: string | null;
  telefono_contacto: string | null;
  email_contacto: string | null;
}

export interface ContactoAgenciaCreate {
  agencia_id: string;
  nombre_contacto: string;
  puesto_contacto?: string | null;
  telefono_contacto?: string | null;
  email_contacto?: string | null;
}

export type ContactoAgenciaUpdate = Partial<Omit<ContactoAgenciaCreate, "agencia_id">> & {
  agencia_id?: string;
};
