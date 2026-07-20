/** API de CuentaContable sobre el CRUD genérico: /api/v1/catalogos/cuentas-contables. */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type { CuentaContable, CuentaContableCreate, CuentaContableUpdate } from "./types";

export const cuentaContableApi = createCatalogApi<
  CuentaContable,
  CuentaContableCreate,
  CuentaContableUpdate
>("cuentas-contables");
