/** Llamadas a /api/v1/usuarios.
 *
 * El objeto cumple la forma `CatalogApi` para poder reutilizar `useCatalog` (queries y
 * mutations con invalidación), pero NO se usa `createCatalogApi`: ese factory antepone
 * `/catalogos/`, y los usuarios cuelgan de la raíz de la API. Además, establecer
 * contraseña es un endpoint propio de F5-00, fuera del CRUD estándar.
 */

import { apiClient } from "@/shared/lib/apiClient";
import type { CatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams, Page } from "@/shared/types";

import type { Usuario, UsuarioCreate, UsuarioUpdate } from "./types";

const base = "/usuarios";

export const usuarioApi: CatalogApi<Usuario, UsuarioCreate, UsuarioUpdate> = {
  resource: "usuarios",
  async list(params?: ListParams) {
    const { data } = await apiClient.get<Page<Usuario>>(base, { params });
    return data;
  },
  async get(id: string) {
    const { data } = await apiClient.get<Usuario>(`${base}/${id}`);
    return data;
  },
  async create(payload: UsuarioCreate) {
    const { data } = await apiClient.post<Usuario>(base, payload);
    return data;
  },
  async update(id: string, payload: UsuarioUpdate) {
    const { data } = await apiClient.put<Usuario>(`${base}/${id}`, payload);
    return data;
  },
  async setEstado(id: string, activo: boolean) {
    // `forzar` no aplica a usuarios (no tienen dependientes), pero el backend lo acepta.
    const { data } = await apiClient.post<Usuario>(`${base}/${id}/estado`, { activo });
    return data;
  },
};

/** (Re)establece la contraseña. Acción explícita y separada de editar el perfil. */
export async function establecerPassword(id: string, password: string): Promise<Usuario> {
  const { data } = await apiClient.post<Usuario>(`${base}/${id}/password`, { password });
  return data;
}
