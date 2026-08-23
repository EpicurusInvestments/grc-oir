/** Fix: la tabla de Incidencias debe ordenar de la más reciente a la más antigua por
 * cuándo se dio de alta la incidencia (`created_at`), no por `fecha_transmision` (que se
 * sigue mostrando en la columna "Fecha" tal cual, sin cambios).
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IncidenciaListPage } from "../incidencia/pages/IncidenciaListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { makeIncidencia, makeOC, makeOE } from "./fixtures";

describe("Fix: Incidencias ordena por alta (created_at), más reciente primero", () => {
  it("una incidencia dada de alta después aparece primero, aunque su fecha_transmision sea anterior", () => {
    const oc = makeOC({ id: "oc-1" });
    const oe = makeOE({ id: "oe-1", orden_id: oc.id, estatus: "reales_conciliados" });
    const vieja = makeIncidencia({ id: "inc-vieja", orden_interna_id: oe.id, fecha_transmision: "2025-06-10", created_at: "2026-01-01" });
    const nueva = makeIncidencia({ id: "inc-nueva", orden_interna_id: oe.id, fecha_transmision: "2025-06-01", created_at: "2026-06-15" });

    const utils = render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [oe], incidencias: [vieja, nueva], historialComisiones: [] }}>
        <IncidenciaListPage onVerOE={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;

    const filas = within(tabla).getAllByRole("row").slice(1); // sin el encabezado
    expect(within(filas[0]).getByText("2025-06-01")).toBeInTheDocument(); // fecha_transmision de la nueva
    expect(within(filas[1]).getByText("2025-06-10")).toBeInTheDocument(); // fecha_transmision de la vieja
    expect(screen.getByText(/2 de 2/)).toBeInTheDocument();
  });
});
