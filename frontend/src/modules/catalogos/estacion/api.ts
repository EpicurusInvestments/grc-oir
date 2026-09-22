/** API de Estación/Emisora sobre el CRUD genérico: /api/v1/catalogos/estaciones.
 *
 * Pantalla propia (ADR-094): la lista general acepta filtros opcionales `afiliado_id`/
 * `plaza_id`, además de `GET /catalogos/estaciones/afiliado/{id}` para quien solo
 * necesite las de un afiliado (p.ej. combos de otros módulos).
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams, Page } from "@/shared/types";

import type { Estacion, EstacionCreate, EstacionUpdate } from "./types";

export interface EstacionListParams extends ListParams {
  afiliado_id?: string;
  plaza_id?: string;
}

const estacionCrud = createCatalogApi<Estacion, EstacionCreate, EstacionUpdate>("estaciones");

export const estacionApi = {
  ...estacionCrud,
  /** Lista con filtros `afiliado_id`/`plaza_id` (además de activo/q/paginación). */
  async list(params?: EstacionListParams): Promise<Page<Estacion>> {
    const { data } = await apiClient.get<Page<Estacion>>("/catalogos/estaciones", { params });
    return data;
  },
  /** Estaciones de un afiliado (lectura acotada, p.ej. detalle de Afiliado o combos). */
  async listPorAfiliado(afiliadoId: string, params?: ListParams): Promise<Page<Estacion>> {
    const { data } = await apiClient.get<Page<Estacion>>(
      `/catalogos/estaciones/afiliado/${afiliadoId}`,
      { params },
    );
    return data;
  },
};
