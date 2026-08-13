/** Llamadas HTTP crudas al backend real de Órdenes: /api/v1/ordenes/* (Tanda 3, solo
 * lectura). Devuelve los DTOs tal cual los manda el backend (`ordenesApiDTO.ts`); la
 * conversión a los tipos v5 de `types.ts` vive en `fromApi.ts`, no aquí. */

import { apiClient } from "@/shared/lib/apiClient";
import { fetchAllPages } from "@/shared/lib/fetchAllPages";
import type { HistorialCambio, ListParams, Page } from "@/shared/types";

import type {
  IncidenciaApiDTO,
  OrdenClienteApiDTO,
  OrdenClienteVoBoItemApiDTO,
  OrdenEstacionApiDTO,
  OrdenEstacionDiaApiDTO,
  VerificacionApiDTO,
} from "./ordenesApiDTO";

export async function listarOrdenesClienteApi(): Promise<OrdenClienteApiDTO[]> {
  return fetchAllPages((params) =>
    apiClient.get<Page<OrdenClienteApiDTO>>("/ordenes/clientes", { params }).then((r) => r.data),
  );
}

/** Una sola OrdenCliente — usado para refrescar tras una escritura (Tanda 5), evita
 * releer la lista completa. */
export async function obtenerOrdenClienteApi(ordenId: string): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.get<OrdenClienteApiDTO>(`/ordenes/clientes/${ordenId}`);
  return data;
}

export async function listarVoboApi(ordenId: string): Promise<OrdenClienteVoBoItemApiDTO[]> {
  const { data } = await apiClient.get<OrdenClienteVoBoItemApiDTO[]>(
    `/ordenes/clientes/${ordenId}/vobo`,
  );
  return data;
}

export async function listarHistorialComisionesApi(ordenId: string): Promise<HistorialCambio[]> {
  const { data } = await apiClient.get<HistorialCambio[]>(
    `/ordenes/clientes/${ordenId}/historial-comisiones`,
  );
  return data;
}

export async function listarOrdenesEstacionApi(): Promise<OrdenEstacionApiDTO[]> {
  return fetchAllPages((params) =>
    apiClient.get<Page<OrdenEstacionApiDTO>>("/ordenes/estaciones", { params }).then((r) => r.data),
  );
}

/** Una sola OrdenEstacion — usado para refrescar tras una escritura (Tanda 5). */
export async function obtenerOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.get<OrdenEstacionApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}`,
  );
  return data;
}

export async function listarDiasOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionDiaApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionDiaApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/dias`,
  );
  return data;
}

export async function listarVerificacionesApi(
  ordenEstacionId: string,
): Promise<VerificacionApiDTO[]> {
  return fetchAllPages((params: ListParams & { orden_estacion_id?: string }) =>
    apiClient
      .get<Page<VerificacionApiDTO>>("/ordenes/verificaciones", { params })
      .then((r) => r.data),
    { orden_estacion_id: ordenEstacionId },
  );
}

export async function listarIncidenciasApi(): Promise<IncidenciaApiDTO[]> {
  return fetchAllPages((params) =>
    apiClient.get<Page<IncidenciaApiDTO>>("/ordenes/incidencias", { params }).then((r) => r.data),
  );
}
