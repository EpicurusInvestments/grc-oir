/** Router de la app.
 *  /           → Dashboard (Home real del sistema, malla de fases).
 *  /catalogos  → Explorador de catálogos (F0).
 *  Al construir una fase nueva: darle `enabled`+`route` en phaseRegistry y montar su ruta aquí.
 */

import { createBrowserRouter } from "react-router-dom";

import { DashboardPage } from "@/modules/dashboard/pages/DashboardPage";
import { CatalogosExplorerPage } from "@/modules/catalogos/pages/CatalogosExplorerPage";

export const router = createBrowserRouter([
  { path: "/", element: <DashboardPage /> },
  { path: "/catalogos", element: <CatalogosExplorerPage /> },
]);
