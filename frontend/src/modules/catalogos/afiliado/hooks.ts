/** Hooks de Afiliado (CRUD genérico) y de Estación anidada (lista por afiliado + mutations).
 *
 * Las mutaciones de estación invalidan tanto las queries de estación como las de afiliado
 * (el detalle del afiliado muestra el conteo de sus estaciones).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";
import type { ListParams } from "@/shared/types";

import { afiliadoApi, estacionApi } from "./api";
import type { EstacionCreate, EstacionUpdate } from "./types";

export const useAfiliados = () => useCatalog("afiliado", afiliadoApi);

const ESTACION_KEY = "estacion";

export function useEstaciones() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [ESTACION_KEY] });
    qc.invalidateQueries({ queryKey: ["afiliado"] });
  };

  const useListPorAfiliado = (afiliadoId: string | null, params?: ListParams) =>
    useQuery({
      queryKey: [ESTACION_KEY, "por-afiliado", afiliadoId, params ?? {}],
      queryFn: () => estacionApi.listPorAfiliado(afiliadoId as string, params),
      enabled: afiliadoId != null,
    });

  const useCreate = () =>
    useMutation({ mutationFn: (data: EstacionCreate) => estacionApi.create(data), onSuccess: invalidate });

  const useUpdate = () =>
    useMutation({
      mutationFn: ({ id, data }: { id: string; data: EstacionUpdate }) => estacionApi.update(id, data),
      onSuccess: invalidate,
    });

  const useSetEstado = () =>
    useMutation({
      mutationFn: ({ id, activo, forzar }: { id: string; activo: boolean; forzar?: boolean }) =>
        estacionApi.setEstado(id, activo, forzar),
      onSuccess: invalidate,
    });

  return { useListPorAfiliado, useCreate, useUpdate, useSetEstado };
}
