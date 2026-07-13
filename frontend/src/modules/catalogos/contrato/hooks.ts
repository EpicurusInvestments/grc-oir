/** Hooks de Contrato: CRUD genérico + lista con filtro por estado, transición de estado
 * (máquina de estados) e historial de auditoría. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { contratoApi, type ContratoListParams } from "./api";
import type { EstadoContrato } from "./types";

export function useContratos() {
  const qc = useQueryClient();
  const catalog = useCatalog("contrato", contratoApi);

  const useList = (params?: ContratoListParams) =>
    useQuery({
      queryKey: ["contrato", "list", params ?? {}],
      queryFn: () => contratoApi.list(params),
    });

  const useTransicionar = () =>
    useMutation({
      mutationFn: ({ id, estado }: { id: string; estado: EstadoContrato }) =>
        contratoApi.transicionarEstado(id, estado),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["contrato"] }),
    });

  return { ...catalog, useList, useTransicionar };
}

/** Historial de auditoría del contrato seleccionado (se refresca al mutar "contrato"). */
export function useHistorialContrato(contratoId: string | null) {
  return useQuery({
    queryKey: ["contrato", "historial", contratoId],
    queryFn: () => contratoApi.historial(contratoId as string),
    enabled: contratoId != null,
  });
}
