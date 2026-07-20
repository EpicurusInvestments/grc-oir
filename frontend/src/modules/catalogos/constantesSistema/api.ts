/** API de ConstantesSistema: CRUD genérico + endpoints propios (conteos, importar).
 *
 * - `list` acepta el filtro extra `grupo` (el cliente genérico reenvía todo `params`).
 * - `conteos` alimenta las pills por grupo de la pantalla.
 * - `importar` sube el CSV como multipart/form-data (flujo dry-run/commit del backend).
 */

import { apiClient, postFormData } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type {
  ConstanteSistema,
  ConstanteSistemaCreate,
  ConstanteSistemaUpdate,
  ConteoGrupo,
  ModoDuplicados,
  ResultadoImportacion,
} from "./types";

const BASE = "/catalogos/constantes";

const crud = createCatalogApi<ConstanteSistema, ConstanteSistemaCreate, ConstanteSistemaUpdate>(
  "constantes",
);

export const constanteApi = {
  ...crud,

  /** Conteo por grupo (para las pills). `soloActivos=false` cuenta activas + inactivas. */
  async conteos(soloActivos = false): Promise<ConteoGrupo[]> {
    const { data } = await apiClient.get<ConteoGrupo[]>(`${BASE}/conteos`, {
      params: { solo_activos: soloActivos },
    });
    return data;
  },

  /** Carga masiva CSV. `commit=false` previsualiza (no escribe); `commit=true` aplica. */
  importar(
    archivo: File,
    commit: boolean,
    modo: ModoDuplicados,
  ): Promise<ResultadoImportacion> {
    const fd = new FormData();
    fd.append("archivo", archivo);
    fd.append("commit", String(commit));
    fd.append("modo_duplicados", modo);
    return postFormData<ResultadoImportacion>(`${BASE}/importar`, fd);
  },
};
