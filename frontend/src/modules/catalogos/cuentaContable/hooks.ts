/** Hooks de CuentaContable (CRUD genérico con invalidación por key "cuenta_contable"). */

import { useCatalog } from "@/shared/lib/useCatalog";

import { cuentaContableApi } from "./api";

export const useCuentasContables = () => useCatalog("cuenta_contable", cuentaContableApi);
