/** Hooks de Agencia (CRUD genérico con invalidación por key "agencia") + lecturas del
 * panel de detalle (anunciantes representados e historial de auditoría). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";
import type { ListParams } from "@/shared/types";

import { agenciaApi, contactoAgenciaApi } from "./api";
import type { ContactoAgenciaCreate, ContactoAgenciaUpdate } from "./types";

export const useAgencias = () => useCatalog("agencia", agenciaApi);

/** Anunciantes de la agencia seleccionada (deshabilitado si no hay selección). Comparte
 *  prefijo de key con el catálogo Anunciante para refrescarse ante sus mutaciones. */
export function useAnunciantesPorAgencia(agenciaId: string | null) {
  return useQuery({
    queryKey: ["anunciante", "por-agencia", agenciaId],
    queryFn: () => agenciaApi.anunciantesPorAgencia(agenciaId as string, { size: 100 }),
    enabled: agenciaId != null,
  });
}

/** Historial de auditoría de la agencia seleccionada. Se invalida con la key "agencia"
 *  (una edición del % refresca la lista y también su historial). */
export function useHistorialAgencia(agenciaId: string | null) {
  return useQuery({
    queryKey: ["agencia", "historial", agenciaId],
    queryFn: () => agenciaApi.historial(agenciaId as string),
    enabled: agenciaId != null,
  });
}

const CONTACTO_AGENCIA_KEY = "contacto-agencia";

/** Contactos anidados de la Agencia (entidad nueva) — mismo patrón que
 *  `useContactosAnunciante` en el módulo Anunciante. */
export function useContactosAgencia() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [CONTACTO_AGENCIA_KEY] });
    qc.invalidateQueries({ queryKey: ["agencia"] });
  };

  const useListPorAgencia = (agenciaId: string | null, params?: ListParams) =>
    useQuery({
      queryKey: [CONTACTO_AGENCIA_KEY, "por-agencia", agenciaId, params ?? {}],
      queryFn: () => contactoAgenciaApi.listPorAgencia(agenciaId as string, params),
      enabled: agenciaId != null,
    });

  const useCreate = () =>
    useMutation({
      mutationFn: (data: ContactoAgenciaCreate) => contactoAgenciaApi.create(data),
      onSuccess: invalidate,
    });

  const useUpdate = () =>
    useMutation({
      mutationFn: ({ id, data }: { id: string; data: ContactoAgenciaUpdate }) =>
        contactoAgenciaApi.update(id, data),
      onSuccess: invalidate,
    });

  const useSetEstado = () =>
    useMutation({
      mutationFn: ({ id, activo, forzar }: { id: string; activo: boolean; forzar?: boolean }) =>
        contactoAgenciaApi.setEstado(id, activo, forzar),
      onSuccess: invalidate,
    });

  return { useListPorAgencia, useCreate, useUpdate, useSetEstado };
}
