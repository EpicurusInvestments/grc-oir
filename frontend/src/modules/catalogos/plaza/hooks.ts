/** Hooks de Plaza (queries + mutations con invalidación) sobre el CRUD genérico. */

import { useCatalog } from "@/shared/lib/useCatalog";

import { plazaApi } from "./api";

export const usePlazas = () => useCatalog("plaza", plazaApi);
