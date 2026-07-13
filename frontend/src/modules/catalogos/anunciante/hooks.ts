/** Hooks de Anunciante (CRUD + filtro relación) y de Marca anidada (lista por anunciante +
 * mutaciones), más las lecturas del panel (contratos e historial).
 *
 * Las mutaciones de marca invalidan tanto la key "marca" como "anunciante" (el detalle del
 * anunciante muestra el conteo de sus marcas), igual que Estación↔Afiliado en F0-01.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";
import type { ListParams } from "@/shared/types";

import { anuncianteApi, type AnuncianteListParams, marcaApi } from "./api";
import type { MarcaCreate, MarcaUpdate } from "./types";

export function useAnunciantes() {
  const catalog = useCatalog("anunciante", anuncianteApi);
  const useList = (params?: AnuncianteListParams) =>
    useQuery({
      queryKey: ["anunciante", "list", params ?? {}],
      queryFn: () => anuncianteApi.list(params),
    });
  return { ...catalog, useList };
}

const MARCA_KEY = "marca";

export function useMarcas() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [MARCA_KEY] });
    qc.invalidateQueries({ queryKey: ["anunciante"] });
  };

  const useListPorAnunciante = (anuncianteId: string | null, params?: ListParams) =>
    useQuery({
      queryKey: [MARCA_KEY, "por-anunciante", anuncianteId, params ?? {}],
      queryFn: () => marcaApi.listPorAnunciante(anuncianteId as string, params),
      enabled: anuncianteId != null,
    });

  const useCreate = () =>
    useMutation({ mutationFn: (data: MarcaCreate) => marcaApi.create(data), onSuccess: invalidate });

  const useUpdate = () =>
    useMutation({
      mutationFn: ({ id, data }: { id: string; data: MarcaUpdate }) => marcaApi.update(id, data),
      onSuccess: invalidate,
    });

  const useSetEstado = () =>
    useMutation({
      mutationFn: ({ id, activo, forzar }: { id: string; activo: boolean; forzar?: boolean }) =>
        marcaApi.setEstado(id, activo, forzar),
      onSuccess: invalidate,
    });

  return { useListPorAnunciante, useCreate, useUpdate, useSetEstado };
}

/** Contratos del anunciante seleccionado (sección del panel; deshabilitado sin selección). */
export function useContratosPorAnunciante(anuncianteId: string | null) {
  return useQuery({
    queryKey: ["contrato", "por-anunciante", anuncianteId],
    queryFn: () => anuncianteApi.contratosPorAnunciante(anuncianteId as string, { size: 100 }),
    enabled: anuncianteId != null,
  });
}

/** Historial de auditoría del anunciante seleccionado (se refresca al mutar "anunciante"). */
export function useHistorialAnunciante(anuncianteId: string | null) {
  return useQuery({
    queryKey: ["anunciante", "historial", anuncianteId],
    queryFn: () => anuncianteApi.historial(anuncianteId as string),
    enabled: anuncianteId != null,
  });
}
