/** API de Plaza sobre el CRUD genérico (/api/v1/catalogos/plazas). */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type { Plaza, PlazaCreate, PlazaUpdate } from "./types";

export const plazaApi = createCatalogApi<Plaza, PlazaCreate, PlazaUpdate>("plazas");
