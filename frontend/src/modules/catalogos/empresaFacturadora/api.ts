/** API de EmpresaFacturadora sobre el CRUD genérico:
 * /api/v1/catalogos/empresas-facturadoras. */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type {
  EmpresaFacturadora,
  EmpresaFacturadoraCreate,
  EmpresaFacturadoraUpdate,
} from "./types";

export const empresaFacturadoraApi = createCatalogApi<
  EmpresaFacturadora,
  EmpresaFacturadoraCreate,
  EmpresaFacturadoraUpdate
>("empresas-facturadoras");
