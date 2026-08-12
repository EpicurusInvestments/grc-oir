/** Captura de programados (2.1 → 2.2): parrilla "por excepción" — cada día se muestra
 * como lo asignado hasta que el usuario lo edita; solo las filas que de verdad terminan
 * distintas quedan como override en `horarios_programados`. Contador de "N modificaciones"
 * y adjunto simulado del reporte del afiliado.
 */

import { useState } from "react";

import { diaDeSemana } from "../../format";
import type { OrdenEstacion, PeriodoTransmisionRow } from "../../types";

type Draft = PeriodoTransmisionRow & { editing: boolean };

function distinto(a: PeriodoTransmisionRow, b: PeriodoTransmisionRow): boolean {
  return a.hora_inicio !== b.hora_inicio || a.hora_termino !== b.hora_termino || a.spots_diarios !== b.spots_diarios;
}

interface ProgramadosFormProps {
  oe: OrdenEstacion;
  submitting?: boolean;
  submitError?: string | null;
  onAvanzar: (horariosProgramados: PeriodoTransmisionRow[], reporteRef: string | null) => void;
  onCancelar: () => void;
}

export function ProgramadosForm({ oe, submitting, submitError, onAvanzar, onCancelar }: ProgramadosFormProps) {
  const [overrides, setOverrides] = useState<Record<string, Draft>>(() => {
    const inicial: Record<string, Draft> = {};
    (oe.horarios_programados ?? []).forEach((row) => {
      inicial[row.fecha] = { ...row, editing: false };
    });
    return inicial;
  });
  const [reporteRef, setReporteRef] = useState<string | null>(oe.reporte_programados_ref ?? null);

  const abrirEdicion = (asignado: PeriodoTransmisionRow) => {
    setOverrides((prev) => ({ ...prev, [asignado.fecha]: { ...(prev[asignado.fecha] ?? asignado), editing: true } }));
  };
  const cerrarEdicion = (asignado: PeriodoTransmisionRow) => {
    setOverrides((prev) => {
      const draft = prev[asignado.fecha];
      if (!draft) return prev;
      if (!distinto(draft, asignado)) {
        const copia = { ...prev };
        delete copia[asignado.fecha];
        return copia;
      }
      return { ...prev, [asignado.fecha]: { ...draft, editing: false } };
    });
  };
  const quitarOverride = (fecha: string) => {
    setOverrides((prev) => {
      const copia = { ...prev };
      delete copia[fecha];
      return copia;
    });
  };
  const actualizarDraft = (fecha: string, patch: Partial<PeriodoTransmisionRow>) => {
    setOverrides((prev) => ({ ...prev, [fecha]: { ...prev[fecha], ...patch } }));
  };

  const nModificaciones = Object.values(overrides).filter((o) => !o.editing).length;
  const algunaEnEdicion = Object.values(overrides).some((o) => o.editing);
  const totalAsignado = oe.periodo_transmision.reduce((s, p) => s + p.spots_diarios, 0);
  const totalProgramado = oe.periodo_transmision.reduce((s, p) => {
    const ov = overrides[p.fecha];
    return s + (ov && !ov.editing ? ov.spots_diarios : p.spots_diarios);
  }, 0);

  const avanzar = () => {
    const horariosProgramados: PeriodoTransmisionRow[] = Object.values(overrides)
      .filter((o) => !o.editing)
      .map((o) => ({ fecha: o.fecha, hora_inicio: o.hora_inicio, hora_termino: o.hora_termino, spots_diarios: o.spots_diarios }));
    onAvanzar(horariosProgramados, reporteRef);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div className="cat-header">
        <div>
          <div className="cat-title">Capturar programados — {oe.folio_orden_interna}</div>
          <div className="cat-sub">
            {oe.periodo_transmision.length} días · {nModificaciones} modificado(s) · Asignados {totalAsignado} spots → Programados{" "}
            {totalProgramado}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22 }}>
        <table className="cat-table" style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th>Día</th>
              <th>Fecha</th>
              <th>Hora inicio</th>
              <th>Hora término</th>
              <th className="td-center">Spots</th>
              <th style={{ width: 140 }} />
            </tr>
          </thead>
          <tbody>
            {oe.periodo_transmision.map((asignado) => {
              const ov = overrides[asignado.fecha];
              const modificado = ov && !ov.editing;
              const fila = ov ?? asignado;
              return (
                <tr key={asignado.fecha} style={modificado ? { background: "var(--amber-bg)" } : undefined}>
                  <td className="td-2" style={{ fontSize: 11 }}>
                    {diaDeSemana(asignado.fecha)}
                  </td>
                  <td className="td-mono">{asignado.fecha}</td>
                  {ov?.editing ? (
                    <>
                      <td>
                        <input
                          type="time"
                          className="fi"
                          style={{ marginBottom: 0 }}
                          value={fila.hora_inicio}
                          onChange={(e) => actualizarDraft(asignado.fecha, { hora_inicio: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="time"
                          className="fi"
                          style={{ marginBottom: 0 }}
                          value={fila.hora_termino}
                          onChange={(e) => actualizarDraft(asignado.fecha, { hora_termino: e.target.value })}
                        />
                      </td>
                      <td className="td-center">
                        <input
                          type="number"
                          className="fi"
                          style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                          value={fila.spots_diarios}
                          onChange={(e) => actualizarDraft(asignado.fecha, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
                        />
                      </td>
                      <td>
                        <button type="button" className="btn btn-xs btn-teal" onClick={() => cerrarEdicion(asignado)}>
                          ✓ OK
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="td-mono">{fila.hora_inicio}</td>
                      <td className="td-mono">{fila.hora_termino}</td>
                      <td className="td-center td-mono">{fila.spots_diarios}</td>
                      <td>
                        <div style={{ display: "flex", gap: 4 }}>
                          <button type="button" className="btn btn-xs" onClick={() => abrirEdicion(asignado)}>
                            Editar
                          </button>
                          {modificado && (
                            <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarOverride(asignado.fecha)}>
                              ✕
                            </button>
                          )}
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="fv muted" style={{ fontSize: 12, marginTop: 10 }}>
          {nModificaciones === 0
            ? "Sin modificaciones — lo programado coincide con lo asignado."
            : `${nModificaciones} día(s) con modificación respecto a lo asignado.`}
        </div>

        <div className="fl" style={{ marginTop: 14 }}>
          Reporte del afiliado (simulado)
        </div>
        <input type="file" style={{ fontSize: 12 }} onChange={(e) => setReporteRef(e.target.files?.[0]?.name ?? null)} />
        {reporteRef && (
          <div className="fv mono" style={{ fontSize: 12, marginTop: 4 }}>
            📎 {reporteRef}
          </div>
        )}
      </div>

      <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {submitError && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {submitError}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={onCancelar} disabled={submitting}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-sm btn-teal"
            onClick={avanzar}
            disabled={submitting || algunaEnEdicion}
            title={algunaEnEdicion ? "Cierra las filas que estás editando antes de avanzar." : undefined}
          >
            Avanzar a 2.2 →
          </button>
        </div>
      </div>
    </div>
  );
}
