/** Tipos de Plaza, alineados a los schemas del backend (app/modules/catalogos/plaza.py). */

import type { CatalogoBase } from "@/shared/types";

export interface Plaza extends CatalogoBase {
  plaza_id: string;
  nombre_plaza: string;
  estado: string | null;
  /** Derivado (solo lectura): nº de estaciones en la plaza (todas). */
  estaciones_count: number;
}

export interface PlazaCreate {
  nombre_plaza: string;
  estado?: string | null;
}

export type PlazaUpdate = Partial<PlazaCreate>;
