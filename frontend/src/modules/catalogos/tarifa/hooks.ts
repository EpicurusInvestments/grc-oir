/** Hooks de TarifaPlaza sobre el CRUD genérico.
 *
 * Reutiliza `useCatalog` para get/create/update/setEstado e sobreescribe `useList` para
 * aceptar el filtro `vigencia` (además de activo/q/paginación).
 */

import { useQuery } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { tarifaApi } from "./api";
import type { TarifaListParams } from "./types";

export function useTarifas() {
  const catalog = useCatalog("tarifa", tarifaApi);

  const useList = (params?: TarifaListParams) =>
    useQuery({
      queryKey: ["tarifa", "list", params ?? {}],
      queryFn: () => tarifaApi.list(params),
    });

  return { ...catalog, useList };
}

/** Tarifas VIGENTES (activas y no vencidas) de una plaza, para el panel de detalle de
 *  Plaza. Deshabilitada mientras no haya plaza seleccionada. Comparte el prefijo de key
 *  `["tarifa"]`, así que se refresca cuando se crean/editan tarifas. */
export function useTarifasVigentesPorPlaza(plazaId: string | null) {
  const params: TarifaListParams = {
    plaza_id: plazaId ?? undefined,
    activo: true,
    vigencia: "vigente",
    size: 100,
  };
  return useQuery({
    queryKey: ["tarifa", "vigentes-por-plaza", plazaId],
    queryFn: () => tarifaApi.list(params),
    enabled: plazaId != null,
  });
}
