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
 *
 * ADR-177 (petición del usuario): se agrega `anunciante_id` (selector de Anunciante,
 * PRIMER campo del formulario) — la llave de la tarifa pasa de (Emisora+Producto+
 * Duración) a (Anunciante+Emisora+Producto+Duración). La lista se ordena por
 * Anunciante → Emisora → Producto → Duración.
 */

import type { CatalogoBase, HistorialCambio } from "@/shared/types";

export type { HistorialCambio };

export interface TarifaPlaza extends CatalogoBase {
  tarifa_plaza_id: string;
  /** ADR-177 (petición del usuario): `null` SOLO en las tarifas capturadas ANTES de
   *  este campo (desactivadas por la migración) — toda tarifa nueva siempre lo trae. */
  anunciante_id: string | null;
  estacion_id: string;
  duracion_spot: string;
  producto: string;
  tarifa_bruta: string; // Decimal como string
  descuento_pct: string; // Decimal como string
  tarifa_neta: string; // Calculado por el servidor (solo lectura)
  notas: string | null;
  created_by: string | null;
  // Derivados (solo lectura):
  /** Nombre de la estación referenciada. */
  estacion_nombre: string | null;
  /** ADR-177: nombre del anunciante referenciado; `null` junto con `anunciante_id`. */
  anunciante_nombre: string | null;
}

export interface TarifaPlazaCreate {
  // ADR-177 (petición del usuario): obligatorio — Anunciante pasa a ser parte de la
  // llave de la tarifa (Anunciante + Emisora + Producto + Duración).
  anunciante_id: string;
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
