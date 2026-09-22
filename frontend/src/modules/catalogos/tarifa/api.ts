/** API de TarifaPlaza sobre el CRUD genérico (/api/v1/catalogos/tarifas).
 *
 * Además del CRUD estándar, expone el historial de auditoría de `tarifa_bruta`/
 * `descuento_pct` (parámetros sensibles, ADR-099): `/catalogos/tarifas/{id}/historial`.
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type { HistorialCambio, TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate } from "./types";

const crud = createCatalogApi<TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate>("tarifas");

export const tarifaApi = {
  ...crud,
  /** Historial de cambios a `tarifa_bruta`/`descuento_pct` (más reciente primero). */
  async historial(tarifaId: string): Promise<HistorialCambio[]> {
    const { data } = await apiClient.get<HistorialCambio[]>(
      `/catalogos/tarifas/${tarifaId}/historial`,
    );
    return data;
  },
};
