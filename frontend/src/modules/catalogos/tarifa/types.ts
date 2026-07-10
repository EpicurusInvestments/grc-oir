/** Tipos de TarifaPlaza, alineados a los schemas del backend
 * (app/modules/catalogos/tarifa.py).
 *
 * Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4);
 * las fechas de vigencia como string ISO `YYYY-MM-DD`.
 */

import type { CatalogoBase, ListParams } from "@/shared/types";

export type TipoSenal = "fm" | "am" | "tv";
export type DuracionSpot = "20s" | "30s" | "60s" | "mencion";

export interface TarifaPlaza extends CatalogoBase {
  tarifa_plaza_id: string;
  plaza_id: string;
  tipo_senal: TipoSenal;
  duracion_spot: DuracionSpot;
  tarifa_bruta: string; // Decimal como string
  descuento_pct: string; // Decimal como string
  tarifa_neta: string; // Calculado por el servidor (solo lectura)
  vigencia_desde: string; // YYYY-MM-DD
  vigencia_hasta: string; // YYYY-MM-DD
  notas: string | null;
  created_by: string | null;
  /** Derivados (solo lectura): datos de la plaza referenciada. */
  plaza_nombre: string | null;
  plaza_estado: string | null;
}

export interface TarifaPlazaCreate {
  plaza_id: string;
  tipo_senal: TipoSenal;
  duracion_spot: DuracionSpot;
  tarifa_bruta: string; // se envía como string para preservar Decimal
  descuento_pct: string;
  vigencia_desde: string;
  vigencia_hasta: string;
  notas?: string | null;
  // tarifa_neta NO se envía: la calcula el servidor.
}

export type TarifaPlazaUpdate = Partial<TarifaPlazaCreate>;

/** Parámetros de lista con filtro por plaza + filtro derivado por vigencia
 * (gemelo de `TarifaListParams` del backend). */
export interface TarifaListParams extends ListParams {
  plaza_id?: string;
  vigencia?: "todas" | "vigente" | "expirada";
}

export const TIPO_SENAL_OPCIONES: { value: TipoSenal; label: string }[] = [
  { value: "fm", label: "FM" },
  { value: "am", label: "AM" },
  { value: "tv", label: "TV" },
];

export const DURACION_SPOT_OPCIONES: { value: DuracionSpot; label: string }[] = [
  { value: "20s", label: "20 segundos" },
  { value: "30s", label: "30 segundos" },
  { value: "60s", label: "60 segundos" },
  { value: "mencion", label: "Mención" },
];
