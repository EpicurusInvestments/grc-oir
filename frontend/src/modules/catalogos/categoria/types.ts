/** Tipos de Categoria, alineados al backend (app/modules/catalogos/categoria.py). */

import type { CatalogoBase } from "@/shared/types";

export interface Categoria extends CatalogoBase {
  categoria_id: string;
  nombre_categoria: string;
  descripcion_categoria: string | null;
}

export interface CategoriaCreate {
  nombre_categoria: string;
  descripcion_categoria?: string | null;
}

export type CategoriaUpdate = Partial<CategoriaCreate>;
