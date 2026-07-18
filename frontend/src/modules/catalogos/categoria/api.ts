/** API de Categoria sobre el CRUD genérico: /api/v1/catalogos/categorias. */

import { createCatalogApi } from "@/shared/lib/createCatalogApi";

import type { Categoria, CategoriaCreate, CategoriaUpdate } from "./types";

export const categoriaApi = createCatalogApi<Categoria, CategoriaCreate, CategoriaUpdate>(
  "categorias",
);
