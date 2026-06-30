/** Router de la app. F0-00: una sola ruta → explorador de catálogos. */

import { createBrowserRouter } from "react-router-dom";

import { CatalogosExplorerPage } from "@/modules/catalogos/pages/CatalogosExplorerPage";

export const router = createBrowserRouter([
  { path: "/", element: <CatalogosExplorerPage /> },
  // F0-01+: rutas adicionales si algún catálogo necesita form full-screen propio.
]);
