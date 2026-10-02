/** Pruebas de RENDER de `PeriodoTransmisionGrid.tsx` (ADR-107) — complementa
 * `PeriodoTransmisionGrid.test.ts`, que solo cubre `problemasDeFila` (función pura).
 *
 * Cubre: la columna "Horario de transmisión" (única, ya no "Hora inicio"/"Hora término"
 * separadas) y la columna "Material a Transmitir" — default visible incluso en un día sin
 * `orden_estacion_dia_id` (recién generado por el calendario, sin guardar todavía),
 * "Sustitución de Material" solo disponible en un día con id real (ícono → combo).
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PeriodoTransmisionGrid } from "../components/PeriodoTransmisionGrid";
import type { OrdenEstacionAudio } from "../types";
import { makeRow } from "./fixtures";

const RANGO = { inicio: "2025-06-01", fin: "2025-06-30" };
const AUDIOS: OrdenEstacionAudio[] = [
  { id: "au-1", nombre_archivo: "spot-verano.mp3", orden: 0 },
  { id: "au-2", nombre_archivo: "spot-invierno.mp3", orden: 1 },
];

describe("Horario de transmisión — columna única (ADR-107)", () => {
  it("ya no muestra 'Hora inicio'/'Hora término' como columnas separadas", () => {
    render(
      <PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} />,
    );
    expect(screen.getByText("Horario de transmisión")).toBeInTheDocument();
    expect(screen.queryByText("Hora inicio")).toBeNull();
    expect(screen.queryByText("Hora término")).toBeNull();
  });

  it("ADR-108: un solo input de hora — captura hora_inicio y hora_termino con el MISMO valor", () => {
    const onChange = vi.fn();
    const { container } = render(
      <PeriodoTransmisionGrid rows={[makeRow()]} onChange={onChange} rangoCampania={RANGO} />,
    );
    const horas = container.querySelectorAll('input[type="time"]');
    expect(horas).toHaveLength(1);
    fireEvent.change(horas[0], { target: { value: "10:00" } });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ hora_inicio: "10:00", hora_termino: "10:00" }),
    ]);
  });
});

describe("'+ Agregar día' — no choca con el unique constraint (ADR-134)", () => {
  it("corrige un bug real: si la fecha calculada topa con el fin de campaña, corre el horario en vez de repetirlo", () => {
    const onChange = vi.fn();
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ fecha: "2025-06-30", hora_inicio: "07:09", hora_termino: "07:09" })]}
        onChange={onChange}
        rangoCampania={RANGO}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));

    const filas = onChange.mock.calls[0][0];
    expect(filas).toHaveLength(2);
    const nueva = filas[1];
    // "+1 día" tope con `rangoCampania.fin` (2025-06-30, ya el último día) — se queda en
    // la MISMA fecha que la fila existente, así que el horario debe correrse.
    expect(nueva.fecha).toBe("2025-06-30");
    expect(nueva.hora_inicio).toBe("07:10");
    expect(nueva.hora_termino).toBe("07:10");
  });

  it("sin choque de horario, agrega la fila con el mismo horario de la última (comportamiento normal)", () => {
    const onChange = vi.fn();
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ fecha: "2025-06-10", hora_inicio: "08:00", hora_termino: "08:00" })]}
        onChange={onChange}
        rangoCampania={RANGO}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));

    const nueva = onChange.mock.calls[0][0][1];
    expect(nueva.fecha).toBe("2025-06-11");
    expect(nueva.hora_inicio).toBe("08:00");
  });
});

describe("Material a Transmitir — default visible y sustitución (ADR-107/ADR-108)", () => {
  it("sin pasar audios en absoluto (undefined), la columna no aparece", () => {
    render(<PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} />);
    expect(screen.queryByText("Material a Transmitir")).toBeNull();
  });

  it("ADR-108: al CREAR (audios=[], sin onAsignarAudio todavía) la columna SÍ aparece, con nota de que hay que guardar primero", () => {
    render(
      <PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} audios={[]} />,
    );
    expect(screen.getByText("Material a Transmitir")).toBeInTheDocument();
    expect(screen.getByText(/se sube y se asigna desde "Material a Transmitir" después de guardar/)).toBeInTheDocument();
  });

  it("un día SIN orden_estacion_dia_id (recién generado, sin guardar) muestra el default, sin botón de sustitución", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: undefined })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.getByText("Material a Transmitir")).toBeInTheDocument();
    expect(screen.getByText("spot-verano.mp3")).toBeInTheDocument(); // audios[0], el default
    expect(screen.queryByRole("button", { name: "Sustitución de Material" })).toBeNull();
  });

  it("un día CON orden_estacion_dia_id sin override muestra el default y SÍ ofrece sustituir", () => {
    const onAsignarAudio = vi.fn();
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-1" })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={onAsignarAudio}
      />,
    );
    expect(screen.getByText("spot-verano.mp3")).toBeInTheDocument();
    const boton = screen.getByRole("button", { name: "Sustitución de Material" });

    fireEvent.click(boton);
    const combo = screen.getByRole("combobox");
    fireEvent.change(combo, { target: { value: "au-2" } });

    expect(onAsignarAudio).toHaveBeenCalledWith("dia-1", "au-2");
  });

  it("ADR-128 (corrige un bug real): con UN solo audio subido, el combo no repite 'Default' y el mismo archivo", () => {
    const unSoloAudio: OrdenEstacionAudio[] = [{ id: "au-1", nombre_archivo: "unico.mp3", orden: 0 }];
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-1" })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={unSoloAudio}
        onAsignarAudio={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sustitución de Material" }));
    const combo = screen.getByRole("combobox");
    const opciones = within(combo).getAllByRole("option");
    expect(opciones).toHaveLength(1);
    expect(opciones[0]).toHaveTextContent("Default (unico.mp3)");
  });

  it("un día con override propio muestra el nombre de SU audio, no el default", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-2", orden_estacion_audio_id: "au-2" })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.getByText("spot-invierno.mp3")).toBeInTheDocument();
    expect(screen.queryByText("spot-verano.mp3")).toBeNull();
  });

  it("un día cancelado no muestra material ni botón de sustitución", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-3", cancelada: true })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.queryByText("spot-verano.mp3")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sustitución de Material" })).toBeNull();
  });

  it("sin ningún audio subido todavía, muestra '—' en vez de un nombre", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow()]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={[]}
        onAsignarAudio={vi.fn()}
      />,
    );
    const filas = screen.getAllByRole("row");
    expect(within(filas[1]).getByText("—")).toBeInTheDocument();
  });
});
