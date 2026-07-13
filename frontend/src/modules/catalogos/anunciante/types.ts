/** Tipos de Anunciante + Marca anidada, alineados al backend
 * (app/modules/catalogos/anunciante.py).
 *
 * `dias_credito_default` es PARÁMETRO SENSIBLE (auditado). `agencia_id` nulo = anunciante
 * directo (sin agencia).
 */

import type { CatalogoBase } from "@/shared/types";

export interface Anunciante extends CatalogoBase {
  anunciante_id: string;
  agencia_id: string | null;
  nombre_comercial: string;
  nombre_fiscal: string;
  rfc_anunciante: string;
  localizacion: string | null;
  referencia_anunciante: string | null;
  contacto_nombre: string | null;
  contacto_email: string | null;
  contacto_telefono: string | null;
  dias_credito_default: number;
  // Derivados (solo lectura):
  agencia_nombre: string | null; // nombre_agencia (null si es directo)
  marcas_count: number;
}

export interface AnuncianteCreate {
  agencia_id?: string | null;
  nombre_comercial: string;
  nombre_fiscal: string;
  rfc_anunciante: string;
  localizacion?: string | null;
  referencia_anunciante?: string | null;
  contacto_nombre?: string | null;
  contacto_email?: string | null;
  contacto_telefono?: string | null;
  dias_credito_default: number;
}

export interface AnuncianteUpdate extends Partial<AnuncianteCreate> {
  /** Requerido por el backend si se modifica `dias_credito_default` (sensible). */
  motivo_cambio?: string | null;
}

/** Filtro derivado de la lista (gemelo de `AnuncianteListParams.relacion`). */
export type Relacion = "todas" | "via_agencia" | "directo";

// ── Marca (anidada en Anunciante) ────────────────────────────────────────────────
export interface Marca extends CatalogoBase {
  marca_id: string;
  anunciante_id: string;
  nombre_marca: string;
}

export interface MarcaCreate {
  anunciante_id: string;
  nombre_marca: string;
}

export type MarcaUpdate = Partial<Omit<MarcaCreate, "anunciante_id">> & {
  anunciante_id?: string;
};

/** Contrato mínimo para la sección "Contratos" del panel (lectura). El módulo Contrato
 * completo llega en la Tanda 6. */
export interface AnuncianteContrato extends CatalogoBase {
  contrato_id: string;
  numero_contrato: string;
  nombre_contrato: string;
  fecha_inicio_contrato: string;
  fecha_fin_contrato: string;
  monto_contrato: string | null;
  estado_contrato: "vigente" | "suspendido" | "finalizado" | "cancelado";
}
