/** API de TarifaPlaza sobre el CRUD genérico (/api/v1/catalogos/tarifas).
 *
 * `list` acepta el filtro extra `vigencia` (vigente/expirada), que el backend resuelve
 * contra la fecha del servidor; el cliente genérico reenvía todo `params` como query.
 */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type { TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate } from "./types";

export const tarifaApi = createCatalogApi<TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate>(
  "tarifas",
);
