/** Tipos de DuracionSpotCatalogo, alineados al backend
 * (app/modules/catalogos/duracion_spot_catalogo.py).
 *
 * ADR-159 (petición del usuario): catálogo NUEVO, fuera de la spec BD v2 y DESCONECTADO
 * del enum `DuracionSpot` que usan Tarifa/Órdenes (ese enum no se toca). Reusa el tipo
 * `ProductoTarifa` ya existente — no se duplica. `descripcion_duracion` es texto libre
 * (no un enum cerrado) para poder agregar valores nuevos sin tocar código.
 */

import type { ProductoTarifa } from "@/modules/catalogos/tarifa/types";
import type { CatalogoBase } from "@/shared/types";

export type { ProductoTarifa };

export interface DuracionSpotCatalogo extends CatalogoBase {
  duracion_spot_catalogo_id: string;
  producto: ProductoTarifa;
  descripcion_duracion: string;
}

export interface DuracionSpotCatalogoCreate {
  producto: ProductoTarifa;
  descripcion_duracion: string;
}

export type DuracionSpotCatalogoUpdate = Partial<DuracionSpotCatalogoCreate>;
