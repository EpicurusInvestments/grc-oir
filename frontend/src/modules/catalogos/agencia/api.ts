/** API de Agencia sobre el CRUD genérico: /api/v1/catalogos/agencias.
 *
 * Además del CRUD estándar, expone dos lecturas para el panel de detalle:
 *  - anunciantes de la agencia (`/catalogos/anunciantes/agencia/{id}`);
 *  - historial de auditoría de la agencia (`/catalogos/agencias/{id}/historial`).
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams, Page } from "@/shared/types";

import type { Agencia, AgenciaAnunciante, AgenciaCreate, AgenciaUpdate, HistorialCambio } from "./types";

const crud = createCatalogApi<Agencia, AgenciaCreate, AgenciaUpdate>("agencias");

export const agenciaApi = {
  ...crud,
  /** Anunciantes de una agencia (sección "Anunciantes representados"). */
  async anunciantesPorAgencia(
    agenciaId: string,
    params?: ListParams,
  ): Promise<Page<AgenciaAnunciante>> {
    const { data } = await apiClient.get<Page<AgenciaAnunciante>>(
      `/catalogos/anunciantes/agencia/${agenciaId}`,
      { params },
    );
    return data;
  },
  /** Historial de cambios a parámetros sensibles de la agencia (más reciente primero). */
  async historial(agenciaId: string): Promise<HistorialCambio[]> {
    const { data } = await apiClient.get<HistorialCambio[]>(
      `/catalogos/agencias/${agenciaId}/historial`,
    );
    return data;
  },
};
