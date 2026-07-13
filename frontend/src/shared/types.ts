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

/** Entrada del historial de auditoría (gemela de `LogCambioParametroRead` del backend).
 * Alimenta la sección "Historial de cambios" del panel de detalle de los catálogos con
 * parámetros sensibles (Agencia, Anunciante, Contrato). */
export interface HistorialCambio {
  log_cambio_parametro_id: string;
  entidad: string;
  entidad_id: string;
  campo: string;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  usuario: string;
  ip: string | null;
  motivo_cambio: string | null;
  fecha_cambio: string;
}
