/** Fix: la tabla de Verificaciones debe ordenar de la más reciente a la más antigua por
 * cuándo la OI llegó a 2.3 (`actualizadaEn`, ver `verificacionDerivada` en selectors.ts),
 * no por la fecha de transmisión que muestra la columna "Fecha" (que no cambia).
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VerificacionListPage } from "../verificacion/pages/VerificacionListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { makeOC, makeOE, makeRow } from "./fixtures";

describe("Fix: Verificaciones ordena por cuándo llegó a 2.3, más reciente primero", () => {
  it("una OI que llegó a 2.3 después aparece primero, aunque transmitió antes", () => {
    const oc = makeOC({ id: "oc-1" });
    const vieja = makeOE({
      id: "oe-vieja",
      orden_id: oc.id,
      folio_orden_interna: "OE-2026-0041A",
      estatus: "reales_conciliados",
      periodo_transmision: [makeRow({ fecha: "2026-01-01" })],
      updated_at: "2026-01-02",
    });
    const nueva = makeOE({
      id: "oe-nueva",
      orden_id: oc.id,
      folio_orden_interna: "OE-2026-0050A",
      estatus: "reales_conciliados",
      periodo_transmision: [makeRow({ fecha: "2025-12-01" })],
      updated_at: "2026-06-15",
    });

    const utils = render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [vieja, nueva], incidencias: [], historialComisiones: [] }}>
        <VerificacionListPage onVerOE={vi.fn()} />
      </OrdenesProvider>,
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;

    const filas = within(tabla).getAllByRole("row").slice(1); // sin el encabezado
    expect(within(filas[0]).getByText("OE-2026-0050A")).toBeInTheDocument();
    expect(within(filas[1]).getByText("OE-2026-0041A")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });
});
