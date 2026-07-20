/** Cliente HTTP central contra /api/v1.
 *
 * - Base URL desde VITE_API_URL (el backend del compose en local).
 * - En desarrollo, envía los headers de auth dev (X-Dev-User/X-Dev-Area) si se
 *   configuran, para ejercitar el RBAC mientras el SSO está pendiente.
 * - Normaliza el sobre de error uniforme del backend a un Error con mensaje legible.
 */

import axios, { AxiosError } from "axios";

import type { ApiError } from "@/shared/types";

const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const apiClient = axios.create({ baseURL });

// Auth de desarrollo (solo si Vite corre en modo dev y hay valores configurados).
if (import.meta.env.DEV) {
  const devUser = import.meta.env.VITE_DEV_USER;
  const devArea = import.meta.env.VITE_DEV_AREA;
  if (devUser) apiClient.defaults.headers.common["X-Dev-User"] = devUser;
  if (devArea) apiClient.defaults.headers.common["X-Dev-Area"] = devArea;
}

/** Error de API con el código del backend (sin_permiso, no_encontrado, ...). */
export class ApiRequestError extends Error {
  codigo: string;
  detalles?: unknown;
  status?: number;

  constructor(codigo: string, mensaje: string, status?: number, detalles?: unknown) {
    super(mensaje);
    this.name = "ApiRequestError";
    this.codigo = codigo;
    this.status = status;
    this.detalles = detalles;
  }
}

/** POST de `multipart/form-data` (carga de archivos). Axios fija el boundary del
 *  Content-Type automáticamente al recibir un FormData. Lo usa la importación CSV. */
export async function postFormData<T>(url: string, formData: FormData): Promise<T> {
  const { data } = await apiClient.post<T>(url, formData);
  return data;
}

apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError<ApiError>) => {
    const sobre = error.response?.data?.error;
    if (sobre) {
      return Promise.reject(
        new ApiRequestError(sobre.codigo, sobre.mensaje, error.response?.status, sobre.detalles),
      );
    }
    return Promise.reject(
      new ApiRequestError("error_red", error.message || "Error de red", error.response?.status),
    );
  },
);
