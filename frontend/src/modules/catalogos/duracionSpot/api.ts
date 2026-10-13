/** API de DuracionSpotCatalogo sobre el CRUD genérico: /api/v1/catalogos/duraciones-spot. */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type {
  DuracionSpotCatalogo,
  DuracionSpotCatalogoCreate,
  DuracionSpotCatalogoUpdate,
} from "./types";

export const duracionSpotCatalogoApi = createCatalogApi<
  DuracionSpotCatalogo,
  DuracionSpotCatalogoCreate,
  DuracionSpotCatalogoUpdate
>("duraciones-spot");
