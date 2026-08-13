/** Llamadas a /api/v1/auth. */

import { apiClient } from "@/shared/lib/apiClient";

import type { LoginIn, SesionOut, SesionUsuario } from "./types";

export async function login(credenciales: LoginIn): Promise<SesionOut> {
  const { data } = await apiClient.post<SesionOut>("/auth/login", credenciales);
  return data;
}

/** Identidad vigente según el backend.
 *
 * Se llama al montar la app para validar el token guardado: si expiró o el usuario fue
 * desactivado, responde 401 y la sesión se limpia ahí mismo, en vez de descubrirlo en la
 * primera acción del usuario. Además devuelve el ÁREA fresca (pudo cambiarla un admin).
 */
export async function obtenerSesion(): Promise<SesionUsuario> {
  const { data } = await apiClient.get<SesionUsuario>("/auth/me");
  return data;
}
