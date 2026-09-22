/** Tipos de Estación/Emisora, alineados al backend (app/modules/catalogos/estacion.py).
 *
 * ADR-094: pantalla propia (ya no anidada dentro de Afiliados) y `plaza_id` de selección
 * LIBRE (reemplaza la herencia automática de ADR-005) — puede ser distinta a la plaza del
 * afiliado que opera la estación.
 */

import type { CatalogoBase } from "@/shared/types";

export type TipoSenal = "fm" | "am" | "tv";

export interface Estacion extends CatalogoBase {
  estacion_id: string;
  afiliado_id: string;
  plaza_id: string;
  nombre_estacion: string;
  siglas: string | null;
  frecuencia: string | null;
  tipo_senal: TipoSenal;
  // Derivados (solo lectura):
  afiliado_nombre: string | null;
  plaza_nombre: string | null;
}

export interface EstacionCreate {
  afiliado_id: string;
  plaza_id: string;
  nombre_estacion: string;
  siglas?: string | null;
  frecuencia?: string | null;
  tipo_senal: TipoSenal;
}

export type EstacionUpdate = Partial<EstacionCreate>;
