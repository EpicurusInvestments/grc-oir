/** `SessionProvider`: resuelve y mantiene la sesión del usuario (F5-00).
 *
 * Estados (ver `sessionContext.ts`):
 *   `cargando`    — se valida el token guardado contra /auth/me. Sin este estado, recargar
 *                   la página rebotaría a /login antes de que la validación terminara.
 *   `autenticado` — hay usuario; `usuario` trae identidad y área.
 *   `anonimo`     — no hay sesión (nunca hubo, expiró o fue revocada).
 *
 * En modo `dev_headers` la sesión se da por hecha con los datos del `.env`: ese proveedor
 * no emite token y el backend resuelve la identidad por headers.
 *
 * El hook `useSession` vive en `sessionContext.ts` (requisito de Fast Refresh).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { login as loginApi, obtenerSesion } from "@/modules/auth/api";
import {
  SessionContext,
  type EstadoSesion,
  type SessionContextValue,
} from "@/modules/auth/sessionContext";
import type { SesionUsuario } from "@/modules/auth/types";
import { registrarCierreDeSesion, sincronizarUsuarioActual } from "@/shared/lib/currentUser";
import {
  borrarToken,
  esModoDevHeaders,
  guardarToken,
  leerToken,
  registrarManejadorSesionExpirada,
} from "@/shared/lib/session";

/** Usuario sintético del modo desarrollo (mismos valores que usaba `currentUser` antes). */
const USUARIO_DEV: SesionUsuario = {
  usuario_id: null,
  nombre_usuario: import.meta.env.VITE_DEV_USER ?? "dev.admin",
  email: null,
  area: import.meta.env.VITE_DEV_AREA ?? "admin",
};

export function SessionProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoSesion>(() => {
    if (esModoDevHeaders) return "autenticado";
    return leerToken() ? "cargando" : "anonimo";
  });
  const [usuario, setUsuario] = useState<SesionUsuario | null>(
    esModoDevHeaders ? USUARIO_DEV : null,
  );
  /** Ver `SessionContextValue.expiroLaSesion`: decide si tras re-loguearse se vuelve a la
   *  pantalla interrumpida o se entra al Dashboard. */
  const [expiroLaSesion, setExpiroLaSesion] = useState(false);

  /** Publica el usuario en el shim `currentUser` para las pantallas de F0 (ver H-4). */
  const aplicar = useCallback((nuevo: SesionUsuario | null, porExpiracion = false) => {
    sincronizarUsuarioActual(
      nuevo ? { username: nuevo.nombre_usuario, area: nuevo.area } : null,
    );
    setUsuario(nuevo);
    setEstado(nuevo ? "autenticado" : "anonimo");
    setExpiroLaSesion(nuevo ? false : porExpiracion);
  }, []);

  /** Cierre de sesión EXPLÍCITO (menú de usuario): no es una interrupción, así que al
   *  volver a entrar se aterriza en el Dashboard, no en la pantalla anterior. */
  const cerrarSesion = useCallback(() => {
    borrarToken();
    aplicar(null);
  }, [aplicar]);

  // Al montar: validar contra el backend el token guardado.
  useEffect(() => {
    if (esModoDevHeaders) {
      sincronizarUsuarioActual({
        username: USUARIO_DEV.nombre_usuario,
        area: USUARIO_DEV.area,
      });
      return;
    }
    if (!leerToken()) return;

    let vigente = true;
    obtenerSesion()
      .then((u) => {
        if (vigente) aplicar(u);
      })
      .catch(() => {
        // El token no sirve (expirado, alterado, usuario desactivado). El interceptor ya
        // lo borró en el 401; aquí se cierra el estado para que el guard mande a /login.
        if (vigente) cerrarSesion();
      });
    return () => {
      vigente = false;
    };
  }, [aplicar, cerrarSesion]);

  // Canales con el código que no puede usar hooks: el interceptor de 401 (apiClient) y el
  // botón "Cerrar sesión" del AppHeader (componente compartido).
  useEffect(() => {
    // 401 del backend estando dentro: la sesión se perdió a media tarea (`porExpiracion`).
    registrarManejadorSesionExpirada(() => aplicar(null, true));
    registrarCierreDeSesion(cerrarSesion);
    return () => {
      registrarManejadorSesionExpirada(null);
      registrarCierreDeSesion(null);
    };
  }, [aplicar, cerrarSesion]);

  const iniciarSesion = useCallback(
    async (email: string, password: string) => {
      const sesion = await loginApi({ email, password });
      guardarToken(sesion.access_token);
      aplicar(sesion.usuario);
    },
    [aplicar],
  );

  const valor = useMemo<SessionContextValue>(
    () => ({
      estado,
      usuario,
      esModoDesarrollo: esModoDevHeaders,
      expiroLaSesion,
      iniciarSesion,
      cerrarSesion,
    }),
    [estado, usuario, expiroLaSesion, iniciarSesion, cerrarSesion],
  );

  return <SessionContext.Provider value={valor}>{children}</SessionContext.Provider>;
}
