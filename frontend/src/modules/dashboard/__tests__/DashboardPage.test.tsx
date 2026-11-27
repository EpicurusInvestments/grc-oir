import { render, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { DashboardPage } from "@/modules/dashboard/pages/DashboardPage";
import { currentUser } from "@/shared/lib/currentUser";
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
  const areaOriginal = currentUser.area;

  // `admin` ve TODAS las fases (ninguna `visibleParaArea` la excluye, ADR-040 también
  // aplica aquí) — es la condición bajo la que estas dos pruebas asumen "una tarjeta
  // por cada fase del registro".
  beforeEach(() => {
    currentUser.area = "admin";
  });

  afterEach(() => {
    currentUser.area = areaOriginal;
  });

  it("muestra una tarjeta por cada fase del registro (para un área que puede ver todas)", () => {
    const grid = renderGrid();
    for (const phase of phaseRegistry) {
      expect(grid.getByText(phase.name)).toBeInTheDocument();
    }
  });

  it("oculta por completo la tarjeta de una fase con `visibleParaArea` para un área sin ningún permiso adentro", () => {
    currentUser.area = "area_inexistente_sin_ningun_permiso";
    const faseConRestriccion = phaseRegistry.find((p) => p.visibleParaArea);
    if (!faseConRestriccion) return; // nada que probar si ninguna fase define la restricción
    const grid = renderGrid();
    expect(grid.queryByText(faseConRestriccion.name)).not.toBeInTheDocument();
  });

  it("las fases construidas son navegables; el resto aparece 'Próximamente'", () => {
    const grid = renderGrid();
    const activas = phaseRegistry.filter((p) => p.enabled);
    const inactivas = phaseRegistry.filter((p) => !p.enabled);

    // Las fases activas se renderizan como <button> (clicable); las inactivas como <div>.
    // La aserción se deriva del registro y NO de un conteo fijo: encender una fase nueva
    // (F1 encendió Órdenes, F5-00 encendió Seguridad) no debe obligar a tocar esta prueba.
    for (const fase of activas) {
      expect(grid.getByText(fase.name).closest("button")).not.toBeNull();
    }
    // `queryAllByText` (no `getAllByText`): con 0 fases inactivas (hoy, tras F4-01) no
    // hay ningún "Próximamente" que encontrar, y `getAllByText` lanza en ese caso en vez
    // de regresar un arreglo vacío.
    expect(grid.queryAllByText("Próximamente")).toHaveLength(inactivas.length);
    // Coherencia del registro: habilitada ⇔ tiene ruta. Es lo que rompería una fase mal
    // dada de alta, y no caduca al encender la siguiente.
    expect(activas.every((p) => p.route !== null)).toBe(true);
    expect(inactivas.every((p) => p.route === null)).toBe(true);
  });
});
