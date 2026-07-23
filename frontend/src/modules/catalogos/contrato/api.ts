/** API de Contrato sobre el CRUD genérico: /api/v1/catalogos/contratos.
 *
 * Además del CRUD: lista con filtro por estado, transición de estado (máquina de estados)
 * e historial de auditoría del contrato.
 */

import { apiClient, postFormData } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { HistorialCambio, ListParams, Page } from "@/shared/types";

import type {
  AdjuntoContrato,
  Contrato,
  ContratoCreate,
  ContratoUpdate,
  EstadoContrato,
} from "./types";

export interface ContratoListParams extends ListParams {
  estado?: EstadoContrato;
}

const crud = createCatalogApi<Contrato, ContratoCreate, ContratoUpdate>("contratos");

export const contratoApi = {
  ...crud,
  /** Lista con filtro `estado` (además de activo/q/paginación). */
  async list(params?: ContratoListParams): Promise<Page<Contrato>> {
    const { data } = await apiClient.get<Page<Contrato>>("/catalogos/contratos", { params });
    return data;
  },
  /** Transiciona `estado_contrato` (valida la máquina de estados; 409 si no permitida). */
  async transicionarEstado(id: string, estado: EstadoContrato): Promise<Contrato> {
    const { data } = await apiClient.post<Contrato>(
      `/catalogos/contratos/${id}/estado-contrato`,
      { estado },
    );
    return data;
  },
  /** Historial de cambios del % de comisión (más reciente primero). */
  async historial(id: string): Promise<HistorialCambio[]> {
    const { data } = await apiClient.get<HistorialCambio[]>(
      `/catalogos/contratos/${id}/historial`,
    );
    return data;
  },

  /** Adjuntos (PDF) del contrato. El bucket es privado: todo pasa por el backend. */
  adjuntos: {
    /** Lista los PDF del contrato. */
    async listar(id: string): Promise<AdjuntoContrato[]> {
      const { data } = await apiClient.get<AdjuntoContrato[]>(
        `/catalogos/contratos/${id}/adjuntos`,
      );
      return data;
    },
    /** Sube un PDF (multipart). El backend valida tipo y tamaño. */
    subir(id: string, archivo: File): Promise<AdjuntoContrato> {
      const fd = new FormData();
      fd.append("archivo", archivo);
      return postFormData<AdjuntoContrato>(`/catalogos/contratos/${id}/adjuntos`, fd);
    },
    /** Descarga el PDF como blob (con headers de auth) para ver/guardar en el navegador. */
    async descargar(id: string, nombre: string): Promise<Blob> {
      const { data } = await apiClient.get<Blob>(
        `/catalogos/contratos/${id}/adjuntos/${encodeURIComponent(nombre)}`,
        { responseType: "blob" },
      );
      return data;
    },
    /** Borra un PDF del contrato. */
    async borrar(id: string, nombre: string): Promise<void> {
      await apiClient.delete(
        `/catalogos/contratos/${id}/adjuntos/${encodeURIComponent(nombre)}`,
      );
    },
  },
};
