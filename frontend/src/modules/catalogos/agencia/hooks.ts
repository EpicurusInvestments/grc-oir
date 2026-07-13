/** Hooks de Agencia (CRUD genérico con invalidación por key "agencia") + lecturas del
 * panel de detalle (anunciantes representados e historial de auditoría). */

import { useQuery } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { agenciaApi } from "./api";

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
