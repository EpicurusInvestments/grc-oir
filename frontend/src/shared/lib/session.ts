/** Almacenamiento del token de sesión y señal de sesión expirada (F5-00).
 *
 * Módulo SIN React a propósito: lo consume tanto el `apiClient` (que no vive en el árbol
 * de componentes) como el `SessionProvider`. Aquí no hay llamadas HTTP ni estado de UI.
 *
 * Dónde vive el token: `localStorage`. Es lo más simple para una SPA que habla con un
 * backend en otro origen, y es un **riesgo aceptado y documentado** (ADR-028): un XSS
 * podría leerlo. La alternativa (cookie httpOnly + CSRF) se evaluará en F5 pleno.
 */

const CLAVE_TOKEN = "grcoir.token";

/** Proveedor de autenticación del frontend; debe coincidir con AUTH_PROVIDER del backend. */
export const authProvider = import.meta.env.VITE_AUTH_PROVIDER ?? "local";

/** Modo desarrollo: el backend resuelve la identidad por headers y NO hay login. */
export const esModoDevHeaders = authProvider === "dev_headers";

export function leerToken(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_TOKEN);
  } catch {
    // Navegador con almacenamiento bloqueado: se opera sin persistencia (se pedirá
    // login en cada recarga) en vez de romper la app.
    return null;
  }
}

export function guardarToken(token: string): void {
  try {
    window.localStorage.setItem(CLAVE_TOKEN, token);
  } catch {
    /* sin persistencia: la sesión dura lo que la pestaña */
  }
}

export function borrarToken(): void {
  try {
    window.localStorage.removeItem(CLAVE_TOKEN);
  } catch {
    /* nada que limpiar */
  }
}

/** Manejador que el `SessionProvider` registra para reaccionar a un 401 del backend. */
type ManejadorSesionExpirada = () => void;

let alExpirarSesion: ManejadorSesionExpirada | null = null;

/** El `SessionProvider` se registra aquí; el `apiClient` avisa por este canal.
 *
 * Se hace con un registro y no con `window.location` para que el cierre de sesión sea
 * una navegación de React Router (sin recargar la página ni perder el estado del árbol).
 */
export function registrarManejadorSesionExpirada(fn: ManejadorSesionExpirada | null): void {
  alExpirarSesion = fn;
}

export function notificarSesionExpirada(): void {
  borrarToken();
  alExpirarSesion?.();
}
