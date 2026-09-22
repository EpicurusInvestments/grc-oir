/** Hooks de Afiliado (CRUD genérico) y de ContactoAfiliado anidado (lista por afiliado +
 * mutaciones, ADR-094).
 *
 * Las mutaciones de contacto invalidan tanto las queries de contacto como las de
 * afiliado. La Estación tiene sus propios hooks desde ADR-094
 * (`modules/catalogos/estacion/hooks.ts`).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";
import type { ListParams } from "@/shared/types";

import { afiliadoApi, contactoAfiliadoApi } from "./api";
import type { ContactoAfiliadoCreate, ContactoAfiliadoUpdate } from "./types";

export const useAfiliados = () => useCatalog("afiliado", afiliadoApi);

const CONTACTO_AFILIADO_KEY = "contacto-afiliado";

export function useContactosAfiliado() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [CONTACTO_AFILIADO_KEY] });
    qc.invalidateQueries({ queryKey: ["afiliado"] });
  };

  const useListPorAfiliado = (afiliadoId: string | null, params?: ListParams) =>
    useQuery({
      queryKey: [CONTACTO_AFILIADO_KEY, "por-afiliado", afiliadoId, params ?? {}],
      queryFn: () => contactoAfiliadoApi.listPorAfiliado(afiliadoId as string, params),
      enabled: afiliadoId != null,
    });

  const useCreate = () =>
    useMutation({
      mutationFn: (data: ContactoAfiliadoCreate) => contactoAfiliadoApi.create(data),
      onSuccess: invalidate,
    });

  const useUpdate = () =>
    useMutation({
      mutationFn: ({ id, data }: { id: string; data: ContactoAfiliadoUpdate }) =>
        contactoAfiliadoApi.update(id, data),
      onSuccess: invalidate,
    });

  const useSetEstado = () =>
    useMutation({
      mutationFn: ({ id, activo, forzar }: { id: string; activo: boolean; forzar?: boolean }) =>
        contactoAfiliadoApi.setEstado(id, activo, forzar),
      onSuccess: invalidate,
    });

  return { useListPorAfiliado, useCreate, useUpdate, useSetEstado };
}
