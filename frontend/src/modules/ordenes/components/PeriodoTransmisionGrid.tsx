/** Constructor/editor de `periodo_transmision`: filas de fecha + horario de transmisión
 * + spots del día, con día de la semana visible, agregar/quitar fila, y validación de que
 * la fecha cae dentro del rango de la campaña. Se reutiliza en el alta de OrdenEstacion
 * (Tanda 3) y, en modo de solo lectura, en el detalle.
 *
 * ADR-107/ADR-108 (petición del usuario): "Hora inicio"/"Hora término" dejan de ser 2
 * columnas Y 2 valores separados — una sola columna "Horario de transmisión" con UN
 * solo `<input type="time">`; `hora_inicio`/`hora_termino` (columnas del modelo, sin
 * cambio de esquema) se capturan siempre con el MISMO valor.
 *
 * ADR-103/ADR-107: columna "Material a Transmitir" — solo aparece cuando el padre pasa
 * `audios`/`onAsignarAudio` (edición, con la OE ya creada). Por default se muestra el
 * PRIMER audio subido (`audios[0]`) para cualquier día sin override propio — incluidos
 * los días recién generados por `CalendarioPeriodoTransmision.tsx`, que nacen sin
 * `orden_estacion_audio_id` (ADR-107: antes se mostraba un "—", ahora el nombre real del
 * default, para que se vea de inmediato qué material le tocó a cada fecha). Cambiar el
 * default de un día puntual ("Sustitución de Material", botón con ícono) requiere un
 * `orden_estacion_dia_id` real — antes de guardar solo se ve el nombre, sin botón.
 *
 * ADR-111: en el ALTA (antes de que exista `orden_estacion_dia_id` real), "Sustitución de
 * Material" también está disponible — el padre pasa `permiteAsignacionLocal` y el cambio
 * se guarda en la fila misma (`orden_estacion_audio_id`, sin llamar a ningún endpoint),
 * viajando con el resto del día al hacer "Guardar" (`toApi.ts` lo manda como
 * `audio_staging_ref`, resuelto por el backend contra los audios de la misma solicitud).
 *
 * ADR-104: "Cancelar transmisión" de un día puntual — solo aparece cuando el padre pasa
 * `onCancelarDia` (mismo criterio que el audio: requiere `orden_estacion_dia_id` real).
 * Captura el motivo en un campo de texto en línea (no `window.prompt`, para mantener el
 * patrón del resto de la app — p.ej. "Motivo del cambio de tarifa"). Un día ya cancelado
 * (`row.cancelada`) se muestra atenuado, de solo lectura, sin botón de quitar/cancelar.
 */

import { useState, type CSSProperties } from "react";

import { diaDeSemana } from "../format";
import type { OrdenEstacionAudio, PeriodoTransmisionRow } from "../types";

// Tamaño fijo (no solo mínimo) + centrado por flex: así los 3 íconos de acción
// (Sustitución de Material, Quitar día, Cancelar transmisión) miden EXACTO lo mismo por
// fuera, sin importar que sus glifos (🔄 ✕ 🚫) tengan anchos naturales distintos.
const ICON_BTN_STYLE: CSSProperties = {
  width: 44,
  height: 44,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 0,
};
// Los emojis a color (🔄 🚫) se dibujan más grandes que un glifo de texto (✕) al MISMO
// font-size (petición del usuario: que se vean del mismo tamaño que la X) — se
// compensa con un font-size menor solo para los emoji, no para la X.
const ICON_BTN_STYLE_EMOJI: CSSProperties = { ...ICON_BTN_STYLE, fontSize: 14 };
const ICON_BTN_STYLE_X: CSSProperties = { ...ICON_BTN_STYLE, fontSize: 20 };

export function problemasDeFila(row: PeriodoTransmisionRow, rango: { inicio: string; fin: string }): string[] {
  const problemas: string[] = [];
  if (!row.fecha) {
    problemas.push("Falta la fecha.");
  } else if (rango.inicio && rango.fin && (row.fecha < rango.inicio || row.fecha > rango.fin)) {
    problemas.push("La fecha cae fuera del rango de la campaña.");
  }
  if (!row.hora_inicio) {
    problemas.push("Falta el horario de transmisión.");
  }
  if (!row.spots_diarios || row.spots_diarios <= 0) {
    problemas.push("Los spots del día deben ser mayores a 0.");
  }
  return problemas;
}

interface PeriodoTransmisionGridProps {
  rows: PeriodoTransmisionRow[];
  onChange: (rows: PeriodoTransmisionRow[]) => void;
  rangoCampania: { inicio: string; fin: string };
  disabled?: boolean;
  /** ADR-103: lista de audios disponibles (orden 0 = default) — su sola presencia
   *  decide si se muestra la columna "Audio". */
  audios?: OrdenEstacionAudio[];
  /** Asigna (o quita, con `null`) el audio de UN día — llamada inmediata al backend
   *  (endpoint dedicado, `PUT .../dias/{id}/audio`), no se acumula con "Guardar". */
  onAsignarAudio?: (diaId: string, audioId: string | null) => void;
  /** ADR-104: cancela UN día puntual — llamada inmediata al backend (endpoint dedicado,
   *  `POST .../dias/{id}/cancelar`), no se acumula con "Guardar". Su sola presencia decide
   *  si se muestra el botón "Cancelar transmisión" (requiere la OE ya creada, igual que
   *  `onAsignarAudio`). */
  onCancelarDia?: (diaId: string, motivo: string) => void;
  /** ADR-111: habilita "Sustitución de Material" también para filas SIN
   *  `orden_estacion_dia_id` (recién generadas, antes de guardar) — el cambio se guarda
   *  localmente en la fila (`onChange`), no llama a `onAsignarAudio`. */
  permiteAsignacionLocal?: boolean;
}

export function PeriodoTransmisionGrid({
  rows,
  onChange,
  rangoCampania,
  disabled,
  audios,
  onAsignarAudio,
  onCancelarDia,
  permiteAsignacionLocal,
}: PeriodoTransmisionGridProps) {
  // ADR-108: la columna aparece con solo pasar `audios` (aunque venga vacía, p.ej. al
  // CREAR una OE nueva, antes de poder subir ningún material) — así el usuario ve la
  // columna desde el principio, en vez de que aparezca "de la nada" hasta que edita.
  // `onAsignarAudio` sigue siendo lo que habilita el botón de sustituir (aparte).
  const mostrarColumnaAudio = audios != null;
  // ADR-104: un día cancelado no cuenta para el total (libera su cupo, igual que en el
  // balance de la OC — ver `oiTotalSpots`, selectors.ts).
  const totalSpots = rows.reduce((s, r) => (r.cancelada ? s : s + (r.spots_diarios || 0)), 0);
  const [cancelandoIdx, setCancelandoIdx] = useState<number | null>(null);
  const [motivoCancelacion, setMotivoCancelacion] = useState("");
  // ADR-107: "Sustitución de Material" — reveló bajo demanda (ícono → combo), en vez de
  // un combo siempre visible.
  const [sustituyendoIdx, setSustituyendoIdx] = useState<number | null>(null);

  const confirmarCancelacion = (diaId: string) => {
    if (!motivoCancelacion.trim()) return;
    onCancelarDia?.(diaId, motivoCancelacion.trim());
    setCancelandoIdx(null);
    setMotivoCancelacion("");
  };

  /** ADR-107: nombre del material que le toca a ESTE día — el propio si tiene override,
   *  si no el default (`audios[0]`, el primero subido). `undefined` si no hay ningún
   *  audio subido todavía. */
  const nombreMaterial = (row: PeriodoTransmisionRow): string | undefined => {
    if (!audios || audios.length === 0) return undefined;
    if (row.orden_estacion_audio_id) {
      return audios.find((a) => a.id === row.orden_estacion_audio_id)?.nombre_archivo ?? audios[0].nombre_archivo;
    }
    return audios[0].nombre_archivo;
  };

  const actualizarFila = (idx: number, patch: Partial<PeriodoTransmisionRow>) => {
    onChange(rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };
  const quitarFila = (idx: number) => onChange(rows.filter((_, i) => i !== idx));
  const agregarFila = () => {
    const ultima = rows[rows.length - 1];
    let siguienteFecha = rangoCampania.inicio;
    if (ultima?.fecha) {
      const d = new Date(ultima.fecha);
      d.setDate(d.getDate() + 1);
      siguienteFecha = d.toISOString().slice(0, 10);
      if (rangoCampania.fin && siguienteFecha > rangoCampania.fin) siguienteFecha = rangoCampania.fin;
    }
    const horario = ultima?.hora_inicio ?? "07:00";
    onChange([
      ...rows,
      {
        fecha: siguienteFecha,
        hora_inicio: horario,
        hora_termino: horario,
        spots_diarios: ultima?.spots_diarios ?? 0,
      },
    ]);
  };

  return (
    <div>
      <table className="cat-table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th>Día</th>
            <th>Fecha</th>
            <th>Horario de transmisión</th>
            <th className="td-center" style={{ width: 70, minWidth: 70 }}>
              Spots
            </th>
            {mostrarColumnaAudio && <th>Material a Transmitir</th>}
            <th style={{ width: onCancelarDia ? 120 : 60, minWidth: onCancelarDia ? 120 : 60 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const problemas = row.cancelada ? [] : problemasDeFila(row, rangoCampania);
            const mostrarCancelar =
              onCancelarDia != null && row.orden_estacion_dia_id != null && !row.cancelada;
            const cancelandoEstaFila = cancelandoIdx === idx;
            return (
              <tr key={idx} style={row.cancelada ? { opacity: 0.55 } : undefined}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(row.fecha)}
                </td>
                <td>
                  <input
                    type="date"
                    className="fi"
                    style={{ marginBottom: 0, borderColor: problemas.length ? "var(--red-text)" : undefined }}
                    value={row.fecha}
                    disabled={disabled || row.cancelada}
                    onChange={(e) => actualizarFila(idx, { fecha: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="time"
                    className="fi"
                    style={{ marginBottom: 0 }}
                    value={row.hora_inicio}
                    disabled={disabled || row.cancelada}
                    onChange={(e) => actualizarFila(idx, { hora_inicio: e.target.value, hora_termino: e.target.value })}
                  />
                </td>
                <td className="td-center" style={{ width: 70, minWidth: 70 }}>
                  <input
                    type="number"
                    className="fi"
                    style={{
                      marginBottom: 0,
                      width: 56,
                      padding: "0 6px",
                      textAlign: "center",
                      fontFamily: "var(--mono)",
                    }}
                    value={row.spots_diarios}
                    disabled={disabled || row.cancelada}
                    onChange={(e) => actualizarFila(idx, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
                  />
                </td>
                {mostrarColumnaAudio && (
                  <td style={{ paddingRight: 0 }}>
                    {row.cancelada ? (
                      <span className="fv muted" style={{ fontSize: 11 }}>
                        —
                      </span>
                    ) : sustituyendoIdx === idx &&
                      (row.orden_estacion_dia_id || permiteAsignacionLocal) ? (
                      <select
                        className="fsel"
                        style={{ marginBottom: 0, fontSize: 12 }}
                        autoFocus
                        value={row.orden_estacion_audio_id ?? ""}
                        onChange={(e) => {
                          const nuevoId = e.target.value || null;
                          if (row.orden_estacion_dia_id) {
                            onAsignarAudio?.(row.orden_estacion_dia_id, nuevoId);
                          } else {
                            actualizarFila(idx, { orden_estacion_audio_id: nuevoId });
                          }
                          setSustituyendoIdx(null);
                        }}
                        onBlur={() => setSustituyendoIdx(null)}
                      >
                        <option value="">
                          Default{audios && audios.length > 0 ? ` (${audios[0].nombre_archivo})` : ""}
                        </option>
                        {audios?.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.nombre_archivo}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 12, flex: 1 }}>{nombreMaterial(row) ?? "—"}</span>
                        {(row.orden_estacion_dia_id || permiteAsignacionLocal) &&
                          audios &&
                          audios.length > 0 && (
                            <button
                              type="button"
                              className="btn"
                              style={{ ...ICON_BTN_STYLE_EMOJI, marginLeft: "auto" }}
                              title="Sustitución de Material"
                              aria-label="Sustitución de Material"
                              onClick={() => setSustituyendoIdx(idx)}
                            >
                              🔄
                            </button>
                          )}
                      </div>
                    )}
                  </td>
                )}
                <td style={{ paddingLeft: 0 }}>
                  {row.cancelada ? (
                    <span className="fv" style={{ fontSize: 11, color: "var(--red-text)", fontWeight: 600 }}>
                      Cancelado
                    </span>
                  ) : cancelandoEstaFila ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input
                        type="text"
                        className="fi"
                        style={{ marginBottom: 0, fontSize: 11, width: 140 }}
                        placeholder="Motivo de la cancelación"
                        value={motivoCancelacion}
                        autoFocus
                        onChange={(e) => setMotivoCancelacion(e.target.value)}
                      />
                      <button
                        type="button"
                        className="btn btn-xs btn-danger"
                        disabled={!motivoCancelacion.trim()}
                        onClick={() => confirmarCancelacion(row.orden_estacion_dia_id as string)}
                      >
                        Confirmar
                      </button>
                      <button
                        type="button"
                        className="btn btn-xs"
                        onClick={() => {
                          setCancelandoIdx(null);
                          setMotivoCancelacion("");
                        }}
                      >
                        Cancelar
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
                      {!disabled && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          style={ICON_BTN_STYLE_X}
                          onClick={() => quitarFila(idx)}
                          aria-label="Quitar día"
                        >
                          ✕
                        </button>
                      )}
                      {mostrarCancelar && (
                        <button
                          type="button"
                          className="btn"
                          style={ICON_BTN_STYLE_EMOJI}
                          title="Cancelar transmisión"
                          aria-label="Cancelar transmisión"
                          onClick={() => {
                            setCancelandoIdx(idx);
                            setMotivoCancelacion("");
                          }}
                        >
                          🚫
                        </button>
                      )}
                      {problemas.length > 0 && (
                        <span style={{ fontSize: 11, color: "var(--red-text)" }} title={problemas.join(" ")}>
                          ⚠
                        </span>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        {rows.length > 0 && (
          <tfoot>
            <tr>
              <td colSpan={3} style={{ textAlign: "right", fontWeight: 600, fontSize: 11, padding: "8px 16px" }}>
                Total
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {totalSpots}
              </td>
              {mostrarColumnaAudio && <td />}
              <td />
            </tr>
          </tfoot>
        )}
      </table>
      {!disabled && (
        <button type="button" className="btn btn-xs" style={{ marginTop: 8 }} onClick={agregarFila}>
          + Agregar día
        </button>
      )}
      {rows.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginTop: 8 }}>
          Captura al menos un día de transmisión.
        </div>
      )}
      {audios != null && audios.length === 0 && (
        <div className="fv muted" style={{ fontSize: 11, marginTop: 8 }}>
          El material a transmitir (audios) se sube y se asigna desde "Material a
          Transmitir" después de guardar la orden — necesita un id real.
        </div>
      )}
    </div>
  );
}
