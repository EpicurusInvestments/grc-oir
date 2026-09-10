/** Router de la app.
 *  /login      → Inicio de sesión (PÚBLICA; única ruta fuera del guard).
 *  /           → Dashboard (Home real del sistema, malla de fases).
 *  /catalogos  → Explorador de catálogos (F0).
 *  /ordenes    → Explorador de órdenes (F1).
 *  /facturacion → Explorador de Facturación (F2).
 *  /cobranza   → Explorador de Cobranza y Pagos (F3).
 *  /seguridad  → Explorador de Seguridad (F5) — solo área admin.
 *
 *  Todo lo que cuelga de `RequireSession` exige sesión: al agregar una fase nueva basta
 *  meterla en `children` y queda protegida sin tocar el guard. `RequireArea` se anida
 *  encima SOLO cuando la pantalla entera pertenece a un área (como la gestión de
 *  usuarios); cuando el RBAC es por endpoint —Órdenes: Ventas captura, casi todas las
 *  áreas leen— basta la sesión, y el backend decide qué puede hacer cada quien.
 *  Al construir una fase nueva: darle `enabled`+`route` en phaseRegistry y montar su ruta aquí.
 */

import { createBrowserRouter } from "react-router-dom";

import { RequireArea } from "@/modules/auth/components/RequireArea";
import { RequireSession } from "@/modules/auth/components/RequireSession";
import { LoginPage } from "@/modules/auth/pages/LoginPage";
import { DashboardPage } from "@/modules/dashboard/pages/DashboardPage";
import { CatalogosExplorerPage } from "@/modules/catalogos/pages/CatalogosExplorerPage";
import { CobranzaExplorerPage } from "@/modules/cobranza/pages/CobranzaExplorerPage";
import { FacturacionExplorerPage } from "@/modules/facturacion/pages/FacturacionExplorerPage";
import { OrdenesExplorerPage } from "@/modules/ordenes/pages/OrdenesExplorerPage";
import { SeguridadExplorerPage } from "@/modules/seguridad/pages/SeguridadExplorerPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireSession />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/catalogos", element: <CatalogosExplorerPage /> },
      // DEMO VISUAL (datos dummy, sin backend) — ver docs/referencias/pantallas/Fase_1_-_Ordenes.html
      { path: "/ordenes", element: <OrdenesExplorerPage /> },
      { path: "/facturacion", element: <FacturacionExplorerPage /> },
      { path: "/cobranza", element: <CobranzaExplorerPage /> },
      {
        element: <RequireArea areas={["admin"]} />,
        children: [{ path: "/seguridad", element: <SeguridadExplorerPage /> }],
      },
    ],
  },
]);
