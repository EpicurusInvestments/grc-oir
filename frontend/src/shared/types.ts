/** Tipos compartidos, alineados a los schemas del backend (app/modules/catalogos/schemas.py).
 * Ideal a futuro: generarlos del OpenAPI con openapi-typescript. [[POR LLENAR]]
 */

/** Respuesta paginada estándar (gemela de `Page[T]` del backend). */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/** Parámetros de listado (gemelos de `ListParams`). */
export interface ListParams {
  page?: number;
  size?: number;
  activo?: boolean | null;
  q?: string | null;
}

/** Campos comunes de salida de todo catálogo (gemelo de `CatalogoReadBase`). */
export interface CatalogoBase {
  activo: boolean;
  created_at: string;
  updated_at: string | null;
}

/** Sobre de error uniforme del backend (core/errors.py). */
export interface ApiError {
  error: {
    codigo: string;
    mensaje: string;
    detalles?: unknown;
  };
}
