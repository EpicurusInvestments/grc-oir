/** Fix: llegar a "Órdenes internas" con una OI preseleccionada (p.ej. "Ver orden interna →"
 * desde Verificaciones o Incidencias) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionListPage } from "../ordenEstacion/pages/OrdenEstacionListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { makeOC, makeOE } from "./fixtures";

function renderPage(oeIdPreseleccionada?: string) {
  const oc = makeOC({ id: "oc-1" });
  const oe1 = makeOE({ id: "oe-1", folio_orden_interna: "OE-2026-0054A", orden_id: oc.id });
  const oe2 = makeOE({ id: "oe-2", folio_orden_interna: "OE-2026-0054B", orden_id: oc.id });
  const utils = render(
    <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [oe1, oe2], incidencias: [], historialComisiones: [] }}>
      <OrdenEstacionListPage oeIdPreseleccionada={oeIdPreseleccionada} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
    </OrdenesProvider>,
  );
  const tabla = utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("Fix: OI preseleccionada filtra la tabla (no solo resalta la fila)", () => {
  it("sin preselección, se ven todas las OI", () => {
    const { tabla } = renderPage();
    expect(within(tabla).getByText("OE-2026-0054A")).toBeInTheDocument();
    expect(within(tabla).getByText("OE-2026-0054B")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });

  it("con una OI preseleccionada, el buscador arranca con su folio y la tabla muestra solo esa fila", () => {
    const { tabla } = renderPage("oe-2");

    const buscador = screen.getByPlaceholderText("Buscar folio, estación, afiliado, OC de origen…");
    expect((buscador as HTMLInputElement).value).toBe("OE-2026-0054B");

    expect(within(tabla).getByText("OE-2026-0054B")).toBeInTheDocument();
    expect(within(tabla).queryByText("OE-2026-0054A")).toBeNull();
    expect(screen.getByText("1 de 2")).toBeInTheDocument();
  });
});
