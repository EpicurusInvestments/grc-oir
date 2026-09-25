/** ADR-108: "Horario de transmisión" del generador por calendario pasa de un RANGO
 * (inicio/término, 2 campos) a UNA sola hora. No existía ninguna prueba de este
 * componente antes. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CalendarioPeriodoTransmision } from "../components/CalendarioPeriodoTransmision";

const RANGO = { inicio: "2026-01-01", fin: "2026-12-31" };

describe("CalendarioPeriodoTransmision — Horario de transmisión único (ADR-108)", () => {
  it("muestra UN solo campo 'Horario de transmisión', no 'inicio'/'término' separados", () => {
    render(<CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} />);

    expect(screen.getByText("Horario de transmisión")).toBeInTheDocument();
    expect(screen.queryByText(/Horario de transmisión — inicio/)).toBeNull();
    expect(screen.queryByText(/Horario de transmisión — término/)).toBeNull();
    expect(screen.getAllByDisplayValue("07:00")).toHaveLength(1);
  });

  it("no renderiza nada cuando disabled=true", () => {
    const { container } = render(
      <CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} disabled />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("cambiar el horario actualiza el único input de hora", () => {
    render(<CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} />);
    const input = screen.getByDisplayValue("07:00") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "15:30" } });
    expect(screen.getByDisplayValue("15:30")).toBeInTheDocument();
  });
});
