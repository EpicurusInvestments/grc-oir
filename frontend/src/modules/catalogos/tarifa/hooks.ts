/** Hooks de TarifaPlaza sobre el CRUD genérico (`useCatalog` alcanza sin overrides desde
 * ADR-097: ya no hay filtro `vigencia` ni `plaza_id`, la búsqueda `q` la resuelve el
 * backend directo contra el `ListParams` base) + historial de auditoría (ADR-099). */

import { useQuery } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { tarifaApi } from "./api";

export function useTarifas() {
  return useCatalog("tarifa", tarifaApi);
}

/** Historial de cambios de `tarifa_bruta`/`descuento_pct` de la tarifa seleccionada. Se
 *  invalida con la key "tarifa" (una edición refresca la lista y también su historial). */
export function useHistorialTarifa(tarifaId: string | null) {
  return useQuery({
    queryKey: ["tarifa", "historial", tarifaId],
    queryFn: () => tarifaApi.historial(tarifaId as string),
    enabled: tarifaId != null,
  });
}
