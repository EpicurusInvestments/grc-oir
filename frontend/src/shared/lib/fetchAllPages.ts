/** Trae TODAS las páginas de un listado paginado (`Page<T>`) y las concatena.
 *
 * Para pantallas normales de catálogo se usa la paginación real (`useCatalog`). Esto es
 * para los pocos casos que necesitan el conjunto COMPLETO en memoria de una sola vez
 * (p.ej. poblar catálogos de referencia o el estado inicial del modo `api` de Órdenes,
 * Tanda 4) — nunca para listas grandes sin acotar.
 */

import type { ListParams, Page } from "@/shared/types";

export async function fetchAllPages<T, P extends ListParams = ListParams>(
  fetchPage: (params: P) => Promise<Page<T>>,
  params?: Omit<P, "page" | "size">,
  size = 100,
): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  for (;;) {
    const respuesta = await fetchPage({ ...(params as P), page, size });
    items.push(...respuesta.items);
    if (items.length >= respuesta.total || respuesta.items.length === 0) break;
    page += 1;
  }
  return items;
}
