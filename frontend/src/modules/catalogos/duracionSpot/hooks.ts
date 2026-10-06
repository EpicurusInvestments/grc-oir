/** Hooks de DuracionSpotCatalogo (CRUD genérico con invalidación por key "duracion_spot_catalogo"). */

import { useCatalog } from "@/shared/lib/useCatalog";

import { duracionSpotCatalogoApi } from "./api";

export const useDuracionesSpot = () =>
  useCatalog("duracion_spot_catalogo", duracionSpotCatalogoApi);
