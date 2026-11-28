/** Hooks de F4-01 (TanStack Query). Solo lectura: sin mutaciones, sin invalidación — el
 * Estado de resultados no tiene estado propio que capturar, solo agrega lo que F1-F3
 * ya escribieron. */

import { useMutation, useQuery } from "@tanstack/react-query";

import { reportesApi } from "./api";
import type { FormatoExportacion, VentanaComercial } from "./types";

const K_ESTADO_RESULTADOS = "reportes:estado-resultados";
const K_DASHBOARD_COMERCIAL = "reportes:comercial";
const K_DASHBOARD_COBRANZA = "reportes:cobranza";
const K_DASHBOARD_OPERATIVO = "reportes:operativo";

export function useEstadoResultados(periodo?: string) {
  return useQuery({
    queryKey: [K_ESTADO_RESULTADOS, periodo ?? "actual"],
    queryFn: () => reportesApi.estadoResultados(periodo),
  });
}

export function useExportarEstadoResultados() {
  return useMutation({
    mutationFn: ({ periodo, formato }: { periodo: string; formato: FormatoExportacion }) =>
      reportesApi.exportarEstadoResultados(periodo, formato),
  });
}

export function useDashboardComercial(ventana: VentanaComercial, periodo?: string) {
  return useQuery({
    queryKey: [K_DASHBOARD_COMERCIAL, ventana, periodo ?? "actual"],
    queryFn: () => reportesApi.dashboardComercial(ventana, periodo),
  });
}

export function useExportarDashboardComercial() {
  return useMutation({
    mutationFn: ({
      ventana,
      periodo,
      formato,
    }: {
      ventana: VentanaComercial;
      periodo?: string;
      formato: FormatoExportacion;
    }) => reportesApi.exportarDashboardComercial(ventana, periodo, formato),
  });
}

export function useDashboardCobranza(mes?: string, ventanaDsoDias = 90) {
  return useQuery({
    queryKey: [K_DASHBOARD_COBRANZA, mes ?? "actual", ventanaDsoDias],
    queryFn: () => reportesApi.dashboardCobranza(mes, ventanaDsoDias),
  });
}

export function useExportarDashboardCobranza() {
  return useMutation({
    mutationFn: ({
      mes,
      ventanaDsoDias,
      formato,
    }: {
      mes?: string;
      ventanaDsoDias: number;
      formato: FormatoExportacion;
    }) => reportesApi.exportarDashboardCobranza(mes, ventanaDsoDias, formato),
  });
}

export function useDashboardOperativo(ventana: VentanaComercial, periodo?: string) {
  return useQuery({
    queryKey: [K_DASHBOARD_OPERATIVO, ventana, periodo ?? "actual"],
    queryFn: () => reportesApi.dashboardOperativo(ventana, periodo),
  });
}

export function useExportarDashboardOperativo() {
  return useMutation({
    mutationFn: ({
      ventana,
      periodo,
      formato,
    }: {
      ventana: VentanaComercial;
      periodo?: string;
      formato: FormatoExportacion;
    }) => reportesApi.exportarDashboardOperativo(ventana, periodo, formato),
  });
}
