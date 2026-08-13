/** Guard de ruta: exige sesión para todo lo que cuelgue de él.
 *
 * Se usa como *layout route* (renderiza `<Outlet />`), así basta declararlo una vez en el
 * router y todas las pantallas quedan protegidas — incluidas las que se agreguen después.
 *
 * Mientras la sesión está `cargando` NO redirige: si lo hiciera, recargar la página con un
 * token válido rebotaría a /login antes de que /auth/me respondiera.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSession } from "@/modules/auth/sessionContext";

export function RequireSession() {
  const { estado, expiroLaSesion } = useSession();
  const location = useLocation();

  if (estado === "cargando") {
    return (
      <div className="login-page">
        <div className="state-msg" role="status">
          Verificando sesión…
        </div>
      </div>
    );
  }

  if (estado === "anonimo") {
    // `from` SOLO cuando la sesión se perdió trabajando: al re-entrar se retoma la
    // pantalla interrumpida. En un login desde cero no se manda, y el usuario aterriza en
    // el Dashboard (el Home real del sistema) aunque hubiera escrito otra URL.
    return (
      <Navigate to="/login" replace state={expiroLaSesion ? { from: location } : null} />
    );
  }

  return <Outlet />;
}
