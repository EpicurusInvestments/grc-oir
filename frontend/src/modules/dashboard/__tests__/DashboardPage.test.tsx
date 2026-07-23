import { render, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DashboardPage } from "@/modules/dashboard/pages/DashboardPage";
import { phaseRegistry } from "@/shared/phases/phaseRegistry";

/** Acota las aserciones a la malla de tarjetas (el drawer global también monta los
 *  nombres de fase, así que buscamos solo dentro de .phase-grid). */
function renderGrid() {
  const { container } = render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
  const grid = container.querySelector<HTMLElement>(".phase-grid");
  if (!grid) throw new Error("No se encontró .phase-grid");
  return within(grid);
}

describe("DashboardPage", () => {
  it("muestra una tarjeta por cada fase del registro", () => {
    const grid = renderGrid();
    for (const phase of phaseRegistry) {
      expect(grid.getByText(phase.name)).toBeInTheDocument();
    }
  });

  it("solo F0 (Catálogos) es navegable; el resto aparece 'Próximamente'", () => {
    const grid = renderGrid();
    const inactivas = phaseRegistry.filter((p) => !p.enabled);

    // La fase activa se renderiza como <button> (clicable); las inactivas como <div>.
    expect(grid.getByText("Catálogos").closest("button")).not.toBeNull();
    expect(grid.getAllByText("Próximamente")).toHaveLength(inactivas.length);
    expect(phaseRegistry.filter((p) => p.enabled)).toHaveLength(1);
  });
});
