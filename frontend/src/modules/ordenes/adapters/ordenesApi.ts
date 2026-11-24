/** Llamadas HTTP crudas al backend real de Órdenes: /api/v1/ordenes/* (Tanda 3, solo
 * lectura). Devuelve los DTOs tal cual los manda el backend (`ordenesApiDTO.ts`); la
 * conversión a los tipos v5 de `types.ts` vive en `fromApi.ts`, no aquí. */

import { apiClient } from "@/shared/lib/apiClient";
import { fetchAllPages } from "@/shared/lib/fetchAllPages";
import type { HistorialCambio, ListParams, Page } from "@/shared/types";

import type {
  IncidenciaApiDTO,
  OrdenClienteApiDTO,
  OrdenEstacionApiDTO,
  OrdenEstacionDiaApiDTO,
  VerificacionApiDTO,
} from "./ordenesApiDTO";

export async function listarOrdenesClienteApi(): Promise<OrdenClienteApiDTO[]> {
  return fetchAllPages((params) =>
    apiClient.get<Page<OrdenClienteApiDTO>>("/ordenes/clientes", { params }).then((r) => r.data),
  );
}

/** ADR-285 (petición del usuario, con captura): UNA página real contra el backend —
 *  a diferencia de `listarOrdenesClienteApi` (trae el 100%, se usaba para precargar el
 *  estado global), esta es la que debe usar la pantalla de lista: solo pide lo que se
 *  va a pintar. */
export interface FiltrosOrdenCliente extends ListParams {
  estatus_orden?: string;
  anunciante_id?: string;
  agencia_id?: string;
  vendedor_principal_id?: string;
  contrato_id?: string;
  listas_para_cerrar?: boolean;
  activas?: boolean;
}

export async function paginaOrdenesClienteApi(
  params: FiltrosOrdenCliente,
): Promise<Page<OrdenClienteApiDTO>> {
  const { data } = await apiClient.get<Page<OrdenClienteApiDTO>>("/ordenes/clientes", { params });
  return data;
}

/** Una sola OrdenCliente — usado para refrescar tras una escritura (Tanda 5), evita
 * releer la lista completa. */
export async function obtenerOrdenClienteApi(ordenId: string): Promise<OrdenClienteApiDTO> {
  const { data } = await apiClient.get<OrdenClienteApiDTO>(`/ordenes/clientes/${ordenId}`);
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

/** ADR-285: espejo de `paginaOrdenesClienteApi`, para la pantalla de lista. */
export interface FiltrosOrdenEstacion extends ListParams {
  orden_id?: string;
  estacion_id?: string;
  plaza_id?: string;
  anunciante_id?: string;
  estatus?: string;
  tiene_incidencias?: boolean;
}

export async function paginaOrdenesEstacionApi(
  params: FiltrosOrdenEstacion,
): Promise<Page<OrdenEstacionApiDTO>> {
  const { data } = await apiClient.get<Page<OrdenEstacionApiDTO>>("/ordenes/estaciones", { params });
  return data;
}

/** Todas las OE de UNA OrdenCliente (panel de detalle/alta): acotado por `orden_id`,
 *  nunca el arreglo completo del sistema. `size: 100` porque una orden rara vez tiene
 *  más de unas pocas estaciones asignadas. */
export async function oesDeLaOCApi(ordenId: string): Promise<OrdenEstacionApiDTO[]> {
  const { data } = await apiClient.get<Page<OrdenEstacionApiDTO>>("/ordenes/estaciones", {
    params: { orden_id: ordenId, size: 100 },
  });
  return data.items;
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

/** ADR-285: una página real — usada hoy solo para el conteo ligero del sidebar
 *  (`size: 1` + `total`); la pantalla de Incidencias sigue usando `listarIncidenciasApi`
 *  (fuera de alcance de esta ronda). */
export async function paginaIncidenciasApi(params: ListParams): Promise<Page<IncidenciaApiDTO>> {
  const { data } = await apiClient.get<Page<IncidenciaApiDTO>>("/ordenes/incidencias", { params });
  return data;
}
