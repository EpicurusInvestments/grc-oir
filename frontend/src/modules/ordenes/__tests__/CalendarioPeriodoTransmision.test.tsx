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

describe("CalendarioPeriodoTransmision — solo navega dentro del rango de campaña (ADR-132)", () => {
  it("arranca en el mes de inicio de la campaña, no en el mes actual", () => {
    render(
      <CalendarioPeriodoTransmision
        rows={[]}
        onGenerar={vi.fn()}
        rangoCampania={{ inicio: "2026-01-15", fin: "2026-03-10" }}
      />,
    );
    expect(screen.getByText(/enero 2026/i)).toBeInTheDocument();
  });

  it("no deja navegar antes del mes de inicio ni después del mes de fin de la campaña", () => {
    render(
      <CalendarioPeriodoTransmision
        rows={[]}
        onGenerar={vi.fn()}
        rangoCampania={{ inicio: "2026-01-15", fin: "2026-02-10" }}
      />,
    );
    // Un solo click hacia atrás ya debería quedar fuera de rango (arranca en enero).
    const anterior = screen.getByRole("button", { name: "Ir al mes anterior" });
    expect(anterior).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(screen.getByRole("button", { name: "Ir al mes siguiente" }));
    expect(screen.getByText(/febrero 2026/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ir al mes siguiente" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});

describe("CalendarioPeriodoTransmision — un registro por spot (ADR-127)", () => {
  it("'Spots por día' = 3 genera 3 filas (1 spot c/u) con horarios distintos, no 1 fila con spots_diarios=3", () => {
    const onGenerar = vi.fn();
    render(<CalendarioPeriodoTransmision rows={[]} onGenerar={onGenerar} rangoCampania={RANGO} />);

    // Un día cualquiera visible del mes actual (dentro del rango completo del año).
    fireEvent.click(screen.getByText("15"));

    const spotsInput = screen.getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(spotsInput, { target: { value: "3" } });

    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    expect(onGenerar).toHaveBeenCalledTimes(1);
    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(3);
    expect(filas.every((f: { spots_diarios: number }) => f.spots_diarios === 1)).toBe(true);
    expect(filas.every((f: { fecha: string }) => f.fecha === filas[0].fecha)).toBe(true);
    expect(filas.map((f: { hora_inicio: string }) => f.hora_inicio)).toEqual(["07:00", "07:01", "07:02"]);
    expect(filas.map((f: { hora_termino: string }) => f.hora_termino)).toEqual(["07:00", "07:01", "07:02"]);
  });
});
