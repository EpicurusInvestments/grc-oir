/** Hooks de TanStack Query gemelos del CRUD genérico. Cada catálogo obtiene queries y
 * mutations listas (con invalidación tras mutar) pasando su `CatalogApi` y una `key`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { CatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams } from "@/shared/types";

export function useCatalog<Read, Create, Update>(
  key: string,
  api: CatalogApi<Read, Create, Update>,
) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: [key] });

  const useList = (params?: ListParams) =>
    useQuery({
      queryKey: [key, "list", params ?? {}],
      queryFn: () => api.list(params),
    });

  const useGet = (id: string | null) =>
    useQuery({
      queryKey: [key, "detail", id],
      queryFn: () => api.get(id as string),
      enabled: id != null,
    });

  const useCreate = () =>
    useMutation({ mutationFn: (data: Create) => api.create(data), onSuccess: invalidate });

  const useUpdate = () =>
    useMutation({
      mutationFn: ({ id, data }: { id: string; data: Update }) => api.update(id, data),
      onSuccess: invalidate,
    });

  const useSetEstado = () =>
    useMutation({
      mutationFn: ({ id, activo }: { id: string; activo: boolean }) => api.setEstado(id, activo),
      onSuccess: invalidate,
    });

  return { useList, useGet, useCreate, useUpdate, useSetEstado };
}
