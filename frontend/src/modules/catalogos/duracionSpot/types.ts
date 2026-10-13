/** Tipos de DuracionSpotCatalogo, alineados al backend
 * (app/modules/catalogos/duracion_spot_catalogo.py).
 *
 * ADR-159 (petición del usuario): catálogo NUEVO, fuera de la spec BD v2 y DESCONECTADO
 * del enum `DuracionSpot` que usan Tarifa/Órdenes (ese enum no se toca).
 * ADR-164 (petición del usuario): `producto` dejó de reusar el enum `ProductoTarifa` de
 * Tarifa — ahora es texto libre, igual que `descripcion_duracion`, para poder dar de
 * alta productos nuevos sin tocar código.
 * ADR-165 (petición del usuario): `descripcion_duracion` pasa a ser OPCIONAL — vacía se
 * guarda como el literal `SIN_RESULTADO` (equivale a nulo).
 */

import type { CatalogoBase } from "@/shared/types";

/** Literal que sustituye a una `descripcion_duracion` no capturada (ADR-165). Tarifa
 *  (`tarifa/components/TarifaForm.tsx`, ADR-166) lo excluye de sus opciones de Duración. */
export const SIN_RESULTADO = "sin resultado";

export interface DuracionSpotCatalogo extends CatalogoBase {
  duracion_spot_catalogo_id: string;
  producto: string;
  descripcion_duracion: string;
}

export interface DuracionSpotCatalogoCreate {
  producto: string;
  descripcion_duracion: string;
}

export type DuracionSpotCatalogoUpdate = Partial<DuracionSpotCatalogoCreate>;
