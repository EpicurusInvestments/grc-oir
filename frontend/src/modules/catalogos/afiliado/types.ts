/** Tipos de Afiliado y Estación, alineados a los schemas del backend
 * (app/modules/catalogos/afiliado.py y estacion.py). La Estación se administra ANIDADA
 * dentro del Afiliado (no tiene pantalla propia); por eso viven en el mismo módulo.
 */

import type { CatalogoBase } from "@/shared/types";

export interface Afiliado extends CatalogoBase {
  afiliado_id: string;
  nombre_afiliado: string;
  razon_social_afiliado: string;
  rfc_afiliado: string;
  plaza_id: string;
  contacto_nombre: string | null;
  contacto_email: string | null;
  contacto_telefono: string | null;
  /** Derivados (solo lectura): nombre de la plaza referenciada y nº de estaciones. */
  plaza_nombre: string | null;
  estaciones_count: number;
}

export interface AfiliadoCreate {
  nombre_afiliado: string;
  razon_social_afiliado: string;
  rfc_afiliado: string;
  plaza_id: string;
  contacto_nombre?: string | null;
  contacto_email?: string | null;
  contacto_telefono?: string | null;
}

export type AfiliadoUpdate = Partial<AfiliadoCreate>;

export type TipoSenal = "fm" | "am" | "tv";

export interface Estacion extends CatalogoBase {
  estacion_id: string;
  afiliado_id: string;
  plaza_id: string; // heredada del afiliado (no se captura)
  nombre_estacion: string;
  frecuencia: string | null;
  tipo_senal: TipoSenal;
}

export interface EstacionCreate {
  afiliado_id: string;
  nombre_estacion: string;
  frecuencia?: string | null;
  tipo_senal: TipoSenal;
}

export type EstacionUpdate = Partial<Omit<EstacionCreate, "afiliado_id">> & {
  afiliado_id?: string;
};
