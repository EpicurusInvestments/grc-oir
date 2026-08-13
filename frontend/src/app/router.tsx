/** Router de la app.
 *  /login      → Inicio de sesión (PÚBLICA; única ruta fuera del guard).
 *  /           → Dashboard (Home real del sistema, malla de fases).
 *  /catalogos  → Explorador de catálogos (F0).
 *  /seguridad  → Explorador de Seguridad (F5) — solo área admin.
 *
 *  Todo lo que cuelga de `RequireSession` exige sesión: al agregar una fase nueva basta
 *  meterla en `children` y queda protegida sin tocar el guard. `RequireArea` se anida
 *  encima cuando además hay que restringir por área.
 *  Al construir una fase nueva: darle `enabled`+`route` en phaseRegistry y montar su ruta aquí.
 */

import { createBrowserRouter } from "react-router-dom";

import { RequireArea } from "@/modules/auth/components/RequireArea";
import { RequireSession } from "@/modules/auth/components/RequireSession";
import { LoginPage } from "@/modules/auth/pages/LoginPage";
import { DashboardPage } from "@/modules/dashboard/pages/DashboardPage";
import { CatalogosExplorerPage } from "@/modules/catalogos/pages/CatalogosExplorerPage";
import { SeguridadExplorerPage } from "@/modules/seguridad/pages/SeguridadExplorerPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireSession />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/catalogos", element: <CatalogosExplorerPage /> },
      {
        element: <RequireArea areas={["admin"]} />,
        children: [{ path: "/seguridad", element: <SeguridadExplorerPage /> }],
      },
    ],
  },
]);
