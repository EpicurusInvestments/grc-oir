/** Fase 4: generador de días de `periodo_transmision` a partir de un calendario —
 * selecciona varias fechas sueltas (no necesariamente seguidas) y captura UNA VEZ el
 * horario/spots; se copian a cada fecha generada, pero cada fila queda editable después
 * en `PeriodoTransmisionGrid.tsx` (no cambia el modelo de datos).
 *
 * Complementa, no reemplaza, el "+ Agregar día" de la grid: ese sigue sirviendo para
 * sumar un día suelto rápido: este calendario es para armar varios de un jalón.
 *
 * ADR-107: las filas que genera traen su propio `orden_estacion_audio_id` ya resuelto
 * (ver ADR-187 — ya NO existe un solo "material default" para todos los días).
 *
 * ADR-108 (petición del usuario): "Horario de transmisión" pasó de un RANGO
 * (inicio/término) a UNA sola hora. **REVERTIDO en ADR-184** (ver abajo).
 *
 * ADR-127 (petición del usuario): "Spots por día" = N genera UN REGISTRO POR SPOT (N
 * filas reales, cada una con `spots_diarios = 1`) — SIGUE IGUAL (ver ADR-185): cada spot
 * sigue siendo su propia fila real en `OrdenEstacionDia`, para que "Capturar reales" y la
 * carga del layout de reales NO necesiten ningún cambio. Lo único que cambió de ADR-127
 * a hoy es la FÓRMULA con la que se separan entre sí dentro de una misma fecha (ver
 * ADR-184 abajo): antes sumaba 1 minuto por fila a partir de un solo horario; ahora
 * reparte uniformemente el rango capturado.
 *
 * ADR-132 (petición del usuario): el calendario ya solo navega entre el mes de inicio y
 * el mes de fin de la campaña (`startMonth`/`endMonth`) — antes, aunque los días fuera
 * de rango salían deshabilitados, los MESES seguían siendo navegables sin límite (se
 * podía hojear todo el año). Arranca mostrando el mes de `rangoCampania.inicio`.
 *
 * ADR-184 (petición del usuario): "Horario de transmisión" (un solo campo, ADR-108)
 * vuelve a ser un RANGO real — "Hora inicio"/"Hora fin". Con N spots para una fecha,
 * cada una de las N filas generadas sigue siendo un registro real independiente (sin
 * cambio de ADR-127). Con 1 solo spot, la única fila conserva el rango capturado TAL
 * CUAL (`hora_inicio`/`hora_termino` reales, posiblemente distintos — igual que antes de
 * ADR-127). Con 2+ spots, el horario de cada fila ya NO se separa sumando 1 minuto desde
 * un único punto: se reparte UNIFORMEMENTE dentro del rango — `intervalo = (hora_fin −
 * hora_inicio) / N`, fila i en `hora_inicio + i×intervalo` (i = 0..N-1), cada una como un
 * PUNTO (`hora_inicio === hora_termino`). Si capturan 2+ spots y Hora fin no es
 * estrictamente posterior a Hora inicio, el intervalo sería 0 (todas las filas caerían
 * en la MISMA hora, violando `uq_orden_estacion_dia_oe_fecha_hora` al guardar) — se
 * bloquea "Generar" con un mensaje explícito en ese caso.
 *
 * ADR-185 (petición del usuario, corrige un primer intento fallido de este mismo ADR-184
 * que sí llegó a probarse en vivo): el primer intento hizo que la GRID
 * (`PeriodoTransmisionGrid.tsx`) mostrara las N filas reales por separado (una por
 * spot) — el usuario señaló que la grid debía seguir viéndose como "un solo registro por
 * fecha", con sus columnas Hora Inicio/Hora Fin editables, exactamente como antes de
 * ADR-127. La solución correcta (ver `PeriodoTransmisionGrid.tsx`): la GRID agrupa/
 * colapsa las N filas de una misma fecha en UN renglón visual (Hora Inicio = la más
 * temprana del grupo, Hora Fin = la más tardía, Spots = el total) — las N filas reales
 * siguen existiendo tal cual por dentro (mismo arreglo `rows`/`periodo_transmision` de
 * siempre), así que "Capturar reales", el layout CSV y el backend NO cambian en nada.
 *
 * ADR-187 (petición del usuario) — ya NO hay un solo "material default" para todos los
 * días: cada SPOT recibe su propio material por POSICIÓN, en el orden en que se subieron
 * ("spot 1 → material 1, spot 2 → material 2…"), repitiendo cíclicamente si hay menos
 * materiales que spots ese día (confirmado con el usuario). Si hay MÁS materiales que
 * spots, los sobrantes simplemente no se usan ESE día (`asignarPorPosicion`, abajo). Esto
 * se resuelve aquí mismo, al generar — cada fila nueva nace con su `orden_estacion_audio_id`
 * ya puesto (ya no queda en blanco esperando un fallback). Ver `PeriodoTransmisionGrid.tsx`
 * para la columna "Material a Transmitir" (ahora un multi-select).
 *
 * ADR-188 (petición del usuario) — el calendario YA NO bloquea elegir una fecha que ya
 * tiene filas: antes, una fecha con registros salía deshabilitada en el DayPicker y
 * `generar()` la descartaba en silencio. El usuario confirmó que SÍ puede repetirse una
 * fecha — y, gracias a que la grid ya agrupa por fecha (ADR-185), generar MÁS filas para
 * una fecha existente se ve automáticamente como "sumar spots al mismo renglón" (Spots =
 * el total de TODAS sus filas, Hora Inicio/Fin se amplían para cubrir ambos rangos) — no
 * hizo falta ninguna lógica de "fusión" aparte. Lo único que si hay que cuidar: los
 * puntos nuevos no deben chocar con `hora_inicio` de las filas YA existentes de esa
 * fecha (mismo unique constraint que ya resolvía "+ Agregar día" — ADR-134): se corren
 * +1 minuto hasta encontrar uno libre, antes de asignarlos.
 */

import { useState } from "react";
import { DayPicker } from "react-day-picker";
import { es } from "react-day-picker/locale";
import "react-day-picker/style.css";

import type { OrdenEstacionAudio, PeriodoTransmisionRow } from "../types";

interface CalendarioPeriodoTransmisionProps {
  rows: PeriodoTransmisionRow[];
  onGenerar: (nuevas: PeriodoTransmisionRow[]) => void;
  rangoCampania: { inicio: string; fin: string };
  /** ADR-187: materiales disponibles, en el orden en que se subieron — se reparten 1 por
   *  spot (ver `asignarPorPosicion`). Sin pasar nada (o `[]`), las filas nacen sin
   *  material (`orden_estacion_audio_id: null`). */
  audios?: OrdenEstacionAudio[];
  disabled?: boolean;
}

/** ADR-187: reparte `ids` (en el orden dado) entre `cantidad` posiciones, repitiendo
 * cíclicamente si hay menos ids que posiciones — "spot 1 → material 1, spot 2 →
 * material 2, spot 3 → material 1…". Con `ids` vacío, regresa `cantidad` nulls (sin
 * material subido todavía). Exportada: `PeriodoTransmisionGrid.tsx` la reusa para el
 * multi-select de "Material a Transmitir" y para regenerar un grupo al editarlo. */
export function asignarPorPosicion(ids: string[], cantidad: number): (string | null)[] {
  if (ids.length === 0) return Array.from({ length: cantidad }, () => null);
  return Array.from({ length: cantidad }, (_, i) => ids[i % ids.length]);
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

function minutosDelDia(hora: string): number {
  const [h, m] = hora.split(":").map(Number);
  return h * 60 + m;
}

function sumarMinutos(hora: string, minutos: number): string {
  const total = (((minutosDelDia(hora) + minutos) % 1440) + 1440) % 1440;
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** Una fila real de `periodo_transmision`: siempre tiene su PROPIO `hora_inicio` — con 1
 * solo spot, `hora_termino` es el fin del rango capturado (un rango genuino); con 2+
 * spots, cada fila comparte el MISMO `hora_termino` (el fin del rango tal cual se
 * capturó) y solo varía su `hora_inicio` (el punto que le tocó dentro del rango). Esto es
 * lo que permite que, al re-agrupar N filas de una misma fecha para mostrarlas como un
 * solo renglón (`PeriodoTransmisionGrid.tsx`: Hora Inicio = la mínima, Hora Fin = la
 * máxima), se recupere EXACTAMENTE el rango que el usuario tecleó — no un punto interior
 * del reparto (ver ADR-186, corrige un bug real: con 5 spots en 09:05–23:00, la fila
 * mostraba Hora Fin = 20:13, un punto calculado, en vez de las 23:00 capturadas). */
export interface RangoHora {
  hora_inicio: string;
  hora_termino: string;
}

/** ADR-184/185/186: reparte N spots dentro de [horaInicio, horaFin]. Con 1 solo spot NO
 * hay nada que repartir — esa única fila conserva el rango capturado TAL CUAL (igual que
 * antes de ADR-127: una fila por día, con una hora de inicio y una de fin reales). Con
 * 2+ spots, cada fila nace en un PUNTO uniformemente espaciado dentro del rango —
 * `intervalo = (hora_fin − hora_inicio) / N`, fila i en `hora_inicio + i×intervalo` (evita
 * chocar con `uq_orden_estacion_dia_oe_fecha_hora` sin depender de un incremento fijo de
 * 1 minuto, como hacía ADR-127) — pero TODAS comparten `hora_termino = horaFin` (ADR-186:
 * antes cada una colapsaba `hora_termino` a su propio punto, perdiendo el fin de rango
 * capturado en cuanto se agrupaban para mostrarlas). Exportada: `PeriodoTransmisionGrid.tsx`
 * la reusa para regenerar un grupo de fecha al editar su fila colapsada.
 *
 * ADR-190 (corrige un bug real: `UNIQUE constraint failed` al guardar): con un rango
 * angosto y varios spots (p.ej. 6 spots en 1 minuto — llega a pasar tras expandir un
 * grupo por ADR-189 y luego seguir editando Hora Inicio/Hora Fin), `Math.round(intervalo
 * × i)` puede redondear VARIAS `i` al MISMO minuto — dos filas nacían con el mismo
 * `hora_inicio`, violando el unique constraint al guardar. Ahora cada punto que choca con
 * uno YA asignado en este mismo reparto se corre +1 minuto hasta encontrar uno libre
 * (mismo criterio de colisión que ya se usa en otros lados — ADR-134/188). Si eso empuja
 * algún punto más allá de `horaFin` (rango demasiado angosto para tantos spots), el fin
 * efectivo de TODAS las filas se extiende para seguir cumpliendo `hora_fin >=
 * hora_inicio` en cada una — mejor que el rango se vea un poco más ancho de lo
 * capturado, a que el guardado truene. */
export function repartirHoras(horaInicio: string, horaFin: string, spots: number): RangoHora[] {
  if (spots <= 0) return [];
  if (spots === 1) return [{ hora_inicio: horaInicio, hora_termino: horaFin }];
  const intervalo = (minutosDelDia(horaFin) - minutosDelDia(horaInicio)) / spots;
  const usados = new Set<string>();
  const puntos = Array.from({ length: spots }, (_, i) => {
    let punto = sumarMinutos(horaInicio, Math.round(intervalo * i));
    while (usados.has(punto)) {
      punto = sumarMinutos(punto, 1);
    }
    usados.add(punto);
    return punto;
  });
  const finEfectivo = puntos.reduce((max, p) => (minutosDelDia(p) > minutosDelDia(max) ? p : max), horaFin);
  return puntos.map((punto) => ({ hora_inicio: punto, hora_termino: finEfectivo }));
}

/** ADR-189 (petición del usuario, corrige un bug real): un día capturado SIN rango
 * ("+ Agregar día", Hora Inicio === Hora Fin) se queda como 1 sola fila real aunque
 * `spots_diarios` sea grande (ADR-185/186) — eso significa que, por diseño, solo puede
 * llevar 1 material. El usuario reportó que quería 2 spots con 2 materiales distintos en
 * un día así, y el tope (ligado a cuántas filas REALES existen, no a los spots
 * capturados) se lo impedía. Fix: cuando el usuario elige más materiales distintos de
 * los que hay filas, `PeriodoTransmisionGrid.tsx` expande el grupo a `grupo.spots` filas
 * — con un rango real usa `repartirHoras`, pero un PUNTO no tiene rango que repartir
 * (`repartirHoras` colapsaría todos los puntos en el mismo `hora_inicio`, chocando con
 * `uq_orden_estacion_dia_oe_fecha_hora`) — por eso esta función separa cada fila por 1
 * minuto a partir del punto capturado (mismo criterio histórico de ADR-127), SOLO para
 * darle a cada una su propio `hora_inicio` y poder llevar su propio material. */
export function dividirPuntoEnFilas(punto: string, cantidad: number): RangoHora[] {
  if (cantidad <= 0) return [];
  return Array.from({ length: cantidad }, (_, i) => {
    const p = sumarMinutos(punto, i);
    return { hora_inicio: p, hora_termino: p };
  });
}

export function CalendarioPeriodoTransmision({
  rows,
  onGenerar,
  rangoCampania,
  audios,
  disabled,
}: CalendarioPeriodoTransmisionProps) {
  const [fechasElegidas, setFechasElegidas] = useState<Date[]>([]);
  const [horaInicio, setHoraInicio] = useState("07:00");
  const [horaFin, setHoraFin] = useState("22:00");
  const [spotsPorDia, setSpotsPorDia] = useState("1");

  const spots = Number.parseInt(spotsPorDia, 10) || 0;
  // "Hora fin" antes de "Hora inicio" nunca tiene sentido (ni para 1 fila con rango
  // genuino, ni para repartir). Con 2+ spots, además, un rango de ancho 0 haría que
  // todas las filas cayeran en la MISMA hora — choca con
  // `uq_orden_estacion_dia_oe_fecha_hora` al guardar.
  const rangoInvalido =
    minutosDelDia(horaFin) < minutosDelDia(horaInicio) ||
    (spots > 1 && minutosDelDia(horaFin) === minutosDelDia(horaInicio));

  const generar = () => {
    if (rangoInvalido || spots <= 0) return;
    const fechas = fechasElegidas.map(formatoFechaLocal).sort();
    const rangos = repartirHoras(horaInicio, horaFin, spots);
    // ADR-187: cada fecha reparte sus propios materiales por posición, empezando de
    // nuevo en cada una (spot 1 de CADA fecha → material 1, etc.).
    const idsAudio = asignarPorPosicion((audios ?? []).map((a) => a.id), spots);
    // ADR-188: una fecha puede repetirse (ya tener filas) — sus horarios nuevos no deben
    // chocar con los `hora_inicio` ya ocupados de esa misma fecha (mismo criterio que
    // "+ Agregar día", ADR-134): se corren +1 minuto hasta encontrar uno libre.
    const nuevas: PeriodoTransmisionRow[] = fechas.flatMap((fecha) => {
      const ocupados = new Set(rows.filter((r) => r.fecha === fecha).map((r) => r.hora_inicio));
      return rangos.map((r, i) => {
        // Con 1 solo spot y Hora inicio === Hora fin, la fila es un PUNTO (no un rango) —
        // si se corre `hora_inicio` para no chocar, `hora_termino` debe correrse IGUAL
        // (si no, quedaría `hora_termino < hora_inicio`, violando el CHECK del modelo).
        // Con un rango real, `hora_termino` comparte `horaFin` (ADR-186) y sigue
        // quedando por delante aunque se corra `hora_inicio` un par de minutos.
        const esPunto = r.hora_inicio === r.hora_termino;
        let horaInicioFila = r.hora_inicio;
        while (ocupados.has(horaInicioFila)) {
          horaInicioFila = sumarMinutos(horaInicioFila, 1);
        }
        ocupados.add(horaInicioFila);
        return {
          fecha,
          hora_inicio: horaInicioFila,
          hora_termino: esPunto ? horaInicioFila : r.hora_termino,
          spots_diarios: 1,
          orden_estacion_audio_id: idsAudio[i],
        };
      });
    });
    if (nuevas.length === 0) return;
    onGenerar(nuevas);
    setFechasElegidas([]);
  };

  if (disabled) return null;

  return (
    <div className="form-card">
      <div className="form-card-title">Generar días desde calendario</div>
      <div className="form-card-sub">
        Elige varias fechas y captura el rango de horario y los spots una sola vez — se reparten uniformemente dentro del
        rango (editable después en la tabla de abajo, agrupado por fecha).
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
            disabled={[{ before: parseFechaLocal(rangoCampania.inicio) }, { after: parseFechaLocal(rangoCampania.fin) }]}
          />
        </div>

        <div style={{ flex: 1, minWidth: 200 }}>
          {/* ADR-184/185 (petición del usuario): "Hora inicio"/"Hora fin" van en una fila
              angosta y pegada (no el grid `.r2` de ancho completo, que los separaba
              demasiado al ocupar todo el ancho de la columna). */}
          <div style={{ display: "flex", gap: 10 }}>
            <div>
              <div className="fl fl-required">Hora inicio</div>
              <input
                className="fi"
                style={{ maxWidth: 140 }}
                type="time"
                value={horaInicio}
                onChange={(e) => setHoraInicio(e.target.value)}
              />
            </div>
            <div>
              <div className="fl fl-required">Hora fin</div>
              <input
                className="fi"
                style={{ maxWidth: 140 }}
                type="time"
                value={horaFin}
                onChange={(e) => setHoraFin(e.target.value)}
              />
            </div>
          </div>

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
          {rangoInvalido && (
            <div className="fv" style={{ fontSize: 11, marginTop: 4, color: "var(--red-text)" }}>
              "Hora fin" no puede ser anterior a "Hora inicio"
              {spots > 1 ? " (y debe ser posterior para repartir 2 o más spots)." : "."}
            </div>
          )}

          <div className="fv muted" style={{ fontSize: 11, marginTop: 8 }}>
            {fechasElegidas.length} fecha(s) seleccionada(s)
          </div>
          <button
            type="button"
            className="btn btn-sm btn-teal"
            style={{ marginTop: 8 }}
            disabled={fechasElegidas.length === 0 || rangoInvalido}
            onClick={generar}
          >
            + Generar registros
          </button>
        </div>
      </div>
    </div>
  );
}
