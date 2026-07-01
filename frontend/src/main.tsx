import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

// PrimeReact: tema base + core + iconos. Nuestro theme.css va DESPUÉS para aplicar los
// tokens del patrón aprobado (color por fase, IBM Plex) sobre los componentes.
import "primereact/resources/themes/lara-light-indigo/theme.css";
import "primereact/resources/primereact.min.css";
import "primeicons/primeicons.css";
import "@/shared/ui/theme.css";

import { router } from "@/app/router";
import { Providers } from "@/app/providers";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("No se encontró el elemento #root");

createRoot(rootEl).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
);
