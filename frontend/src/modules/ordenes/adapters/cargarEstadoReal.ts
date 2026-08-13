/** Orquesta la carga completa del estado real: puebla los catálogos de referencia y
 * arma el `OrdenesState` con datos del backend, para que `OrdenesProvider` reciba un
 * `initialState` ya resuelto.
 *
 * Nota de rendimiento (aceptada para desarrollo, Tanda 3 no tiene endpoints por lote):
 * por cada OrdenCliente se piden su checklist Vo.Bo. y su historial de comisiones; por
 * cada OrdenEstacion, sus días y verificaciones. Con los volúmenes de la siembra (10 OC,
 * 18 OE) son ~60 requests en paralelo — aceptable en desarrollo, a revisar si el volumen
 * real de datos crece mucho antes de llevarlo a producción.
 */

import type { OrdenesState } from "../state/OrdenesContext";
import { cargarCatalogosReales } from "./catalogosApi";
import { ordenClienteFromApi, ordenEstacionFromApi, incidenciaFromApi } from "./fromApi";
import {
  listarDiasOrdenEstacionApi,
  listarHistorialComisionesApi,
  listarIncidenciasApi,
  listarOrdenesClienteApi,
  listarOrdenesEstacionApi,
  listarVerificacionesApi,
  listarVoboApi,
} from "./ordenesApi";

export async function cargarEstadoReal(): Promise<OrdenesState> {
  const [, ordenesClienteDTO, ordenesEstacionDTO, incidenciasDTO] = await Promise.all([
    cargarCatalogosReales(),
    listarOrdenesClienteApi(),
    listarOrdenesEstacionApi(),
    listarIncidenciasApi(),
  ]);

  const [ordenesCliente, historialesPorOC] = await Promise.all([
    Promise.all(
      ordenesClienteDTO.map(async (oc) => {
        const vobo = await listarVoboApi(oc.orden_id);
        return ordenClienteFromApi(oc, vobo);
      }),
    ),
    Promise.all(ordenesClienteDTO.map((oc) => listarHistorialComisionesApi(oc.orden_id))),
  ]);

  const ordenesEstacion = await Promise.all(
    ordenesEstacionDTO.map(async (oe) => {
      const [dias, verificaciones] = await Promise.all([
        listarDiasOrdenEstacionApi(oe.orden_estacion_id),
        listarVerificacionesApi(oe.orden_estacion_id),
      ]);
      return ordenEstacionFromApi(oe, dias, verificaciones);
    }),
  );

  const incidencias = incidenciasDTO.map(incidenciaFromApi);
  const historialComisiones = historialesPorOC.flat();

  return { ordenesCliente, ordenesEstacion, incidencias, historialComisiones };
}
