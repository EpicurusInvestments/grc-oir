/** Captura de reales (2.2 → 2.3): misma parrilla "por excepción" que Programados, pero
 * comparando contra lo PROGRAMADO EFECTIVO (el override de `horarios_programados` si lo
 * hay, si no lo asignado). Al avanzar se genera una incidencia por cada día con diferencia
 * de spots — la vista previa de "esto se va a generar" ya se calcula aquí mismo.
 *
 * ADR-108 (mismo criterio que `PeriodoTransmisionGrid.tsx`, petición del usuario):
 * "Hora inicio"/"Hora término" dejan de ser 2 columnas Y 2 valores separados — una sola
 * columna "Horario de transmisión" con UN solo `<input type="time">`; `hora_inicio`/
 * `hora_termino` (columnas del modelo, sin cambio de esquema) se capturan siempre con el
 * MISMO valor.
 *
 * ADR-127 (corrige un bug real): el diccionario de overrides se indexa por
 * `orden_estacion_dia_id`, NO por `fecha` — una OE puede tener 2+ filas de
 * `periodo_transmision` con la MISMA fecha (varios spots/horarios el mismo día, ya
 * permitido por el modelo); indexar por fecha hacía que editar/quitar una fila afectara
 * a TODAS las que compartían fecha. `RealesForm` solo se abre sobre una OE ya guardada,
 * así que todo `row` siempre trae su `orden_estacion_dia_id` real.
 */

import { useEffect, useRef, useState } from "react";

import { SavingOverlay } from "@/shared/ui";

import {
  eliminarLayoutRealOrdenEstacionApi,
  listarEvidenciasOrdenEstacionApi,
  listarFormatosRealesClienteOrdenEstacionApi,
  listarFormatosRealesOrdenEstacionApi,
  listarLayoutRealesOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import {
  ordenEstacionEvidenciaFromApi,
  ordenEstacionFormatoRealClienteFromApi,
  ordenEstacionFormatoRealFromApi,
  ordenEstacionLayoutRealFromApi,
} from "../../adapters/fromApi";
import { diaDeSemana, fmtMonto } from "../../format";
import { programadoEfectivo } from "../../state/selectors";
import type {
  LayoutRealAplicado,
  LayoutRealNuevo,
  OrdenCliente,
  OrdenEstacion,
  OrdenEstacionEvidencia,
  OrdenEstacionFormatoReal,
  OrdenEstacionFormatoRealCliente,
  OrdenEstacionLayoutReal,
  PeriodoTransmisionRow,
} from "../../types";
import { CargaLayoutReales } from "./CargaLayoutReales";
import { EvidenciasTransmitido } from "./EvidenciasTransmitido";
import { FormatoHorariosReales } from "./FormatoHorariosReales";
import { FormatoRealesCliente } from "./FormatoRealesCliente";

type Draft = PeriodoTransmisionRow & { editing: boolean };
type DiaNuevoDraft = LayoutRealNuevo & { editing: boolean };

function distinto(a: PeriodoTransmisionRow, b: PeriodoTransmisionRow): boolean {
  return a.hora_inicio !== b.hora_inicio || a.hora_termino !== b.hora_termino || a.spots_diarios !== b.spots_diarios;
}

// ADR-152 (petición del usuario): antes de "Avanzar a 2.3", avisa en la MISMA tabla
// por qué un día nuevo del layout no se podrá crear — el backend valida lo mismo al
// avanzar (rango de campaña, duplicado, balance de spots), pero esperar a ese 400
// genérico no le dice al usuario CUÁL fila corregir. El balance de spots de TODA la OC
// (spots de las OE hermanas) no se valida aquí — requeriría una consulta aparte al
// backend — así que esa validación sigue dándose solo al avanzar.
function diaNuevoInvalidoMotivo(
  d: LayoutRealNuevo,
  index: number,
  oc: OrdenCliente | undefined,
  oe: OrdenEstacion,
  diasNuevos: readonly LayoutRealNuevo[],
): string | null {
  if (oc && (d.fecha < oc.fecha_inicio_campania || d.fecha > oc.fecha_fin_campania)) {
    return `Fuera del rango de campaña (${oc.fecha_inicio_campania} a ${oc.fecha_fin_campania}).`;
  }
  const yaExiste =
    oe.periodo_transmision.some((r) => r.fecha === d.fecha && r.hora_inicio === d.hora) ||
    diasNuevos.some((d2, i2) => i2 !== index && d2.fecha === d.fecha && d2.hora === d.hora);
  if (yaExiste) {
    return "Ya existe un día con esa fecha y hora en esta orden.";
  }
  return null;
}

interface RealesFormProps {
  oe: OrdenEstacion;
  oc?: OrdenCliente;
  submitting?: boolean;
  submitError?: string | null;
  onAvanzar: (
    horariosReales: PeriodoTransmisionRow[],
    extra: { notasTransmision: string | null; diasNuevos: LayoutRealNuevo[] },
  ) => void;
  onCancelar: () => void;
}

export function RealesForm({ oe, oc, submitting, submitError, onAvanzar, onCancelar }: RealesFormProps) {
  const [overrides, setOverrides] = useState<Record<string, Draft>>(() => {
    const inicial: Record<string, Draft> = {};
    (oe.horarios_reales ?? []).forEach((row) => {
      inicial[row.orden_estacion_dia_id!] = { ...row, editing: false };
    });
    return inicial;
  });
  const [notas, setNotas] = useState(oe.notas_transmision ?? "");
  // ADR-149/ADR-151 (petición del usuario): días propuestos por el layout que NO
  // existían en esta OE — se crean de verdad solo al "Avanzar a 2.3". Igual que
  // `overrides`, cargar un layout nuevo REEMPLAZA completo esta lista. `editing` se
  // agrega aquí (no viene del backend) para poder editarlos inline igual que las
  // filas existentes, dentro de la MISMA tabla (ADR-151: ya no van en una tabla aparte).
  const [diasNuevos, setDiasNuevos] = useState<DiaNuevoDraft[]>([]);
  // ADR-151/ADR-157 (petición del usuario): mientras no se cargue ningún layout, la
  // tabla sigue el flujo de SIEMPRE (`oe.periodo_transmision`, edición manual por
  // fila). En cuanto un layout aporta algo (aplicados o nuevos), la tabla se
  // RECONSTRUYE completa a partir de lo que trajo el archivo — PERO ya no "esconde"
  // los días que no vinieron en él (ADR-151 lo hacía; ADR-157 lo corrigió): el backend
  // concilia contra lo programado y manda esos días también en `aplicados`, con
  // `spots=0` — se siguen viendo en la tabla, con su incidencia de faltante marcada.
  const [layoutCargado, setLayoutCargado] = useState(false);

  // ADR-119: "Evidencias de lo Transmitido" — requiere el `orden_estacion_id` real de
  // esta OE (siempre lo hay: `RealesForm` solo se abre sobre una OE ya guardada).
  const [evidencias, setEvidencias] = useState<OrdenEstacionEvidencia[]>([]);
  useEffect(() => {
    let cancelado = false;
    listarEvidenciasOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) setEvidencias(dtos.map(ordenEstacionEvidenciaFromApi));
    });
    return () => {
      cancelado = true;
    };
  }, [oe.id]);

  // ADR-123: "Formato de Horarios Reales" — junto a Evidencias, mismo criterio (requiere
  // el `orden_estacion_id` real de esta OE, siempre disponible aquí).
  const [formatosReales, setFormatosReales] = useState<OrdenEstacionFormatoReal[]>([]);
  useEffect(() => {
    let cancelado = false;
    listarFormatosRealesOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) setFormatosReales(dtos.map(ordenEstacionFormatoRealFromApi));
    });
    return () => {
      cancelado = true;
    };
  }, [oe.id]);

  // ADR-146: "Carga de Órdenes Reales Desde Layout" — mismo criterio que arriba.
  const [layoutReales, setLayoutReales] = useState<OrdenEstacionLayoutReal[]>([]);
  // ADR-148/ADR-150 (petición del usuario): a diferencia de Evidencias/Formato de
  // Horarios Reales/Formato Cliente (evidencia real que se conserva siempre), un
  // layout es un INSUMO de trabajo para esta sesión de captura — si el usuario sube
  // uno y la pantalla se cierra SIN "Avanzar a 2.3" (por cualquier vía: el botón
  // "Cancelar", navegar a otra sección, etc.), el archivo subido EN ESTA SESIÓN se debe
  // borrar también; uno que ya existía al abrir la pantalla (de una sesión anterior ya
  // avanzada) no se toca. `layoutRealesRef` espeja el estado más reciente para que el
  // cleanup de abajo (que corre al DESMONTAR, con un closure potencialmente viejo) lea
  // el valor real, no el de cuando se creó el efecto.
  const layoutRealesIdsInicialesRef = useRef<Set<string> | null>(null);
  const layoutRealesRef = useRef<OrdenEstacionLayoutReal[]>([]);
  useEffect(() => {
    layoutRealesRef.current = layoutReales;
  }, [layoutReales]);
  useEffect(() => {
    let cancelado = false;
    listarLayoutRealesOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) {
        const mapeados = dtos.map(ordenEstacionLayoutRealFromApi);
        setLayoutReales(mapeados);
        layoutRealesIdsInicialesRef.current = new Set(mapeados.map((l) => l.id));
      }
    });
    return () => {
      cancelado = true;
    };
  }, [oe.id]);

  // ADR-150: la limpieza de "Cancelar" vivía SOLO en el click de ese botón — si el
  // usuario salía de "Capturar Reales" de cualquier OTRA forma (navegar a otra
  // sección, por ejemplo) el layout subido en la sesión se quedaba sin borrar. Ahora
  // corre al DESMONTAR el componente, sin importar la vía de salida — salvo que
  // `avanzadoRef` esté en `true` (se puso al dar "Avanzar a 2.3"; si el intento falla,
  // `submitError` lo regresa a `false` para que si después cancelan sí se limpie).
  const avanzadoRef = useRef(false);
  useEffect(() => {
    if (submitError) avanzadoRef.current = false;
  }, [submitError]);
  useEffect(() => {
    return () => {
      if (avanzadoRef.current) return;
      const idsIniciales = layoutRealesIdsInicialesRef.current ?? new Set<string>();
      layoutRealesRef.current
        .filter((l) => !idsIniciales.has(l.id))
        .forEach((l) => {
          void eliminarLayoutRealOrdenEstacionApi(oe.id, l.id);
        });
    };
  }, [oe.id]);

  // ADR-146: "Formato de Horarios Reales Enviado al Cliente" — mismo criterio que arriba.
  const [formatosRealesCliente, setFormatosRealesCliente] = useState<OrdenEstacionFormatoRealCliente[]>([]);
  useEffect(() => {
    let cancelado = false;
    listarFormatosRealesClienteOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) setFormatosRealesCliente(dtos.map(ordenEstacionFormatoRealClienteFromApi));
    });
    return () => {
      cancelado = true;
    };
  }, [oe.id]);

  const abrirEdicion = (programado: PeriodoTransmisionRow) => {
    const diaId = programado.orden_estacion_dia_id!;
    setOverrides((prev) => ({ ...prev, [diaId]: { ...(prev[diaId] ?? programado), editing: true } }));
  };
  const cerrarEdicion = (programado: PeriodoTransmisionRow) => {
    const diaId = programado.orden_estacion_dia_id!;
    setOverrides((prev) => {
      const draft = prev[diaId];
      if (!draft) return prev;
      if (!distinto(draft, programado)) {
        const copia = { ...prev };
        delete copia[diaId];
        return copia;
      }
      return { ...prev, [diaId]: { ...draft, editing: false } };
    });
  };
  const quitarOverride = (diaId: string) => {
    setOverrides((prev) => {
      const copia = { ...prev };
      delete copia[diaId];
      return copia;
    });
  };
  const actualizarDraft = (diaId: string, patch: Partial<PeriodoTransmisionRow>) => {
    setOverrides((prev) => ({ ...prev, [diaId]: { ...prev[diaId], ...patch } }));
  };

  // ADR-147/ADR-149/ADR-151/ADR-157 (petición del usuario): cargar un layout REEMPLAZA
  // completo `overrides`/`diasNuevos` (nunca se hace merge con lo anterior) — pero
  // desde ADR-157 el backend ya manda en `aplicados` un override `spots=0` por cada
  // día programado que el archivo no tocó (conciliación completa contra lo
  // programado), así que en la práctica la tabla sigue mostrando TODOS los días: los
  // que el archivo confirmó (con su spots real), los que no mencionó (en 0, marcados
  // como faltante) y los que propone como nuevos (`diasNuevos`).
  const onLayoutAplicado = (aplicados: LayoutRealAplicado[], nuevos: LayoutRealNuevo[]) => {
    const overridesNuevos: Record<string, Draft> = {};
    aplicados.forEach((a) => {
      const programado = oe.periodo_transmision.find(
        (row) => row.orden_estacion_dia_id === a.ordenEstacionDiaId,
      );
      if (!programado) return;
      overridesNuevos[a.ordenEstacionDiaId] = { ...programado, spots_diarios: a.spots, editing: false };
    });
    setOverrides(overridesNuevos);
    setDiasNuevos(nuevos.map((n) => ({ ...n, editing: false })));
    if (aplicados.length > 0 || nuevos.length > 0) setLayoutCargado(true);
  };

  const quitarDiaNuevo = (index: number) => {
    setDiasNuevos((prev) => prev.filter((_, i) => i !== index));
  };
  const abrirEdicionNuevo = (index: number) => {
    setDiasNuevos((prev) => prev.map((d, i) => (i === index ? { ...d, editing: true } : d)));
  };
  const cerrarEdicionNuevo = (index: number) => {
    setDiasNuevos((prev) => prev.map((d, i) => (i === index ? { ...d, editing: false } : d)));
  };
  const actualizarDraftNuevo = (index: number, patch: Partial<LayoutRealNuevo>) => {
    setDiasNuevos((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };
  // ADR-151: para las filas "existentes" DENTRO de la tabla en modo layout, cerrar
  // edición nunca borra el override (a diferencia de `cerrarEdicion`, pensada para el
  // flujo normal) — en este modo la fila debe seguir reflejando lo que trajo el
  // archivo tal cual, aunque coincida por casualidad con el valor programado original.
  const cerrarEdicionEnLayout = (diaId: string) => {
    setOverrides((prev) => ({ ...prev, [diaId]: { ...prev[diaId], editing: false } }));
  };

  const algunaEnEdicion =
    Object.values(overrides).some((o) => o.editing) || diasNuevos.some((d) => d.editing);
  const hayDiasNuevosInvalidos = diasNuevos.some(
    (d, i) => diaNuevoInvalidoMotivo(d, i, oc, oe, diasNuevos) !== null,
  );

  let totalProgramado = 0;
  let totalReal = 0;
  let nModif = 0;
  let nBonif = 0;
  let nDesc = 0;
  let montoNeto = 0;
  oe.periodo_transmision.forEach((row) => {
    const programado = programadoEfectivo(oe, row);
    const ov = overrides[row.orden_estacion_dia_id!];
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
    // Marca "no borrar al desmontar" ANTES de llamar a `onAvanzar` (el padre hace el
    // `await` real y solo entonces desmonta esta pantalla) — ver el efecto de limpieza
    // de arriba (ADR-150).
    avanzadoRef.current = true;
    const horariosReales: PeriodoTransmisionRow[] = Object.values(overrides)
      .filter((o) => !o.editing)
      .map((o) => ({
        fecha: o.fecha,
        hora_inicio: o.hora_inicio,
        hora_termino: o.hora_termino,
        spots_diarios: o.spots_diarios,
        orden_estacion_dia_id: o.orden_estacion_dia_id,
      }));
    onAvanzar(horariosReales, {
      notasTransmision: notas.trim() || null,
      diasNuevos: diasNuevos.map(({ fecha, hora, spots }) => ({ fecha, hora, spots })),
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
                <th>Horario de transmisión</th>
                <th className="td-center">Spots</th>
                <th className="td-center">Resultado</th>
                <th style={{ width: 140 }} />
              </tr>
            </thead>
            <tbody>
              {!layoutCargado &&
                oe.periodo_transmision.map((row) => {
                  const diaId = row.orden_estacion_dia_id!;
                  const programado = programadoEfectivo(oe, row);
                  const ov = overrides[diaId];
                  const modificado = ov && !ov.editing && distinto(programado, ov);
                  const fila = ov ?? programado;
                  const diff = modificado ? fila.spots_diarios - programado.spots_diarios : 0;

                  return (
                    <tr key={diaId} style={modificado ? { background: "var(--amber-bg)" } : undefined}>
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
                              onChange={(e) =>
                                actualizarDraft(diaId, {
                                  hora_inicio: e.target.value,
                                  hora_termino: e.target.value,
                                })
                              }
                            />
                          </td>
                          <td className="td-center">
                            <input
                              type="number"
                              className="fi"
                              style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                              value={fila.spots_diarios}
                              onChange={(e) => actualizarDraft(diaId, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
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
                                <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarOverride(diaId)}>
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

              {/* ADR-151/ADR-157 (petición del usuario): con un layout cargado, la tabla
                  deja de mostrar `oe.periodo_transmision` tal cual — se reconstruye
                  COMPLETA a partir de lo que trajo el archivo (`overrides` = aplicados,
                  `diasNuevos` = propuestas de día nuevo). Un día que no viene en el
                  archivo YA NO desaparece (ADR-151 lo escondía; ADR-157 lo corrigió):
                  el backend lo manda en `overrides` con spots=0, así que sigue en la
                  tabla marcado como descuento/faltante, con su incidencia. */}
              {layoutCargado &&
                Object.values(overrides).map((ov) => {
                  const diaId = ov.orden_estacion_dia_id!;
                  const original = oe.periodo_transmision.find((r) => r.orden_estacion_dia_id === diaId);
                  if (!original) return null;
                  const programado = programadoEfectivo(oe, original);
                  const modificado = !ov.editing && distinto(programado, ov);
                  const diff = modificado ? ov.spots_diarios - programado.spots_diarios : 0;

                  return (
                    <tr key={diaId} style={{ background: "var(--amber-bg)" }}>
                      <td className="td-2" style={{ fontSize: 11 }}>
                        {diaDeSemana(ov.fecha)}
                      </td>
                      <td className="td-mono">{ov.fecha}</td>
                      {ov.editing ? (
                        <>
                          <td>
                            <input
                              type="time"
                              className="fi"
                              style={{ marginBottom: 0 }}
                              value={ov.hora_inicio}
                              onChange={(e) =>
                                actualizarDraft(diaId, {
                                  hora_inicio: e.target.value,
                                  hora_termino: e.target.value,
                                })
                              }
                            />
                          </td>
                          <td className="td-center">
                            <input
                              type="number"
                              className="fi"
                              style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                              value={ov.spots_diarios}
                              onChange={(e) => actualizarDraft(diaId, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
                            />
                          </td>
                          <td className="td-center">—</td>
                          <td>
                            <button type="button" className="btn btn-xs btn-teal" onClick={() => cerrarEdicionEnLayout(diaId)}>
                              ✓ OK
                            </button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="td-mono">{ov.hora_inicio}</td>
                          <td className="td-center td-mono">{ov.spots_diarios}</td>
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
                              <button type="button" className="btn btn-xs" onClick={() => abrirEdicion(ov)}>
                                Editar
                              </button>
                              <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarOverride(diaId)}>
                                ✕
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}

              {layoutCargado &&
                diasNuevos.map((d, i) => {
                  // ADR-152: avisa en esta misma fila si al avanzar el backend la
                  // rechazaría (fuera de campaña, o ya existe esa fecha+hora) — antes
                  // de que el usuario intente "Avanzar a 2.3" y solo vea un error
                  // genérico sin saber cuál renglón corregir.
                  const motivoInvalido = diaNuevoInvalidoMotivo(d, i, oc, oe, diasNuevos);
                  // La key NO debe incluir `fecha`/`hora`: son justo los campos que se
                  // editan en esta fila (ADR-153), y una key que cambia a medio tecleo
                  // remonta el <input type="date">, perdiendo el foco antes de confirmar.
                  return (
                    <tr
                      key={`nuevo-${i}`}
                      style={{ background: motivoInvalido ? "var(--red-bg)" : "var(--amber-bg)" }}
                    >
                      <td className="td-2" style={{ fontSize: 11 }}>
                        {diaDeSemana(d.fecha)}
                      </td>
                      {d.editing ? (
                        <>
                          <td>
                            <input
                              type="date"
                              className="fi"
                              style={{ marginBottom: 0 }}
                              value={d.fecha}
                              onChange={(e) => actualizarDraftNuevo(i, { fecha: e.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              type="time"
                              className="fi"
                              style={{ marginBottom: 0 }}
                              value={d.hora}
                              onChange={(e) => actualizarDraftNuevo(i, { hora: e.target.value })}
                            />
                          </td>
                          <td className="td-center">
                            <input
                              type="number"
                              className="fi"
                              style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                              value={d.spots}
                              onChange={(e) =>
                                actualizarDraftNuevo(i, { spots: Number.parseInt(e.target.value, 10) || 0 })
                              }
                            />
                          </td>
                          <td className="td-center">—</td>
                          <td>
                            <button type="button" className="btn btn-xs btn-teal" onClick={() => cerrarEdicionNuevo(i)}>
                              ✓ OK
                            </button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="td-mono">{d.fecha}</td>
                          <td className="td-mono">{d.hora}</td>
                          <td className="td-center td-mono">{d.spots}</td>
                          <td className="td-center">
                            <span className="badge b-purple">Nuevo</span>
                            {motivoInvalido && (
                              <div style={{ color: "var(--red-text)", fontSize: 10, marginTop: 3 }}>
                                ⚠ {motivoInvalido}
                              </div>
                            )}
                          </td>
                          <td>
                            <div style={{ display: "flex", gap: 4 }}>
                              <button type="button" className="btn btn-xs" onClick={() => abrirEdicionNuevo(i)}>
                                Editar
                              </button>
                              <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarDiaNuevo(i)}>
                                ✕
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
            </tbody>
          </table>

          <div className="sec">Evidencias y notas</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <EvidenciasTransmitido
              ordenEstacionId={oe.id}
              evidencias={evidencias}
              onEvidenciasChange={setEvidencias}
            />
            <FormatoHorariosReales
              ordenEstacionId={oe.id}
              formatos={formatosReales}
              onFormatosChange={setFormatosReales}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            <CargaLayoutReales
              ordenEstacionId={oe.id}
              layouts={layoutReales}
              onLayoutsChange={setLayoutReales}
              onAplicado={onLayoutAplicado}
            />
            <FormatoRealesCliente
              ordenEstacionId={oe.id}
              formatos={formatosRealesCliente}
              onFormatosChange={setFormatosRealesCliente}
            />
          </div>
          <div className="fl" style={{ marginTop: 10 }}>
            Notas de transmisión
          </div>
          <textarea className="ftxt" rows={2} value={notas} onChange={(e) => setNotas(e.target.value)} />
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
            disabled={submitting || algunaEnEdicion || hayDiasNuevosInvalidos}
            title={
              algunaEnEdicion
                ? "Cierra las filas que estás editando antes de avanzar."
                : hayDiasNuevosInvalidos
                  ? "Corrige o quita los días nuevos marcados en rojo antes de avanzar."
                  : undefined
            }
          >
            Avanzar a 2.3 →
          </button>
        </div>
      </div>
    </div>
  );
}
