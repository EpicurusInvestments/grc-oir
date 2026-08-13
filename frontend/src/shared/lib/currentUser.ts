/** Usuario actual — PUENTE entre la sesión real (F5-00) y el código que aún no usa hooks.
 *
 * Las 14 pantallas de F0 (y el `AppHeader`) leen `currentUser.area` de forma síncrona para
 * decidir qué acciones ofrecer. Cuando F5-00 introdujo la sesión real, se mantuvo este
 * objeto como **shim vivo**: el `SessionProvider` lo actualiza en cada cambio de sesión,
 * así ninguna de esas pantallas tuvo que tocarse (decisión H-4 del plan) y la rama de F1
 * en curso no entra en conflicto.
 *
 * ⚠️ No es reactivo: es una foto que se lee al renderizar. Funciona porque el árbol se
 * monta DESPUÉS de que la sesión está resuelta (ver `RequireSession`). Para código nuevo,
 * usar `useSession()` de `@/modules/auth/session`, que sí es reactivo.
 *
 * # TODO(F5): migrar las pantallas de F0 a `useSession()` y eliminar este módulo (PR aparte).
 */

import { esModoDevHeaders } from "@/shared/lib/session";

export interface UsuarioVisible {
  username: string;
  area: string;
}

/** Valores iniciales: en modo dev_headers son los del `.env` (comportamiento previo a
 *  F5-00); con login real se sobrescriben en cuanto la sesión se resuelve. */
export const currentUser: UsuarioVisible = {
  username: esModoDevHeaders ? (import.meta.env.VITE_DEV_USER ?? "dev.admin") : "",
  area: esModoDevHeaders ? (import.meta.env.VITE_DEV_AREA ?? "admin") : "",
};

/** Lo llama el `SessionProvider` al resolver, iniciar o cerrar sesión. */
export function sincronizarUsuarioActual(usuario: UsuarioVisible | null): void {
  currentUser.username = usuario?.username ?? "";
  currentUser.area = usuario?.area ?? "";
}

/** Cierre de sesión accesible desde componentes compartidos (`AppHeader`) sin que
 *  `shared/ui` tenga que importar un módulo de negocio. Lo registra el provider. */
let cerrarSesionRegistrado: (() => void) | null = null;

export function registrarCierreDeSesion(fn: (() => void) | null): void {
  cerrarSesionRegistrado = fn;
}

export function cerrarSesionActual(): void {
  cerrarSesionRegistrado?.();
}
