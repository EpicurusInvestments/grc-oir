/** Fix: llegar a "Órdenes del cliente" con una OC preseleccionada (p.ej. "Ver OC →" desde
 * el detalle de una orden interna) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio (mismo fix que
 * OrdenEstacionListPage.tsx para "Ver orden interna →").
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenClienteListPage } from "../ordenCliente/pages/OrdenClienteListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { makeOC } from "./fixtures";

function renderPage(ocIdPreseleccionada?: string) {
  const oc1 = makeOC({ id: "oc-1", folio_orden: "OC-2026-0041" });
  const oc2 = makeOC({ id: "oc-2", folio_orden: "OC-2026-0042" });
  const utils = render(
    <OrdenesProvider initialState={{ ordenesCliente: [oc1, oc2], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
      <OrdenClienteListPage
        ocIdPreseleccionada={ocIdPreseleccionada}
        onSeleccionarOE={vi.fn()}
        onAsignarEstaciones={vi.fn()}
      />
    </OrdenesProvider>,
  );
  const tabla = utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("Fix: OC preseleccionada filtra la tabla (no solo resalta la fila)", () => {
  it("sin preselección, se ven todas las OC", () => {
    const { tabla } = renderPage();
    expect(within(tabla).getByText("OC-2026-0041")).toBeInTheDocument();
    expect(within(tabla).getByText("OC-2026-0042")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });

  it("con una OC preseleccionada, el buscador arranca con su folio y la tabla muestra solo esa fila", () => {
    const { tabla } = renderPage("oc-2");

    const buscador = screen.getByPlaceholderText("Buscar folio, anunciante, no. de orden…");
    expect((buscador as HTMLInputElement).value).toBe("OC-2026-0042");

    expect(within(tabla).getByText("OC-2026-0042")).toBeInTheDocument();
    expect(within(tabla).queryByText("OC-2026-0041")).toBeNull();
    expect(screen.getByText("1 de 2")).toBeInTheDocument();
  });
});

describe("Fix: la tabla muestra columna Fecha y ordena de la más reciente a la más antigua", () => {
  it("una OC dada de alta después aparece primero, sin importar el orden en que llegaron los datos", () => {
    const vieja = makeOC({ id: "oc-vieja", folio_orden: "OC-2026-0041", created_at: "2026-01-01" });
    const nueva = makeOC({ id: "oc-nueva", folio_orden: "OC-2026-0050", created_at: "2026-06-15" });
    const utils = render(
      <OrdenesProvider initialState={{ ordenesCliente: [vieja, nueva], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenClienteListPage onSeleccionarOE={vi.fn()} onAsignarEstaciones={vi.fn()} />
      </OrdenesProvider>,
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;

    expect(within(tabla).getByText("Fecha")).toBeInTheDocument();
    const filas = within(tabla).getAllByRole("row").slice(1); // sin el encabezado
    expect(within(filas[0]).getByText("OC-2026-0050")).toBeInTheDocument();
    expect(within(filas[0]).getByText("2026-06-15")).toBeInTheDocument();
    expect(within(filas[1]).getByText("OC-2026-0041")).toBeInTheDocument();
  });
});
