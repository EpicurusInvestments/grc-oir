/** Tipos de TarifaPlaza, alineados a los schemas del backend
 * (app/modules/catalogos/tarifa.py).
 *
 * Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4).
 *
 * ADR-097 (petición del usuario): ya NO hay vigencia (`vigencia_desde`/`vigencia_hasta`
 * se eliminaron por completo) ni `plaza_id` — la tarifa ahora referencia una Estación
 * ("Nombre de la emisora") y agrega `producto`.
 *
 * ADR-099 (petición del usuario): `tarifa_bruta`/`descuento_pct` son PARÁMETROS
 * SENSIBLES — cada cambio se audita (`HistorialCambio`, mismo mecanismo que
 * Agencia/Vendedor/Contrato). `motivo_cambio` es transitorio (solo en `TarifaPlazaUpdate`,
 * nunca en Create/Read).
 *
 * ADR-158 (petición del usuario): se elimina `tipo_senal` por completo — es propiedad
 * de la Estación (`@/modules/catalogos/estacion/types`), no de la tarifa; mantenerla
 * aquí duplicada permitía capturar un tipo de señal distinto al de la estación
 * seleccionada, sin ningún beneficio (la unicidad/sugerencia ya filtran por
 * `estacion_id`, que determina el tipo de señal por sí solo).
 *
 * ADR-166 (petición del usuario): `duracion_spot`/`producto` dejan de ser los
 * CHECK/enum cerrados y pasan a TEXTO LIBRE — se capturan eligiendo del catálogo
 * `DuracionSpotCatalogo` ("Producto Duración", módulo `catalogos/duracionSpot/`) en vez
 * de un selector fijo. Los tipos/constantes `DuracionSpot`/`ProductoTarifa`/
 * `DURACION_SPOT_OPCIONES`/`PRODUCTO_OPCIONES` que vivían aquí se retiraron (ADR-171):
 * desde ADR-166/169, ninguna pantalla los usa ya (Tarifa, OrdenCliente y OrdenEstacion
 * ya están conectadas al catálogo).
 */

import type { CatalogoBase, HistorialCambio } from "@/shared/types";

export type { HistorialCambio };

export interface TarifaPlaza extends CatalogoBase {
  tarifa_plaza_id: string;
  estacion_id: string;
  duracion_spot: string;
  producto: string;
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
  duracion_spot: string;
  producto: string;
  tarifa_bruta: string; // se envía como string para preservar Decimal
  descuento_pct: string;
  notas?: string | null;
  // tarifa_neta NO se envía: la calcula el servidor.
}

export interface TarifaPlazaUpdate extends Partial<TarifaPlazaCreate> {
  /** Transitorio (no persiste): requerido si `tarifa_bruta`/`descuento_pct` cambian. */
  motivo_cambio?: string | null;
}
