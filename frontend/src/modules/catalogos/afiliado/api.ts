/** API de Afiliado (CRUD estándar) y ContactoAfiliado anidado (CRUD + listado por
 * afiliado). La Estación tiene su propia API desde ADR-094
 * (`modules/catalogos/estacion/api.ts`).
 */

import { apiClient } from "@/shared/lib/apiClient";
import { createCatalogApi } from "@/shared/lib/createCatalogApi";
import type { ListParams, Page } from "@/shared/types";

import type {
  Afiliado,
  AfiliadoCreate,
  AfiliadoUpdate,
  ContactoAfiliado,
  ContactoAfiliadoCreate,
  ContactoAfiliadoUpdate,
} from "./types";

export const afiliadoApi = createCatalogApi<Afiliado, AfiliadoCreate, AfiliadoUpdate>("afiliados");

const contactoAfiliadoCrud = createCatalogApi<
  ContactoAfiliado,
  ContactoAfiliadoCreate,
  ContactoAfiliadoUpdate
>("contactos-afiliado");

export const contactoAfiliadoApi = {
  ...contactoAfiliadoCrud,
  /** Contactos de un afiliado (para el panel anidado). */
  async listPorAfiliado(afiliadoId: string, params?: ListParams): Promise<Page<ContactoAfiliado>> {
    const { data } = await apiClient.get<Page<ContactoAfiliado>>(
      `/catalogos/contactos-afiliado/afiliado/${afiliadoId}`,
      { params },
    );
    return data;
  },
};
