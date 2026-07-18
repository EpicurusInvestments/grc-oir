/** Hooks de EmpresaFacturadora (CRUD genérico, invalidación por key "empresa_facturadora"). */

import { useCatalog } from "@/shared/lib/useCatalog";

import { empresaFacturadoraApi } from "./api";

export const useEmpresasFacturadoras = () =>
  useCatalog("empresa_facturadora", empresaFacturadoraApi);
