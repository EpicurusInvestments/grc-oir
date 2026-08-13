/** Guard de ruta por ÁREA. Se usa anidado dentro de `RequireSession`.
 *
 * Es solo UX: el backend valida el RBAC en cada endpoint (la pantalla no podría hacer
 * nada aunque alguien llegara). Por eso, en vez de redirigir en silencio —que se leería
 * como "la app está rota"— se muestra un mensaje claro con salida al Inicio.
 */

import { Navigate, Outlet, useNavigate } from "react-router-dom";

import { useSession } from "@/modules/auth/sessionContext";

interface RequireAreaProps {
  /** Áreas autorizadas. Hoy la gestión de usuarios es exclusiva de `admin`. */
  areas: string[];
}

export function RequireArea({ areas }: RequireAreaProps) {
  const { estado, usuario } = useSession();
  const navigate = useNavigate();

  // Defensa por si se monta fuera de RequireSession.
  if (estado !== "autenticado") return <Navigate to="/login" replace />;

  if (!usuario || !areas.includes(usuario.area)) {
    return (
      <div className="app-shell">
        <main className="dashboard-main">
          <div className="dashboard-inner">
            <div className="state-msg" role="alert">
              <p>
                Esta sección es exclusiva del área{" "}
                <strong>{areas.join(" o ")}</strong>. Tu área es{" "}
                <strong>{usuario?.area ?? "—"}</strong>.
              </p>
              <button
                type="button"
                className="btn btn-sm"
                style={{ marginTop: 14 }}
                onClick={() => navigate("/")}
              >
                Volver al inicio
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return <Outlet />;
}
