/** Cliente HTTP central contra /api/v1.
 *
 * - Base URL desde VITE_API_URL (el backend del compose en local).
 * - **Sesión (F5-00)**: adjunta `Authorization: Bearer <token>` en cada petición. En modo
 *   `VITE_AUTH_PROVIDER=dev_headers` manda en su lugar los headers de desarrollo
 *   (X-Dev-User / X-Dev-Area), que es como trabajaba el equipo antes del login real.
 * - Un **401** del backend significa que la sesión ya no sirve (expirada, revocada o
 *   inexistente): se limpia y se avisa al `SessionProvider`, que redirige a /login.
 * - Normaliza el sobre de error uniforme del backend a un Error con mensaje legible.
 */

import axios, { AxiosError } from "axios";

import { esModoDevHeaders, leerToken, notificarSesionExpirada } from "@/shared/lib/session";
import type { ApiError } from "@/shared/types";

const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const apiClient = axios.create({ baseURL });

/** Ruta de login: su 401 es "credenciales incorrectas", NO "sesión expirada". Si no se
 *  distinguiera, un intento fallido dispararía el cierre de sesión y la redirección. */
const RUTA_LOGIN = "/auth/login";

// Identidad de desarrollo. Mutable a propósito (F1): el selector de usuario/área de la
// demo la cambia en caliente. La lee el INTERCEPTOR, no `defaults.headers.common` — si
// viviera en los defaults, el interceptor la pisaría en cada petición.
let devUser: string | undefined = import.meta.env.VITE_DEV_USER;
let devArea: string | undefined = import.meta.env.VITE_DEV_AREA;

/** Cambia la identidad de desarrollo en caliente (selector de la demo de F1) — sin esto,
 *  `X-Dev-User`/`X-Dev-Area` quedaban fijos al valor de `.env` desde la carga del módulo
 *  y no había forma de probar por UI un área distinta a la del arranque.
 *
 *  Solo tiene efecto con `VITE_AUTH_PROVIDER=dev_headers`: con login real (F5-00) el área
 *  sale del token y el cliente NO puede elegirla. */
export function setDevAuthHeaders(username?: string, area?: string): void {
  if (username) devUser = username;
  if (area) devArea = area;
}

apiClient.interceptors.request.use((config) => {
  if (esModoDevHeaders) {
    if (devUser) config.headers.set("X-Dev-User", devUser);
    if (devArea) config.headers.set("X-Dev-Area", devArea);
    return config;
  }

  // Se lee en CADA petición (no una sola vez al cargar): así el token del login recién
  // hecho se usa de inmediato, sin recargar la página.
  const token = leerToken();
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  return config;
});

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
    const esLogin = (error.config?.url ?? "").includes(RUTA_LOGIN);
    if (error.response?.status === 401 && !esLogin && !esModoDevHeaders) {
      notificarSesionExpirada();
    }

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
