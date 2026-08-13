/** Tras cualquier escritura (Tanda 5), la respuesta del endpoint es SOLO la entidad
 * principal (`OrdenClienteRead`/`OrdenEstacionRead`) — sin checklist, días o
 * verificaciones. Estas funciones piden lo que falta y reconstruyen el objeto v5
 * completo con las MISMAS funciones de `fromApi.ts` que ya usa la carga inicial (Tanda
 * 4) — nunca se duplica la lógica de reconstrucción. */

import {
  listarDiasOrdenEstacionApi,
  listarVerificacionesApi,
  listarVoboApi,
  obtenerOrdenClienteApi,
  obtenerOrdenEstacionApi,
} from "./ordenesApi";
import { ordenClienteFromApi, ordenEstacionFromApi } from "./fromApi";
import type { OrdenCliente, OrdenEstacion } from "../types";

export async function refrescarOrdenCliente(ordenId: string): Promise<OrdenCliente> {
  const [dto, vobo] = await Promise.all([
    obtenerOrdenClienteApi(ordenId),
    listarVoboApi(ordenId),
  ]);
  return ordenClienteFromApi(dto, vobo);
}

export async function refrescarOrdenEstacion(ordenEstacionId: string): Promise<OrdenEstacion> {
  const [dto, dias, verificaciones] = await Promise.all([
    obtenerOrdenEstacionApi(ordenEstacionId),
    listarDiasOrdenEstacionApi(ordenEstacionId),
    listarVerificacionesApi(ordenEstacionId),
  ]);
  return ordenEstacionFromApi(dto, dias, verificaciones);
}
