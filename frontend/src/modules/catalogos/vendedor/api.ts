/** API de Vendedor sobre el CRUD genérico: /api/v1/catalogos/vendedores.
 * Incluye la lectura del historial de auditoría del % de comisión (como Agencia). */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { HistorialCambio } from "@/shared/types";

import type { Vendedor, VendedorCreate, VendedorUpdate } from "./types";

const crud = createCatalogApi<Vendedor, VendedorCreate, VendedorUpdate>("vendedores");

export const vendedorApi = {
  ...crud,
  /** Historial de cambios a `porcentaje_comision_default` (más reciente primero). */
  async historial(vendedorId: string): Promise<HistorialCambio[]> {
    const { data } = await apiClient.get<HistorialCambio[]>(
      `/catalogos/vendedores/${vendedorId}/historial`,
    );
    return data;
  },
};
