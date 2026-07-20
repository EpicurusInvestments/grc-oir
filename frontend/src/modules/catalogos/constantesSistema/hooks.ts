/** Hooks de ConstantesSistema.
 *
 * Reutiliza `useCatalog` para get/create/update/setEstado; añade `useList` con filtro por
 * grupo, `useConteos` para las pills y `useImportar` (invalida la key al aplicar con commit).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { constanteApi } from "./api";
import type { ConstantesListParams, ModoDuplicados } from "./types";

const KEY = "constante";

export function useConstantes() {
  const catalog = useCatalog(KEY, constanteApi);

  const useList = (params?: ConstantesListParams) =>
    useQuery({
      queryKey: [KEY, "list", params ?? {}],
      queryFn: () => constanteApi.list(params),
    });

  const useConteos = (soloActivos = false) =>
    useQuery({
      queryKey: [KEY, "conteos", soloActivos],
      queryFn: () => constanteApi.conteos(soloActivos),
    });

  return { ...catalog, useList, useConteos };
}

/** Importación CSV. Previsualizar (commit=false) NO invalida; aplicar (commit=true) refresca
 *  la lista y los conteos (comparten el prefijo de key `["constante"]`). */
export function useImportarConstantes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { archivo: File; commit: boolean; modo: ModoDuplicados }) =>
      constanteApi.importar(vars.archivo, vars.commit, vars.modo),
    onSuccess: (_res, vars) => {
      if (vars.commit) qc.invalidateQueries({ queryKey: [KEY] });
    },
  });
}
