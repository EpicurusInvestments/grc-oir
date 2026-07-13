/** API de Anunciante + Marca anidada sobre el CRUD genérico.
 *
 * Anunciante: /api/v1/catalogos/anunciantes (CRUD) + lecturas del panel (marcas, contratos
 *   e historial de auditoría del anunciante).
 * Marca: /api/v1/catalogos/marcas (CRUD) + listado por anunciante para el panel anidado.
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { HistorialCambio, ListParams, Page } from "@/shared/types";

import type {
  Anunciante,
  AnuncianteContrato,
  AnuncianteCreate,
  AnuncianteUpdate,
  Marca,
  MarcaCreate,
  MarcaUpdate,
  Relacion,
} from "./types";

/** Params de lista con el filtro derivado Vía agencia / Directo. */
export interface AnuncianteListParams extends ListParams {
  relacion?: Relacion;
}

const anuncianteCrud = createCatalogApi<Anunciante, AnuncianteCreate, AnuncianteUpdate>(
  "anunciantes",
);

export const anuncianteApi = {
  ...anuncianteCrud,
  /** Lista con filtro `relacion` (además de activo/q/paginación). */
  async list(params?: AnuncianteListParams): Promise<Page<Anunciante>> {
    const { data } = await apiClient.get<Page<Anunciante>>("/catalogos/anunciantes", { params });
    return data;
  },
  /** Contratos del anunciante (sección "Contratos" del panel). */
  async contratosPorAnunciante(
    anuncianteId: string,
    params?: ListParams,
  ): Promise<Page<AnuncianteContrato>> {
    const { data } = await apiClient.get<Page<AnuncianteContrato>>(
      `/catalogos/contratos/anunciante/${anuncianteId}`,
      { params },
    );
    return data;
  },
  /** Historial de cambios a parámetros sensibles del anunciante (más reciente primero). */
  async historial(anuncianteId: string): Promise<HistorialCambio[]> {
    const { data } = await apiClient.get<HistorialCambio[]>(
      `/catalogos/anunciantes/${anuncianteId}/historial`,
    );
    return data;
  },
};

const marcaCrud = createCatalogApi<Marca, MarcaCreate, MarcaUpdate>("marcas");

export const marcaApi = {
  ...marcaCrud,
  /** Marcas de un anunciante (para el panel anidado). */
  async listPorAnunciante(anuncianteId: string, params?: ListParams): Promise<Page<Marca>> {
    const { data } = await apiClient.get<Page<Marca>>(
      `/catalogos/marcas/anunciante/${anuncianteId}`,
      { params },
    );
    return data;
  },
};
