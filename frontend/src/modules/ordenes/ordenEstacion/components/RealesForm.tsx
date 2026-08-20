/** Captura de reales (2.2 → 2.3): misma parrilla "por excepción" que Programados, pero
 * comparando contra lo PROGRAMADO EFECTIVO (el override de `horarios_programados` si lo
 * hay, si no lo asignado). Al avanzar se genera una incidencia por cada día con diferencia
 * de spots — la vista previa de "esto se va a generar" ya se calcula aquí mismo.
 */

import { useState } from "react";

import { SavingOverlay } from "@/shared/ui";

import { diaDeSemana, fmtMonto } from "../../format";
import { programadoEfectivo } from "../../state/selectors";
import type { OrdenEstacion, PeriodoTransmisionRow } from "../../types";

type Draft = PeriodoTransmisionRow & { editing: boolean };

function distinto(a: PeriodoTransmisionRow, b: PeriodoTransmisionRow): boolean {
  return a.hora_inicio !== b.hora_inicio || a.hora_termino !== b.hora_termino || a.spots_diarios !== b.spots_diarios;
}

interface RealesFormProps {
  oe: OrdenEstacion;
  submitting?: boolean;
  submitError?: string | null;
  onAvanzar: (
    horariosReales: PeriodoTransmisionRow[],
    extra: { testigosUrl: string | null; testigosUbicacionAlterna: string | null; notasTransmision: string | null; reporteRef: string | null },
  ) => void;
  onCancelar: () => void;
}

export function RealesForm({ oe, submitting, submitError, onAvanzar, onCancelar }: RealesFormProps) {
  const [overrides, setOverrides] = useState<Record<string, Draft>>(() => {
    const inicial: Record<string, Draft> = {};
    (oe.horarios_reales ?? []).forEach((row) => {
      inicial[row.fecha] = { ...row, editing: false };
    });
    return inicial;
  });
  const [testigosUrl, setTestigosUrl] = useState(oe.testigos_url ?? "");
  const [testigosAlt, setTestigosAlt] = useState(oe.testigos_ubicacion_alterna ?? "");
  const [notas, setNotas] = useState(oe.notas_transmision ?? "");
  const [reporteRef, setReporteRef] = useState<string | null>(oe.reporte_reales_ref ?? null);

  const abrirEdicion = (programado: PeriodoTransmisionRow) => {
    setOverrides((prev) => ({ ...prev, [programado.fecha]: { ...(prev[programado.fecha] ?? programado), editing: true } }));
  };
  const cerrarEdicion = (programado: PeriodoTransmisionRow) => {
    setOverrides((prev) => {
      const draft = prev[programado.fecha];
      if (!draft) return prev;
      if (!distinto(draft, programado)) {
        const copia = { ...prev };
        delete copia[programado.fecha];
        return copia;
      }
      return { ...prev, [programado.fecha]: { ...draft, editing: false } };
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

  const algunaEnEdicion = Object.values(overrides).some((o) => o.editing);

  let totalProgramado = 0;
  let totalReal = 0;
  let nModif = 0;
  let nBonif = 0;
  let nDesc = 0;
  let montoNeto = 0;
  oe.periodo_transmision.forEach((row) => {
    const programado = programadoEfectivo(oe, row);
    const ov = overrides[row.fecha];
    totalProgramado += programado.spots_diarios;
    const real = ov && !ov.editing ? ov : programado;
    totalReal += real.spots_diarios;
    if (ov && !ov.editing && distinto(programado, ov)) {
      nModif++;
      const diff = ov.spots_diarios - programado.spots_diarios;
      if (diff > 0) nBonif++;
      else if (diff < 0) nDesc++;
      montoNeto += diff * (oe.precio_spot || 0);
    }
  });

  const avanzar = () => {
    const horariosReales: PeriodoTransmisionRow[] = Object.values(overrides)
      .filter((o) => !o.editing)
      .map((o) => ({ fecha: o.fecha, hora_inicio: o.hora_inicio, hora_termino: o.hora_termino, spots_diarios: o.spots_diarios }));
    onAvanzar(horariosReales, {
      testigosUrl: testigosUrl.trim() || null,
      testigosUbicacionAlterna: testigosAlt.trim() || null,
      notasTransmision: notas.trim() || null,
      reporteRef,
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="cat-header">
        <div>
          <div className="cat-title">Capturar reales — {oe.folio_orden_interna}</div>
          <div className="cat-sub">
            {oe.periodo_transmision.length} días · {nModif} modificado(s) · Programados {totalProgramado} spots → Reales {totalReal}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, display: "grid", gridTemplateColumns: "1fr 300px", gap: 24, alignContent: "start" }}>
        <div>
          <table className="cat-table" style={{ fontSize: 12 }}>
            <thead>
              <tr>
                <th>Día</th>
                <th>Fecha</th>
                <th>Hora inicio</th>
                <th>Hora término</th>
                <th className="td-center">Spots</th>
                <th className="td-center">Resultado</th>
                <th style={{ width: 140 }} />
              </tr>
            </thead>
            <tbody>
              {oe.periodo_transmision.map((row) => {
                const programado = programadoEfectivo(oe, row);
                const ov = overrides[row.fecha];
                const modificado = ov && !ov.editing && distinto(programado, ov);
                const fila = ov ?? programado;
                const diff = modificado ? fila.spots_diarios - programado.spots_diarios : 0;

                return (
                  <tr key={row.fecha} style={modificado ? { background: "var(--amber-bg)" } : undefined}>
                    <td className="td-2" style={{ fontSize: 11 }}>
                      {diaDeSemana(row.fecha)}
                    </td>
                    <td className="td-mono">{row.fecha}</td>
                    {ov?.editing ? (
                      <>
                        <td>
                          <input
                            type="time"
                            className="fi"
                            style={{ marginBottom: 0 }}
                            value={fila.hora_inicio}
                            onChange={(e) => actualizarDraft(row.fecha, { hora_inicio: e.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            type="time"
                            className="fi"
                            style={{ marginBottom: 0 }}
                            value={fila.hora_termino}
                            onChange={(e) => actualizarDraft(row.fecha, { hora_termino: e.target.value })}
                          />
                        </td>
                        <td className="td-center">
                          <input
                            type="number"
                            className="fi"
                            style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                            value={fila.spots_diarios}
                            onChange={(e) => actualizarDraft(row.fecha, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
                          />
                        </td>
                        <td className="td-center">—</td>
                        <td>
                          <button type="button" className="btn btn-xs btn-teal" onClick={() => cerrarEdicion(programado)}>
                            ✓ OK
                          </button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="td-mono">{fila.hora_inicio}</td>
                        <td className="td-mono">{fila.hora_termino}</td>
                        <td className="td-center td-mono">{fila.spots_diarios}</td>
                        <td className="td-center">
                          {!modificado ? (
                            <span style={{ fontSize: 11, color: "var(--green-text)" }}>sin cambio</span>
                          ) : diff > 0 ? (
                            <span className="badge b-teal">+{diff} bonif.</span>
                          ) : diff < 0 ? (
                            <span className="badge b-red">{diff} desc.</span>
                          ) : (
                            <span className="badge b-amber">cambio horario</span>
                          )}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 4 }}>
                            <button type="button" className="btn btn-xs" onClick={() => abrirEdicion(programado)}>
                              Editar
                            </button>
                            {modificado && (
                              <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarOverride(row.fecha)}>
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

          <div className="sec">Testigos y notas</div>
          <div className="r2">
            <div>
              <div className="fl">URL de testigos</div>
              <input className="fi" type="url" placeholder="https://…" value={testigosUrl} onChange={(e) => setTestigosUrl(e.target.value)} />
            </div>
            <div>
              <div className="fl">Ubicación alterna</div>
              <input className="fi" value={testigosAlt} onChange={(e) => setTestigosAlt(e.target.value)} />
            </div>
          </div>
          <div className="fl">Notas de transmisión</div>
          <textarea className="ftxt" rows={2} value={notas} onChange={(e) => setNotas(e.target.value)} />

          <div className="fl" style={{ marginTop: 10 }}>
            Reporte del afiliado (simulado)
          </div>
          <input type="file" style={{ fontSize: 12 }} onChange={(e) => setReporteRef(e.target.files?.[0]?.name ?? null)} />
          {reporteRef && (
            <div className="fv mono" style={{ fontSize: 12, marginTop: 4 }}>
              📎 {reporteRef}
            </div>
          )}
        </div>

        <div className="info-panel">
          <div className="info-panel-title">Al avanzar a 2.3 se generarán</div>
          {nBonif + nDesc === 0 ? (
            <div className="fv muted" style={{ fontSize: 12 }}>
              Ninguna incidencia — lo real coincide con lo programado.
            </div>
          ) : (
            <>
              {nBonif > 0 && (
                <div className="fv" style={{ fontSize: 12 }}>
                  • {nBonif} bonificación(es)
                </div>
              )}
              {nDesc > 0 && (
                <div className="fv" style={{ fontSize: 12 }}>
                  • {nDesc} descuento(s)
                </div>
              )}
              <div className="fl" style={{ marginTop: 6 }}>
                Impacto neto
              </div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600, color: montoNeto >= 0 ? "var(--green-text)" : "var(--red-text)" }}>
                {montoNeto >= 0 ? "+" : ""}
                {fmtMonto(montoNeto)}
              </div>
            </>
          )}
        </div>
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
            Avanzar a 2.3 →
          </button>
        </div>
      </div>
    </div>
  );
}
