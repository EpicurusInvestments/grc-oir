/** Pruebas de RENDER de `PeriodoTransmisionGrid.tsx` (ADR-107) — complementa
 * `PeriodoTransmisionGrid.test.ts`, que solo cubre `problemasDeFila` (función pura).
 *
 * Cubre: las columnas "Hora Inicio"/"Hora Fin" (ADR-185, revierte ADR-107/108: vuelven a
 * ser 2 columnas independientes) y la columna "Material a Transmitir" — default visible
 * incluso en un día sin `orden_estacion_dia_id` (recién generado por el calendario, sin
 * guardar todavía), "Sustitución de Material" solo disponible en un día con id real
 * (ícono → combo).
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

describe("Hora Inicio/Hora Fin — columnas independientes (ADR-185, revierte ADR-107/108)", () => {
  it("muestra 'Hora Inicio' y 'Hora Fin' como columnas separadas, no 'Horario de transmisión'", () => {
    render(
      <PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} />,
    );
    expect(screen.getByText("Hora Inicio")).toBeInTheDocument();
    expect(screen.getByText("Hora Fin")).toBeInTheDocument();
    expect(screen.queryByText("Horario de transmisión")).toBeNull();
  });

  it("2 inputs de hora independientes — cada uno edita SOLO su propio campo", () => {
    const onChange = vi.fn();
    // ADR-185: con 1 SOLO spot en el día, el grupo conserva un rango genuino (no se
    // reparte) — `spots_diarios: 1` a propósito (el default de `makeRow()` es 10).
    const { container } = render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ hora_inicio: "08:00", hora_termino: "08:00", spots_diarios: 1 })]}
        onChange={onChange}
        rangoCampania={RANGO}
      />,
    );
    const horas = container.querySelectorAll('input[type="time"]');
    expect(horas).toHaveLength(2);

    fireEvent.change(horas[0], { target: { value: "10:00" } });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ hora_inicio: "10:00", hora_termino: "08:00" }),
    ]);

    fireEvent.change(horas[1], { target: { value: "12:00" } });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ hora_inicio: "08:00", hora_termino: "12:00" }),
    ]);
  });

  it("editar Spots SIN rango (Hora Inicio === Hora Fin, el default de '+ Agregar día') NO reparte — 1 solo renglón, conserva su id real", () => {
    const onChange = vi.fn();
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ hora_inicio: "07:00", hora_termino: "07:00", spots_diarios: 1, orden_estacion_dia_id: "dia-9" })]}
        onChange={onChange}
        rangoCampania={RANGO}
      />,
    );
    const spotsInput = screen.getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(spotsInput, { target: { value: "50" } });

    expect(onChange).toHaveBeenCalledTimes(1);
    const filas = onChange.mock.calls[0][0];
    expect(filas).toHaveLength(1);
    expect(filas[0]).toMatchObject({
      hora_inicio: "07:00",
      hora_termino: "07:00",
      spots_diarios: 50,
      orden_estacion_dia_id: "dia-9",
    });
  });

  it("ADR-186 (corrige un bug real): con 5 filas generadas por el calendario (09:05–23:00), el grupo muestra Hora Fin = 23:00 capturada, NO un punto interior del reparto", () => {
    // Simula lo que `CalendarioPeriodoTransmision.tsx` genera para 5 spots en
    // 09:05–23:00: 5 filas con `hora_inicio` repartido y `hora_termino` COMPARTIDO
    // (= "23:00", el fin de rango capturado — ver `repartirHoras`, ADR-186).
    const filasGeneradas = [
      makeRow({ fecha: "2025-06-10", hora_inicio: "09:05", hora_termino: "23:00", spots_diarios: 1 }),
      makeRow({ fecha: "2025-06-10", hora_inicio: "11:53", hora_termino: "23:00", spots_diarios: 1 }),
      makeRow({ fecha: "2025-06-10", hora_inicio: "14:41", hora_termino: "23:00", spots_diarios: 1 }),
      makeRow({ fecha: "2025-06-10", hora_inicio: "17:29", hora_termino: "23:00", spots_diarios: 1 }),
      makeRow({ fecha: "2025-06-10", hora_inicio: "20:17", hora_termino: "23:00", spots_diarios: 1 }),
    ];
    render(<PeriodoTransmisionGrid rows={filasGeneradas} onChange={vi.fn()} rangoCampania={RANGO} />);

    expect(screen.getByDisplayValue("09:05")).toBeInTheDocument(); // Hora Inicio del grupo
    expect(screen.getByDisplayValue("23:00")).toBeInTheDocument(); // Hora Fin del grupo
    expect(screen.queryByDisplayValue("20:17")).toBeNull(); // NO el último punto del reparto
    expect(screen.getByDisplayValue("5")).toBeInTheDocument(); // Spots = la suma
    expect(screen.getAllByRole("row")).toHaveLength(3); // encabezado + 1 renglón agrupado + total
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

describe("Material a Transmitir — 1 material por spot, multi-select (ADR-187, revierte ADR-107/108)", () => {
  it("sin pasar audios en absoluto (undefined), la columna no aparece", () => {
    render(<PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} />);
    expect(screen.queryByText("Material a Transmitir")).toBeNull();
  });

  it("ADR-189 (corrige un bug real): un día SIN rango (1 sola fila real) con 2 spots capturados permite elegir 2 materiales — expande la fila en 2, repartiendo las horas por minuto", () => {
    const onChange = vi.fn();
    render(
      <PeriodoTransmisionGrid
        // "+ Agregar día" + Spots = 2: sigue siendo 1 SOLA fila real (sin rango), con
        // `spots_diarios = 2` como conteo — exactamente el caso reportado en vivo.
        rows={[makeRow({ hora_inicio: "07:00", hora_termino: "07:00", spots_diarios: 2, orden_estacion_audio_id: "au-1" })]}
        onChange={onChange}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    // El tope anunciado ya es 2 (los spots), no 1 (las filas reales que hay hoy).
    expect(screen.queryByText(/Máximo 1 material/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "spot-verano.mp3" }));
    fireEvent.click(screen.getByLabelText("spot-invierno.mp3"));

    expect(onChange).toHaveBeenCalledTimes(1);
    const filas = onChange.mock.calls[0][0];
    expect(filas).toHaveLength(2); // se expandió: 1 fila real → 2, una por spot
    expect(filas.map((f: { spots_diarios: number }) => f.spots_diarios)).toEqual([1, 1]);
    expect(filas.map((f: { orden_estacion_audio_id: string }) => f.orden_estacion_audio_id)).toEqual(["au-1", "au-2"]);
    // Sin rango real que repartir (Hora Inicio === Hora Fin): cada fila se separa 1
    // minuto a partir del punto capturado, solo para tener su propio hora_inicio.
    expect(filas.map((f: { hora_inicio: string }) => f.hora_inicio)).toEqual(["07:00", "07:01"]);
  });

  it("al CREAR (audios=[]) la columna SÍ aparece, con nota de que hay que guardar primero", () => {
    render(
      <PeriodoTransmisionGrid rows={[makeRow()]} onChange={vi.fn()} rangoCampania={RANGO} audios={[]} />,
    );
    expect(screen.getByText("Material a Transmitir")).toBeInTheDocument();
    expect(screen.getByText(/se sube y se asigna desde "Material a Transmitir" después de guardar/)).toBeInTheDocument();
  });

  it("un día SIN orden_estacion_dia_id (recién generado, sin guardar, sin permiteAsignacionLocal) muestra el material que le toca por posición, de solo lectura", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: undefined, spots_diarios: 1 })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.getByText("Material a Transmitir")).toBeInTheDocument();
    expect(screen.getByText("spot-verano.mp3")).toBeInTheDocument(); // único spot → 1er material, por posición
    expect(screen.queryByRole("textbox", { name: "" })).toBeNull(); // no hay multi-select editable
  });

  it("2 spots, solo 1 con material propio: el multi-select ofrece el otro y, al elegirlo, llama a onAsignarAudio SOLO de la fila que cambió", () => {
    const onAsignarAudio = vi.fn();
    render(
      <PeriodoTransmisionGrid
        rows={[
          makeRow({ fecha: "2025-06-05", orden_estacion_dia_id: "dia-a", spots_diarios: 1, orden_estacion_audio_id: "au-1" }),
          makeRow({ fecha: "2025-06-05", orden_estacion_dia_id: "dia-b", spots_diarios: 1, orden_estacion_audio_id: null }),
        ]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={onAsignarAudio}
      />,
    );
    // El campo cerrado muestra el material ya asignado; como falta 1 spot por cubrir
    // (2 spots, 1 material propio), el panel SÍ ofrece el otro (no deshabilitado).
    expect(screen.getByRole("button", { name: "spot-verano.mp3" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "spot-verano.mp3" }));
    const checkInvierno = screen.getByLabelText("spot-invierno.mp3") as HTMLInputElement;
    expect(checkInvierno).not.toBeDisabled();
    fireEvent.click(checkInvierno);

    // Reparte ["au-1","au-2"] 1 a 1 sobre [dia-a, dia-b] — dia-a no cambió (ya era au-1),
    // solo se llama para dia-b (que pasó de null a au-2).
    expect(onAsignarAudio).toHaveBeenCalledTimes(1);
    expect(onAsignarAudio).toHaveBeenCalledWith("dia-b", "au-2");
  });

  it("2 spots en el mismo día, cada uno con el material que le tocó por posición: el campo SOLO muestra el primero (no los junta) y, al abrir el panel, ambos quedan marcados", () => {
    // Simula lo que el generador/`+ Agregar día` ya habrían asignado por posición al
    // crear estas 2 filas (ADR-187: spot 1 → au-1, spot 2 → au-2).
    render(
      <PeriodoTransmisionGrid
        rows={[
          makeRow({ fecha: "2025-06-05", orden_estacion_dia_id: "dia-a", spots_diarios: 1, orden_estacion_audio_id: "au-1" }),
          makeRow({ fecha: "2025-06-05", orden_estacion_dia_id: "dia-b", spots_diarios: 1, orden_estacion_audio_id: "au-2" }),
        ]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    // El campo cerrado SOLO muestra el primero elegido (ADR-187, corrige el intento que
    // los juntaba todos — hacía la columna demasiado ancha con 2+ materiales).
    expect(screen.getByRole("button", { name: "spot-verano.mp3" })).toBeInTheDocument();
    expect(screen.queryByText("spot-verano.mp3, spot-invierno.mp3")).toBeNull();

    // Al abrir el panel sí se ven y marcan AMBOS (el resumen abreviado del campo cerrado
    // no limita lo que el panel deja ver/editar).
    fireEvent.click(screen.getByRole("button", { name: "spot-verano.mp3" }));
    expect(screen.getByLabelText("spot-verano.mp3")).toBeChecked();
    expect(screen.getByLabelText("spot-invierno.mp3")).toBeChecked();
    expect(screen.getByLabelText("spot-verano.mp3")).not.toBeDisabled();
  });

  it("un día con id real y SIN material asignado todavía (legado o recién guardado): el campo arranca con el placeholder, no inventa un default", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-x", spots_diarios: 1, orden_estacion_audio_id: null })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Elige material…" })).toBeInTheDocument();
  });

  it("ADR-187 (petición del usuario): un nombre de archivo largo se abrevia a 20 caracteres + '…', tanto en el campo cerrado como en la casilla de la lista", () => {
    const audioLargo: OrdenEstacionAudio[] = [
      { id: "au-largo", nombre_archivo: "Audio_3_30-Second-Timer-Bomb-MISSION-IMPOSSIBLE.mp3", orden: 0 },
    ];
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-y", spots_diarios: 1, orden_estacion_audio_id: "au-largo" })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={audioLargo}
        onAsignarAudio={vi.fn()}
      />,
    );
    const abreviado = "Audio_3_30-Second-Ti…"; // 20 caracteres + "…"
    expect(screen.getByRole("button", { name: abreviado })).toBeInTheDocument();
    expect(screen.queryByText(audioLargo[0].nombre_archivo)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: abreviado }));
    expect(screen.getByLabelText(abreviado)).toBeInTheDocument();
  });

  it("un día con override propio muestra el nombre de SU audio, no el de la posición por default", () => {
    render(
      <PeriodoTransmisionGrid
        rows={[makeRow({ orden_estacion_dia_id: "dia-2", orden_estacion_audio_id: "au-2", spots_diarios: 1 })]}
        onChange={vi.fn()}
        rangoCampania={RANGO}
        audios={AUDIOS}
        onAsignarAudio={vi.fn()}
      />,
    );
    expect(screen.getByText("spot-invierno.mp3")).toBeInTheDocument();
    expect(screen.queryByText("spot-verano.mp3")).toBeNull();
  });

  it("un día cancelado no muestra material", () => {
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
