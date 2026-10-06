/** Llamadas HTTP crudas a los endpoints de ESCRITURA de Órdenes: /api/v1/ordenes/*
 * (Tanda 5). Mismo estilo que `ordenesApi.ts` (que solo cubre lectura, Tanda 3): recibe/
 * devuelve los DTOs tal cual el backend, sin adaptar a v5 — eso lo hacen `toApi.ts` (antes
 * de llamar) y `fromApi.ts`/`refrescar.ts` (después, para reflejar el resultado real).
 *
 * ADR-100: ya no existen los endpoints de checklist de Vo.Bo. (`GET/PATCH .../vobo/*`,
 * `POST .../dar-vobo`) — se eliminaron del backend junto con el checklist. */

import { apiClient, postFormData } from "@/shared/lib/apiClient";
import { fetchAllPages } from "@/shared/lib/fetchAllPages";
import type { HistorialCambio, ListParams, Page } from "@/shared/types";

import type {
  IncidenciaApiDTO,
  LogEnvioCorreoApiDTO,
  MaterialStagingApiDTO,
  OrdenClienteApiDTO,
  OrdenEstacionApiDTO,
  OrdenEstacionAudioApiDTO,
  OrdenEstacionDiaApiDTO,
  OrdenEstacionEvidenciaApiDTO,
  OrdenEstacionFormatoRealApiDTO,
  OrdenEstacionFormatoRealClienteApiDTO,
  OrdenEstacionLayoutRealApiDTO,
  OrdenEstacionLayoutRealSubidoApiDTO,
} from "./ordenesApiDTO";
import type { TipoPdfOrdenEstacion } from "./pdfsApi";

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

export async function actualizarOrdenEstacionApi(
  ordenEstacionId: string,
  body: Record<string, unknown>,
): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.put<OrdenEstacionApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}`,
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

// ── Material a Transmitir: audios (ADR-103) ────────────────────────────────────
export async function listarAudiosOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionAudioApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionAudioApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/audios`,
  );
  return data;
}

export function subirAudioOrdenEstacionApi(
  ordenEstacionId: string,
  archivo: File,
): Promise<OrdenEstacionAudioApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<OrdenEstacionAudioApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/audios`,
    fd,
  );
}

export async function eliminarAudioOrdenEstacionApi(
  ordenEstacionId: string,
  audioId: string,
): Promise<void> {
  await apiClient.delete(`/ordenes/estaciones/${ordenEstacionId}/audios/${audioId}`);
}

/** ADR-109: sube un audio a S3 SIN necesitar ningún `orden_estacion_id` (endpoint
 * "staging", para poder elegir el material a transmitir DURANTE la captura de una OE
 * nueva, antes de que exista). El `ref` devuelto se manda en `audios` al crear la OE. */
export function subirMaterialStagingApi(archivo: File): Promise<MaterialStagingApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<MaterialStagingApiDTO>("/ordenes/material-staging?tipo=audio", fd);
}

/** Descarga el audio (blob con auth) forzando el nombre original — mismo patrón que
 * `verAdjuntoOrden` (`adjuntosApi.ts`). */
export async function descargarAudioOrdenEstacionApi(
  ordenEstacionId: string,
  audioId: string,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/audios/${audioId}/archivo`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Evidencias de lo Transmitido: audios (ADR-119) ─────────────────────────────
export async function listarEvidenciasOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionEvidenciaApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionEvidenciaApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/evidencias`,
  );
  return data;
}

export function subirEvidenciaOrdenEstacionApi(
  ordenEstacionId: string,
  archivo: File,
): Promise<OrdenEstacionEvidenciaApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<OrdenEstacionEvidenciaApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/evidencias`,
    fd,
  );
}

export async function eliminarEvidenciaOrdenEstacionApi(
  ordenEstacionId: string,
  evidenciaId: string,
): Promise<void> {
  await apiClient.delete(`/ordenes/estaciones/${ordenEstacionId}/evidencias/${evidenciaId}`);
}

/** Descarga la evidencia (blob con auth) forzando el nombre original — mismo patrón que
 * `descargarAudioOrdenEstacionApi`. */
export async function descargarEvidenciaOrdenEstacionApi(
  ordenEstacionId: string,
  evidenciaId: string,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/evidencias/${evidenciaId}/archivo`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Formato de Horarios Reales: cualquier formato salvo ejecutables (ADR-123) ──
export async function listarFormatosRealesOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionFormatoRealApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionFormatoRealApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales`,
  );
  return data;
}

export function subirFormatoRealOrdenEstacionApi(
  ordenEstacionId: string,
  archivo: File,
): Promise<OrdenEstacionFormatoRealApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<OrdenEstacionFormatoRealApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales`,
    fd,
  );
}

export async function eliminarFormatoRealOrdenEstacionApi(
  ordenEstacionId: string,
  formatoRealId: string,
): Promise<void> {
  await apiClient.delete(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales/${formatoRealId}`,
  );
}

/** Descarga el archivo (blob con auth) forzando el nombre original — mismo patrón que
 * `descargarEvidenciaOrdenEstacionApi`. */
export async function descargarFormatoRealOrdenEstacionApi(
  ordenEstacionId: string,
  formatoRealId: string,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales/${formatoRealId}/archivo`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Carga de Órdenes Reales Desde Layout: csv/xlsx/xls/txt (ADR-146) ──────────
export async function listarLayoutRealesOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionLayoutRealApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionLayoutRealApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/layout-reales`,
  );
  return data;
}

/** ADR-147: la respuesta trae el archivo guardado + lo que se pudo aplicar/ignorar del
 * CSV (vacíos para xlsx/xls/txt, que no se parsean). */
export function subirLayoutRealOrdenEstacionApi(
  ordenEstacionId: string,
  archivo: File,
): Promise<OrdenEstacionLayoutRealSubidoApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<OrdenEstacionLayoutRealSubidoApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/layout-reales`,
    fd,
  );
}

export async function eliminarLayoutRealOrdenEstacionApi(
  ordenEstacionId: string,
  layoutRealId: string,
): Promise<void> {
  await apiClient.delete(
    `/ordenes/estaciones/${ordenEstacionId}/layout-reales/${layoutRealId}`,
  );
}

/** Descarga el archivo (blob con auth) forzando el nombre original — mismo patrón que
 * `descargarFormatoRealOrdenEstacionApi`. */
export async function descargarLayoutRealOrdenEstacionApi(
  ordenEstacionId: string,
  layoutRealId: string,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/layout-reales/${layoutRealId}/archivo`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Formato de Horarios Reales Enviado al Cliente: cualquier formato salvo
// ejecutables/audio (ADR-146) ──────────────────────────────────────────────────
export async function listarFormatosRealesClienteOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<OrdenEstacionFormatoRealClienteApiDTO[]> {
  const { data } = await apiClient.get<OrdenEstacionFormatoRealClienteApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales-cliente`,
  );
  return data;
}

export function subirFormatoRealClienteOrdenEstacionApi(
  ordenEstacionId: string,
  archivo: File,
): Promise<OrdenEstacionFormatoRealClienteApiDTO> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<OrdenEstacionFormatoRealClienteApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales-cliente`,
    fd,
  );
}

export async function eliminarFormatoRealClienteOrdenEstacionApi(
  ordenEstacionId: string,
  formatoRealClienteId: string,
): Promise<void> {
  await apiClient.delete(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales-cliente/${formatoRealClienteId}`,
  );
}

/** Descarga el archivo (blob con auth) forzando el nombre original — mismo patrón que
 * `descargarFormatoRealOrdenEstacionApi`. */
export async function descargarFormatoRealClienteOrdenEstacionApi(
  ordenEstacionId: string,
  formatoRealClienteId: string,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/formatos-reales-cliente/${formatoRealClienteId}/archivo`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** ADR-104: "Cancelar transmisión" de un día puntual — en cualquier momento. */
export async function cancelarDiaOrdenEstacionApi(
  ordenEstacionId: string,
  diaId: string,
  motivo: string,
): Promise<OrdenEstacionApiDTO> {
  const { data } = await apiClient.post<OrdenEstacionApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/dias/${diaId}/cancelar`,
    { motivo },
  );
  return data;
}

export async function asignarAudioDiaApi(
  ordenEstacionId: string,
  diaId: string,
  ordenEstacionAudioId: string | null,
): Promise<OrdenEstacionDiaApiDTO> {
  const { data } = await apiClient.put<OrdenEstacionDiaApiDTO>(
    `/ordenes/estaciones/${ordenEstacionId}/dias/${diaId}/audio`,
    { orden_estacion_audio_id: ordenEstacionAudioId },
  );
  return data;
}

/** ADR-124/ADR-126: arma el paquete del PDF `tipo` (+ Material a Transmitir, a los
 * contactos activos del afiliado) pero lo descarga como `.eml` — el usuario lo abre con
 * su cliente de correo de escritorio (Outlook, etc.), que lo recibe como un borrador
 * editable con todo ya adjunto, y lo manda él mismo desde su propia cuenta. */
export async function descargarEmlOrdenTransmisionApi(
  ordenEstacionId: string,
  tipo: TipoPdfOrdenEstacion,
  nombreArchivo: string,
): Promise<void> {
  const { data } = await apiClient.post<Blob>(
    `/ordenes/estaciones/${ordenEstacionId}/pdf/${tipo}/correo-orden-transmision/eml`,
    undefined,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function listarEnviosCorreoOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<LogEnvioCorreoApiDTO[]> {
  const { data } = await apiClient.get<LogEnvioCorreoApiDTO[]>(
    `/ordenes/estaciones/${ordenEstacionId}/envios-correo`,
  );
  return data;
}

/** ADR-161 (petición del usuario): historial de veces que `precio_spot` se apartó de
 * la tarifa sugerida del catálogo (ADR-102) — el backend ya lo registraba en
 * `LogCambioParametro`/exponía en `GET .../historial-tarifa`, pero el panel de detalle
 * de Orden de Transmisión nunca lo mostraba. Mismo shape que el historial de Tarifas
 * (`HistorialCambio`), sin necesidad de un DTO/adaptador propio. */
export async function listarHistorialTarifaOrdenEstacionApi(
  ordenEstacionId: string,
): Promise<HistorialCambio[]> {
  const { data } = await apiClient.get<HistorialCambio[]>(
    `/ordenes/estaciones/${ordenEstacionId}/historial-tarifa`,
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
