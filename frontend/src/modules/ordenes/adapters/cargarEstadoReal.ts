/** Orquesta la carga completa del estado real: puebla los catálogos de referencia y
 * arma el `OrdenesState` con datos del backend, para que `OrdenesProvider` reciba un
 * `initialState` ya resuelto.
 *
 * ADR-285 (petición del usuario, con captura — causa raíz de "Lentitud en paginación"):
 * antes, por cada OrdenCliente se pedía su historial de comisiones y, por cada
 * OrdenEstacion, sus días y verificaciones — con los volúmenes de la siembra (10 OC, 18
 * OE) ~40 requests en paralelo SOLO para poder mostrar la primera pantalla. Esos datos
 * ahora se piden bajo demanda, por fila, cuando de verdad hacen falta
 * (`useHistorialComisionesOC`/`useOesDeLaOC`/`useOrdenEstacionSeleccionada` en
 * `hooks.ts`) — aquí solo quedan las 2 listas base completas (OC/OE, sin días ni
 * verificaciones) que siguen usando los combos/cruces que NO se migraron en esta ronda
 * (`OrdenEstacionForm`'s OC-picker, `IncidenciaListPage`), y que son baratas (2 requests
 * en total, no N+1).
 */

import type { OrdenesState } from "../state/OrdenesContext";
import { cargarCatalogosReales } from "./catalogosApi";
import { ordenClienteFromApi, ordenEstacionFromApi, incidenciaFromApi } from "./fromApi";
import { listarIncidenciasApi, listarOrdenesClienteApi, listarOrdenesEstacionApi } from "./ordenesApi";

export async function cargarEstadoReal(): Promise<OrdenesState> {
  const [, ordenesClienteDTO, ordenesEstacionDTO, incidenciasDTO] = await Promise.all([
    cargarCatalogosReales(),
    listarOrdenesClienteApi(),
    listarOrdenesEstacionApi(),
    listarIncidenciasApi(),
  ]);

  const ordenesCliente = ordenesClienteDTO.map((oc) => ordenClienteFromApi(oc));
  // Sin días/verificaciones: los únicos consumidores que quedan de esta lista global
  // (`IncidenciaListPage`, el OC-picker de `OrdenEstacionForm`) solo necesitan
  // `estacion_id`/`folio_orden_interna`/`orden_id`, nunca el período de transmisión.
  const ordenesEstacion = ordenesEstacionDTO.map((oe) => ordenEstacionFromApi(oe, [], []));
  const incidencias = incidenciasDTO.map(incidenciaFromApi);

  return { ordenesCliente, ordenesEstacion, incidencias, historialComisiones: [] };
}
