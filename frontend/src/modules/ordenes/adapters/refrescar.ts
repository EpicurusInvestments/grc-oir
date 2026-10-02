/** Tras cualquier escritura (Tanda 5), la respuesta del endpoint es SOLO la entidad
 * principal (`OrdenClienteRead`/`OrdenEstacionRead`) — sin días o verificaciones.
 * Estas funciones piden lo que falta y reconstruyen el objeto v5 completo con las
 * MISMAS funciones de `fromApi.ts` que ya usa la carga inicial (Tanda 4) — nunca se
 * duplica la lógica de reconstrucción. */

import {
  listarDiasOrdenEstacionApi,
  listarVerificacionesApi,
  obtenerOrdenClienteApi,
  obtenerOrdenEstacionApi,
} from "./ordenesApi";
import { ordenClienteFromApi, ordenEstacionFromApi } from "./fromApi";
import type { OrdenCliente, OrdenEstacion } from "../types";

export async function refrescarOrdenCliente(ordenId: string): Promise<OrdenCliente> {
  const dto = await obtenerOrdenClienteApi(ordenId);
  return ordenClienteFromApi(dto);
}

export async function refrescarOrdenEstacion(ordenEstacionId: string): Promise<OrdenEstacion> {
  const [dto, dias, verificaciones] = await Promise.all([
    obtenerOrdenEstacionApi(ordenEstacionId),
    listarDiasOrdenEstacionApi(ordenEstacionId),
    listarVerificacionesApi(ordenEstacionId),
  ]);
  return ordenEstacionFromApi(dto, dias, verificaciones);
}
