/** Hooks de Categoria (CRUD genérico con invalidación por key "categoria"). */

import { useCatalog } from "@/shared/lib/useCatalog";

import { categoriaApi } from "./api";

export const useCategorias = () => useCatalog("categoria", categoriaApi);
