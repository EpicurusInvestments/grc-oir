/** Fase 4: generador de días de `periodo_transmision` a partir de un calendario —
 * selecciona varias fechas sueltas (no necesariamente seguidas) y captura UNA VEZ el
 * "Horario de transmisión" y los spots por día; se copian a cada fecha generada, pero
 * cada fila queda editable después en `PeriodoTransmisionGrid.tsx` (no cambia el modelo
 * de datos — decisión explícita del usuario: no un horario único de toda la orden).
 *
 * Complementa, no reemplaza, el "+ Agregar día" de la grid: ese sigue sirviendo para
 * sumar un día suelto rápido: este calendario es para armar varios de un jalón.
 *
 * ADR-107: las filas que genera NO traen `orden_estacion_audio_id` (nace `undefined`) —
 * eso YA significa "usa el material default" (el primero subido); `PeriodoTransmisionGrid`
 * lo resuelve y muestra su nombre de inmediato para cada fecha nueva, sin que este
 * componente tenga que saber nada de audios.
 *
 * ADR-108 (petición del usuario): "Horario de transmisión" pasa de un RANGO
 * (inicio/término) a UNA sola hora — `hora_inicio` y `hora_termino` (columnas del
 * modelo, sin cambio de esquema) se capturan con el MISMO valor, nunca por separado.
 *
 * ADR-127 (petición del usuario): "Spots por día" ya NO agrega una sola fila con
 * `spots_diarios = N` — genera UN REGISTRO POR SPOT (N filas, cada una con
 * `spots_diarios = 1`) para que el usuario pueda mover la hora y quitar/agregar spots
 * sueltos de esa fecha en la tabla de abajo. El modelo YA permite 2+ filas con la MISMA
 * fecha (`uq_orden_estacion_dia_oe_fecha_hora` incluye `hora_inicio`, no solo la fecha)
 * — para no chocar con ese unique constraint desde el primer guardado, cada fila nace
 * con un horario distinto (+1 minuto por fila, a partir del capturado); el usuario
 * reacomoda cada una a la hora real después.
 *
 * ADR-132 (petición del usuario): el calendario ya solo navega entre el mes de inicio y
 * el mes de fin de la campaña (`startMonth`/`endMonth`) — antes, aunque los días fuera
 * de rango salían deshabilitados, los MESES seguían siendo navegables sin límite (se
 * podía hojear todo el año). Arranca mostrando el mes de `rangoCampania.inicio`.
 */

import { useMemo, useState } from "react";
import { DayPicker } from "react-day-picker";
import { es } from "react-day-picker/locale";
import "react-day-picker/style.css";

import type { PeriodoTransmisionRow } from "../types";

interface CalendarioPeriodoTransmisionProps {
  rows: PeriodoTransmisionRow[];
  onGenerar: (nuevas: PeriodoTransmisionRow[]) => void;
  rangoCampania: { inicio: string; fin: string };
  disabled?: boolean;
}

function parseFechaLocal(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatoFechaLocal(fecha: Date): string {
  const y = fecha.getFullYear();
  const m = String(fecha.getMonth() + 1).padStart(2, "0");
  const d = String(fecha.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** ADR-127: separa por 1 minuto cada spot generado para la misma fecha (evita chocar
 * con `uq_orden_estacion_dia_oe_fecha_hora` desde el primer guardado); el usuario ajusta
 * cada horario real después. */
function sumarMinutos(hora: string, minutos: number): string {
  const [h, m] = hora.split(":").map(Number);
  const total = (((h * 60 + m + minutos) % 1440) + 1440) % 1440;
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

export function CalendarioPeriodoTransmision({
  rows,
  onGenerar,
  rangoCampania,
  disabled,
}: CalendarioPeriodoTransmisionProps) {
  const [fechasElegidas, setFechasElegidas] = useState<Date[]>([]);
  const [horario, setHorario] = useState("07:00");
  const [spotsPorDia, setSpotsPorDia] = useState("1");

  const fechasExistentes = useMemo(() => new Set(rows.map((r) => r.fecha)), [rows]);

  const generar = () => {
    const spots = Number.parseInt(spotsPorDia, 10) || 0;
    const fechas = fechasElegidas
      .map(formatoFechaLocal)
      .filter((fecha) => !fechasExistentes.has(fecha))
      .sort();
    const nuevas: PeriodoTransmisionRow[] = fechas.flatMap((fecha) =>
      Array.from({ length: spots }, (_, i) => ({
        fecha,
        hora_inicio: sumarMinutos(horario, i),
        hora_termino: sumarMinutos(horario, i),
        spots_diarios: 1,
      })),
    );
    if (nuevas.length === 0) return;
    onGenerar(nuevas);
    setFechasElegidas([]);
  };

  if (disabled) return null;

  return (
    <div className="form-card">
      <div className="form-card-title">Generar días desde calendario</div>
      <div className="form-card-sub">
        Elige varias fechas y captura el horario/spots una sola vez — se genera un registro POR SPOT (editable después en la
        tabla de abajo: puedes moverle la hora a cada uno, o quitar/agregar spots sueltos de una fecha).
      </div>

      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div className="rdp-wrapper">
          <DayPicker
            mode="multiple"
            locale={es}
            selected={fechasElegidas}
            onSelect={(fechas) => setFechasElegidas(fechas ?? [])}
            // ADR-132 (petición del usuario): antes se podía navegar a CUALQUIER mes
            // (todos los días fuera de la campaña salían deshabilitados, pero los meses
            // seguían siendo navegables) — ahora solo se puede navegar entre el mes de
            // inicio y el mes de fin de la campaña.
            defaultMonth={parseFechaLocal(rangoCampania.inicio)}
            startMonth={parseFechaLocal(rangoCampania.inicio)}
            endMonth={parseFechaLocal(rangoCampania.fin)}
            disabled={[
              { before: parseFechaLocal(rangoCampania.inicio) },
              { after: parseFechaLocal(rangoCampania.fin) },
              (fecha: Date) => fechasExistentes.has(formatoFechaLocal(fecha)),
            ]}
          />
        </div>

        <div style={{ flex: 1, minWidth: 200 }}>
          <div className="fl fl-required">Horario de transmisión</div>
          <input className="fi" style={{ maxWidth: 140 }} type="time" value={horario} onChange={(e) => setHorario(e.target.value)} />

          <div className="fl fl-required" style={{ marginTop: 8 }}>
            Spots por día
          </div>
          <input
            className="fi"
            style={{ maxWidth: 140, fontFamily: "var(--mono)" }}
            inputMode="numeric"
            value={spotsPorDia}
            onChange={(e) => setSpotsPorDia(e.target.value.replace(/\D/g, ""))}
          />

          <div className="fv muted" style={{ fontSize: 11, marginTop: 8 }}>
            {fechasElegidas.length} fecha(s) seleccionada(s)
          </div>
          <button
            type="button"
            className="btn btn-sm btn-teal"
            style={{ marginTop: 8 }}
            disabled={fechasElegidas.length === 0}
            onClick={generar}
          >
            + Generar {fechasElegidas.length * (Number.parseInt(spotsPorDia, 10) || 0) || ""} registro
            {fechasElegidas.length * (Number.parseInt(spotsPorDia, 10) || 0) === 1 ? "" : "s"}
          </button>
        </div>
      </div>
    </div>
  );
}
