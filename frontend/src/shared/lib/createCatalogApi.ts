/** Gemelo del `build_crud_router` del backend: dado el nombre del recurso, devuelve las
 * funciones CRUD tipadas contra /api/v1/catalogos/<recurso>. Cada catálogo de F0-01+
 * solo aporta sus tipos (Read/Create/Update) y el nombre del recurso.
 */

import { apiClient } from "@/shared/lib/apiClient";
import type { ListParams, Page } from "@/shared/types";

export interface CatalogApi<Read, Create, Update> {
  resource: string;
  list: (params?: ListParams) => Promise<Page<Read>>;
  get: (id: string) => Promise<Read>;
  create: (data: Create) => Promise<Read>;
  update: (id: string, data: Update) => Promise<Read>;
  /** Baja/alta lógica. `forzar=true` completa una baja pese a dependientes activos
   *  (el backend responde 409 `dependencias_activas` cuando hace falta confirmar). */
  setEstado: (id: string, activo: boolean, forzar?: boolean) => Promise<Read>;
}

export function createCatalogApi<Read, Create, Update>(
  resource: string,
): CatalogApi<Read, Create, Update> {
  const base = `/catalogos/${resource}`;

  return {
    resource,
    async list(params) {
      const { data } = await apiClient.get<Page<Read>>(base, { params });
      return data;
    },
    async get(id) {
      const { data } = await apiClient.get<Read>(`${base}/${id}`);
      return data;
    },
    async create(payload) {
      const { data } = await apiClient.post<Read>(base, payload);
      return data;
    },
    async update(id, payload) {
      const { data } = await apiClient.put<Read>(`${base}/${id}`, payload);
      return data;
    },
    async setEstado(id, activo, forzar = false) {
      const { data } = await apiClient.post<Read>(`${base}/${id}/estado`, { activo, forzar });
      return data;
    },
  };
}
