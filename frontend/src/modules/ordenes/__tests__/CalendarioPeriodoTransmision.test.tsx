/** ADR-108: "Horario de transmisión" del generador por calendario pasó de un RANGO
 * (inicio/término, 2 campos) a UNA sola hora. ADR-184 (petición del usuario) lo
 * REVIERTE: vuelve a ser un rango real — "Hora inicio"/"Hora fin". "Spots por día" = N
 * sigue generando N filas reales (una por spot, sin cambio de ADR-127) — lo único que
 * cambia es la FÓRMULA con la que se separan entre sí: con 1 solo spot, la fila conserva
 * el rango capturado tal cual; con 2+, se reparten uniformemente dentro del rango (ya no
 * sumando 1 minuto por fila). ADR-185 agrupa esas N filas por fecha en
 * `PeriodoTransmisionGrid.tsx` (cubierto en su propia suite) — este generador no cambia.
 * ADR-188: ya no bloquea elegir una fecha que ya tiene filas (ver su propio describe).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CalendarioPeriodoTransmision, repartirHoras } from "../components/CalendarioPeriodoTransmision";
import type { PeriodoTransmisionRow } from "../types";

const RANGO = { inicio: "2026-01-01", fin: "2026-12-31" };

describe("CalendarioPeriodoTransmision — Hora inicio/Hora fin (ADR-184, revierte ADR-108)", () => {
  it("muestra 'Hora inicio' y 'Hora fin' como campos separados, no un solo 'Horario de transmisión'", () => {
    render(<CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} />);

    expect(screen.getByText("Hora inicio")).toBeInTheDocument();
    expect(screen.getByText("Hora fin")).toBeInTheDocument();
    expect(screen.queryByText("Horario de transmisión")).toBeNull();
    expect(screen.getByDisplayValue("07:00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("22:00")).toBeInTheDocument();
  });

  it("no renderiza nada cuando disabled=true", () => {
    const { container } = render(
      <CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} disabled />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("cambiar Hora inicio y Hora fin actualiza cada input por separado", () => {
    const { container } = render(<CalendarioPeriodoTransmision rows={[]} onGenerar={vi.fn()} rangoCampania={RANGO} />);
    const inputs = container.querySelectorAll('input[type="time"]');
    expect(inputs).toHaveLength(2);

    fireEvent.change(inputs[0], { target: { value: "15:30" } });
    expect(screen.getByDisplayValue("15:30")).toBeInTheDocument();
    expect(screen.getByDisplayValue("22:00")).toBeInTheDocument(); // Hora fin sin tocar

    fireEvent.change(inputs[1], { target: { value: "18:00" } });
    expect(screen.getByDisplayValue("18:00")).toBeInTheDocument();
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

describe("CalendarioPeriodoTransmision — un registro por spot, repartido en el rango (ADR-127 + ADR-184)", () => {
  it("1 solo spot conserva el rango capturado TAL CUAL (no lo colapsa a un punto)", () => {
    const onGenerar = vi.fn();
    const { container } = render(<CalendarioPeriodoTransmision rows={[]} onGenerar={onGenerar} rangoCampania={RANGO} />);

    fireEvent.click(screen.getByText("15"));
    const inputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(inputs[0], { target: { value: "08:00" } });
    fireEvent.change(inputs[1], { target: { value: "20:00" } });

    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    expect(onGenerar).toHaveBeenCalledTimes(1);
    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(1);
    expect(filas[0].hora_inicio).toBe("08:00");
    expect(filas[0].hora_termino).toBe("20:00");
    expect(filas[0].spots_diarios).toBe(1);
  });

  it("'Spots por día' = 3 con rango 07:00–08:00 genera 3 filas (1 spot c/u) repartidas uniformemente, no 1 fila con spots_diarios=3", () => {
    const onGenerar = vi.fn();
    const { container } = render(<CalendarioPeriodoTransmision rows={[]} onGenerar={onGenerar} rangoCampania={RANGO} />);

    fireEvent.click(screen.getByText("15"));
    const inputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(inputs[1], { target: { value: "08:00" } }); // Hora fin: rango de 60 min
    const spotsInput = screen.getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(spotsInput, { target: { value: "3" } });

    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    expect(onGenerar).toHaveBeenCalledTimes(1);
    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(3);
    expect(filas.every((f: { spots_diarios: number }) => f.spots_diarios === 1)).toBe(true);
    expect(filas.every((f: { fecha: string }) => f.fecha === filas[0].fecha)).toBe(true);
    // 60 min / 3 spots = intervalo de 20 min: 07:00, 07:20, 07:40 — cada uno un PUNTO de
    // inicio distinto, pero TODOS comparten `hora_termino = "08:00"` (el fin de rango
    // CAPTURADO, ADR-186) — así, al agrupar por fecha para mostrarlas, "Hora Fin" se
    // recupera exacta (la máxima de las 3 es "08:00", no un punto interior del reparto).
    expect(filas.map((f: { hora_inicio: string }) => f.hora_inicio)).toEqual(["07:00", "07:20", "07:40"]);
    expect(filas.map((f: { hora_termino: string }) => f.hora_termino)).toEqual(["08:00", "08:00", "08:00"]);
  });

  it("elegir varias fechas repite el reparto en cada una", () => {
    const onGenerar = vi.fn();
    render(<CalendarioPeriodoTransmision rows={[]} onGenerar={onGenerar} rangoCampania={RANGO} />);

    fireEvent.click(screen.getByText("15"));
    fireEvent.click(screen.getByText("16"));
    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    expect(onGenerar).toHaveBeenCalledTimes(1);
    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(2); // 1 spot por defecto × 2 fechas
    expect(new Set(filas.map((f: { fecha: string }) => f.fecha)).size).toBe(2);
  });

  it("con 2+ spots y Hora fin NO posterior a Hora inicio, bloquea 'Generar' con un mensaje explícito", () => {
    const onGenerar = vi.fn();
    const { container } = render(<CalendarioPeriodoTransmision rows={[]} onGenerar={onGenerar} rangoCampania={RANGO} />);

    fireEvent.click(screen.getByText("15"));
    const spotsInput = screen.getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(spotsInput, { target: { value: "3" } });
    const inputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(inputs[1], { target: { value: "07:00" } }); // Hora fin = Hora inicio (07:00)

    expect(screen.getByText(/"Hora fin" no puede ser anterior a "Hora inicio"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generar/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));
    expect(onGenerar).not.toHaveBeenCalled();
  });
});

describe("CalendarioPeriodoTransmision — una fecha puede repetirse (ADR-188, petición del usuario)", () => {
  const filaExistente: PeriodoTransmisionRow = {
    fecha: "2026-01-15",
    hora_inicio: "07:00",
    hora_termino: "07:00",
    spots_diarios: 1,
  };

  it("una fecha que ya tiene filas ya NO sale deshabilitada en el calendario", () => {
    render(<CalendarioPeriodoTransmision rows={[filaExistente]} onGenerar={vi.fn()} rangoCampania={RANGO} />);
    const boton15 = screen.getByText("15").closest("button") as HTMLButtonElement;
    expect(boton15).not.toBeDisabled();
    expect(boton15).not.toHaveAttribute("aria-disabled", "true");
  });

  it("generar sobre una fecha que ya tiene una fila (punto) no la descarta — agrega una fila nueva con hora_inicio/hora_termino corridos para no chocar", () => {
    const onGenerar = vi.fn();
    const { container } = render(
      <CalendarioPeriodoTransmision rows={[filaExistente]} onGenerar={onGenerar} rangoCampania={RANGO} />,
    );
    const inputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(inputs[0], { target: { value: "07:00" } });
    fireEvent.change(inputs[1], { target: { value: "07:00" } }); // mismo punto que la fila existente

    fireEvent.click(screen.getByText("15"));
    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    expect(onGenerar).toHaveBeenCalledTimes(1);
    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(1);
    expect(filas[0].fecha).toBe("2026-01-15");
    // "07:00" ya estaba ocupado por `filaExistente" — se corre a "07:01", AMBOS campos
    // (es un punto: hora_inicio === hora_termino), para no violar hora_fin >= hora_inicio.
    expect(filas[0].hora_inicio).toBe("07:01");
    expect(filas[0].hora_termino).toBe("07:01");
  });

  it("con rango real (no un punto), solo corre hora_inicio si choca — hora_termino sigue siendo el fin de rango capturado", () => {
    const onGenerar = vi.fn();
    const { container } = render(
      <CalendarioPeriodoTransmision rows={[filaExistente]} onGenerar={onGenerar} rangoCampania={RANGO} />,
    );
    const inputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(inputs[0], { target: { value: "07:00" } }); // choca con filaExistente
    fireEvent.change(inputs[1], { target: { value: "10:00" } }); // rango real, no un punto

    fireEvent.click(screen.getByText("15"));
    fireEvent.click(screen.getByRole("button", { name: /Generar/ }));

    const filas = onGenerar.mock.calls[0][0];
    expect(filas).toHaveLength(1);
    expect(filas[0].hora_inicio).toBe("07:01");
    expect(filas[0].hora_termino).toBe("10:00"); // el fin de rango capturado, sin cambio
  });
});

describe("repartirHoras — nunca genera hora_inicio repetidos (ADR-190, corrige un bug real)", () => {
  it("un rango angosto (1 minuto) con 6 spots producía hora_inicio DUPLICADOS por redondeo — ahora los 6 son distintos", () => {
    const filas = repartirHoras("20:13", "20:14", 6);
    const horas = filas.map((f) => f.hora_inicio);
    expect(new Set(horas).size).toBe(6); // nunca se repite ninguno
    // Como el rango capturado (1 min) no alcanza para 6 puntos distintos, se corren +1
    // minuto cada vez que chocan: 20:13, 20:14, 20:15, 20:16, 20:17, 20:18.
    expect(horas).toEqual(["20:13", "20:14", "20:15", "20:16", "20:17", "20:18"]);
  });

  it("si el reparto se corre más allá de 'horaFin' capturada, el fin efectivo de TODAS las filas se extiende (hora_fin >= hora_inicio en cada una)", () => {
    const filas = repartirHoras("20:13", "20:14", 6);
    filas.forEach((f) => expect(f.hora_termino >= f.hora_inicio).toBe(true));
    // Todas comparten el mismo fin efectivo (el más tardío de los puntos, no el
    // "20:14" originalmente capturado — ADR-186 sigue compartiéndolo entre todas).
    const fines = new Set(filas.map((f) => f.hora_termino));
    expect(fines.size).toBe(1);
    expect([...fines][0]).toBe("20:18");
  });

  it("con un rango ancho de sobra (sin colisiones), el comportamiento no cambia", () => {
    const filas = repartirHoras("07:00", "08:00", 3);
    expect(filas.map((f) => f.hora_inicio)).toEqual(["07:00", "07:20", "07:40"]);
    expect(filas.every((f) => f.hora_termino === "08:00")).toBe(true);
  });
});
