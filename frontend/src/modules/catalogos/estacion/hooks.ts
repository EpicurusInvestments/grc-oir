/** Hooks de Estación/Emisora (CRUD genérico + lectura acotada por afiliado). */

import { useQuery } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { estacionApi, type EstacionListParams } from "./api";

export function useEstaciones() {
  const catalog = useCatalog("estacion", estacionApi);
  const useList = (params?: EstacionListParams) =>
    useQuery({
      queryKey: ["estacion", "list", params ?? {}],
      queryFn: () => estacionApi.list(params),
    });
  return { ...catalog, useList };
}

/** Estaciones de un afiliado (sección de solo lectura en su detalle; deshabilitado sin
 *  selección). Comparte prefijo de key con el catálogo Estación para refrescarse ante
 *  sus mutaciones (alta/edición/baja desde la pantalla propia). */
export function useEstacionesPorAfiliado(afiliadoId: string | null) {
  return useQuery({
    queryKey: ["estacion", "por-afiliado", afiliadoId],
    queryFn: () => estacionApi.listPorAfiliado(afiliadoId as string, { size: 100 }),
    enabled: afiliadoId != null,
  });
}
