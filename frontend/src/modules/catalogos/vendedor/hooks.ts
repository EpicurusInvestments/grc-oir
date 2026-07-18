/** Hooks de Vendedor (CRUD genérico) + historial de auditoría del % (patrón Agencia). */

import { useQuery } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { vendedorApi } from "./api";

export const useVendedores = () => useCatalog("vendedor", vendedorApi);

/** Historial de auditoría del vendedor seleccionado (se refresca al mutar "vendedor"). */
export function useHistorialVendedor(vendedorId: string | null) {
  return useQuery({
    queryKey: ["vendedor", "historial", vendedorId],
    queryFn: () => vendedorApi.historial(vendedorId as string),
    enabled: vendedorId != null,
  });
}
