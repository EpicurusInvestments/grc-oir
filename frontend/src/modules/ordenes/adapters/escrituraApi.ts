/** Llamadas HTTP crudas a los 9 endpoints de ESCRITURA de Órdenes: /api/v1/ordenes/*
 * (Tanda 5). Mismo estilo que `ordenesApi.ts` (que solo cubre lectura, Tanda 3): recibe/
 * devuelve los DTOs tal cual el backend, sin adaptar a v5 — eso lo hacen `toApi.ts` (antes
 * de llamar) y `fromApi.ts`/`refrescar.ts` (después, para reflejar el resultado real). */

import { apiClient } from "@/shared/lib/apiClient";
import { fetchAllPages } from "@/shared/lib/fetchAllPages";
import type { ListParams, Page } from "@/shared/types";

import type {
  IncidenciaApiDTO,
  OrdenClienteApiDTO,
  OrdenClienteVoBoItemApiDTO,
  OrdenEstacionApiDTO,
} from "./ordenesApiDTO";

// ── OrdenCliente ──────────────────────────────────────────────────────────────
export async function crearOrdenClienteApi(body: unknown): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.post<OrdenClienteApiDTO>("/ordenes/clientes", body);
  return data;
}

export async function actualizarOrdenClienteApi(
  ordenId: string,
  body: Record<string, unknown>,
): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.put<OrdenClienteApiDTO>(`/ordenes/clientes/${ordenId}`, body);
  return data;
}

export async function actualizarComisionesApi(
  ordenId: string,
  body: unknown,
): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.patch<OrdenClienteApiDTO>(
    `/ordenes/clientes/${ordenId}/comisiones`,
    body,
  );
  return data;
}

export async function toggleVoboApi(
  ordenId: string,
  itemClave: string,
  completado: boolean,
): Promise<OrdenClienteVoBoItemApiDTO> {
  const { data } = await apiClient.patch<OrdenClienteVoBoItemApiDTO>(
    `/ordenes/clientes/${ordenId}/vobo/${itemClave}`,
    { completado },
  );
  return data;
}

export async function darVoboApi(ordenId: string): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.post<OrdenClienteApiDTO>(
    `/ordenes/clientes/${ordenId}/dar-vobo`,
  );
  return data;
}

export async function cerrarOrdenClienteApi(
  ordenId: string,
  body: unknown,
): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.post<OrdenClienteApiDTO>(
    `/ordenes/clientes/${ordenId}/cerrar`,
    body,
  );
  return data;
}

// ── OrdenEstacion ─────────────────────────────────────────────────────────────
export async function crearOrdenEstacionApi(body: unknown): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.post<OrdenEstacionApiDTO>("/ordenes/estaciones", body);
  return data;
}

export async function avanzarProgramadosApi(
  ordenEstacionId: string,
  body: unknown,
): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.post<OrdenEstacionApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/programados`,
    body,
  );
  return data;
}

export async function avanzarRealesApi(
  ordenEstacionId: string,
  body: unknown,
): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.post<OrdenEstacionApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/reales`,
    body,
  );
  return data;
}

export async function listarIncidenciasDeOEApi(
  ordenEstacionId: string,
): Promise<IncidenciaApiDTO[]> {
  return fetchAllPages(
    (params: ListParams & { orden_estacion_id?: string }) =>
      apiClient
        .get<Page<IncidenciaApiDTO>>("/ordenes/incidencias", { params })
        .then((r) => r.data),
    { orden_estacion_id: ordenEstacionId },
  );
}
