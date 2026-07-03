/** API de Afiliado y Estación sobre el CRUD genérico.
 *
 * Afiliado: /api/v1/catalogos/afiliados (CRUD estándar).
 * Estación: /api/v1/catalogos/estaciones (CRUD estándar) + la ruta anidada
 *           GET /catalogos/estaciones/afiliado/{afiliado_id} para listar por afiliado.
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams, Page } from "@/shared/types";

import type {
  Afiliado,
  AfiliadoCreate,
  AfiliadoUpdate,
  Estacion,
  EstacionCreate,
  EstacionUpdate,
} from "./types";

export const afiliadoApi = createCatalogApi<Afiliado, AfiliadoCreate, AfiliadoUpdate>("afiliados");

const estacionCrud = createCatalogApi<Estacion, EstacionCreate, EstacionUpdate>("estaciones");

export const estacionApi = {
  ...estacionCrud,
  /** Estaciones de un afiliado (para el panel anidado). */
  async listPorAfiliado(afiliadoId: string, params?: ListParams): Promise<Page<Estacion>> {
    const { data } = await apiClient.get<Page<Estacion>>(
      `/catalogos/estaciones/afiliado/${afiliadoId}`,
      { params },
    );
    return data;
  },
};
