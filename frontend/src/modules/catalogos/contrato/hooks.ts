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

/** Adjuntos (PDF) del contrato: listado + subir/borrar/descargar. */
export function useAdjuntosContrato(contratoId: string | null) {
  const qc = useQueryClient();
  const clave = ["contrato", "adjuntos", contratoId] as const;

  const listar = useQuery({
    queryKey: clave,
    queryFn: () => contratoApi.adjuntos.listar(contratoId as string),
    enabled: contratoId != null,
  });

  const subir = useMutation({
    mutationFn: (archivo: File) => contratoApi.adjuntos.subir(contratoId as string, archivo),
    onSuccess: () => qc.invalidateQueries({ queryKey: clave }),
  });

  const borrar = useMutation({
    mutationFn: (nombre: string) => contratoApi.adjuntos.borrar(contratoId as string, nombre),
    onSuccess: () => qc.invalidateQueries({ queryKey: clave }),
  });

  /** Abre el PDF en una pestaña nueva (blob servido por el backend). */
  const ver = async (nombre: string): Promise<void> => {
    const blob = await contratoApi.adjuntos.descargar(contratoId as string, nombre);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener");
    // Se libera tras un margen para que el navegador alcance a abrir la pestaña.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  return { listar, subir, borrar, ver };
}
