/** Tipos de TarifaPlaza, alineados a los schemas del backend
 * (app/modules/catalogos/tarifa.py).
 *
 * Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4).
 *
 * ADR-097 (petición del usuario): ya NO hay vigencia (`vigencia_desde`/`vigencia_hasta`
 * se eliminaron por completo) ni `plaza_id` — la tarifa ahora referencia una Estación
 * ("Nombre de la emisora") y agrega `producto` (spot/mención/control remoto/patrocinio).
 *
 * ADR-098 (petición del usuario): `DuracionSpot` perdió el valor `mencion` — ahora
 * "Mención" solo vive en `ProductoTarifa` (tenerlo también como duración era redundante).
 *
 * ADR-099 (petición del usuario): `tarifa_bruta`/`descuento_pct` son PARÁMETROS
 * SENSIBLES — cada cambio se audita (`HistorialCambio`, mismo mecanismo que
 * Agencia/Vendedor/Contrato). `motivo_cambio` es transitorio (solo en `TarifaPlazaUpdate`,
 * nunca en Create/Read).
 */

import type { CatalogoBase, HistorialCambio } from "@/shared/types";

export type { HistorialCambio };

export type TipoSenal = "fm" | "am" | "tv";
export type DuracionSpot = "20s" | "30s" | "60s";
export type ProductoTarifa = "spot" | "mencion" | "control_remoto" | "patrocinio";

export interface TarifaPlaza extends CatalogoBase {
  tarifa_plaza_id: string;
  estacion_id: string;
  tipo_senal: TipoSenal;
  duracion_spot: DuracionSpot;
  producto: ProductoTarifa;
  tarifa_bruta: string; // Decimal como string
  descuento_pct: string; // Decimal como string
  tarifa_neta: string; // Calculado por el servidor (solo lectura)
  notas: string | null;
  created_by: string | null;
  /** Derivado (solo lectura): nombre de la estación referenciada. */
  estacion_nombre: string | null;
}

export interface TarifaPlazaCreate {
  estacion_id: string;
  tipo_senal: TipoSenal;
  duracion_spot: DuracionSpot;
  producto: ProductoTarifa;
  tarifa_bruta: string; // se envía como string para preservar Decimal
  descuento_pct: string;
  notas?: string | null;
  // tarifa_neta NO se envía: la calcula el servidor.
}

export interface TarifaPlazaUpdate extends Partial<TarifaPlazaCreate> {
  /** Transitorio (no persiste): requerido si `tarifa_bruta`/`descuento_pct` cambian. */
  motivo_cambio?: string | null;
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
];

export const PRODUCTO_OPCIONES: { value: ProductoTarifa; label: string }[] = [
  { value: "spot", label: "Spot" },
  { value: "mencion", label: "Mención" },
  { value: "control_remoto", label: "Control remoto" },
  { value: "patrocinio", label: "Patrocinio" },
];
