/** Contexto de sesión + hook `useSession`.
 *
 * Separado de `session.tsx` (que exporta el componente `SessionProvider`) porque Fast
 * Refresh de Vite solo funciona bien si un archivo exporta únicamente componentes.
 */

import { createContext, useContext } from "react";

import type { SesionUsuario } from "@/modules/auth/types";

/** `cargando` = validando el token guardado contra el backend; hasta que resuelva no se
 *  puede decidir si redirigir a /login. */
export type EstadoSesion = "cargando" | "autenticado" | "anonimo";

export interface SessionContextValue {
  estado: EstadoSesion;
  usuario: SesionUsuario | null;
  /** True cuando el proveedor no pide login (dev_headers): la UI oculta el logout. */
  esModoDesarrollo: boolean;
  /** True SOLO si había sesión activa y se perdió (401 del backend) sin que el usuario
   *  cerrara sesión a propósito.
   *
   *  Distingue dos situaciones que a la vista son la misma pantalla de login:
   *  - **Expiró trabajando**: se interrumpió una tarea → al re-entrar se vuelve a donde
   *    estaba (p.ej. /catalogos).
   *  - **Login desde cero** (primera visita, logout explícito, token viejo en el
   *    navegador): no hay tarea que retomar → se entra al Dashboard.
   */
  expiroLaSesion: boolean;
  iniciarSesion: (email: string, password: string) => Promise<void>;
  cerrarSesion: () => void;
}

export const SessionContext = createContext<SessionContextValue | null>(null);

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession debe usarse dentro de <SessionProvider>");
  return ctx;
}
