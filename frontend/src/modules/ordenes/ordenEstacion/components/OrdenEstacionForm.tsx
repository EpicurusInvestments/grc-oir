/** Alta de OrdenEstacion — pantalla completa (patrón form full-screen). Puede llegar ya
 * "amarrada" a una OrdenCliente (desde su detalle, botón "+ Asignar estaciones") o abrirse
 * suelta desde la lista de Órdenes internas, en cuyo caso primero hay que elegir la OC de
 * origen entre las elegibles (con Vo.Bo. o ya en estado 2; ni sin Vo.Bo. ni congeladas).
 *
 * Balance de spots en vivo + constructor de `periodo_transmision`, igual que en el
 * prototipo aprobado: nada se calcula "a mano", todo sale de `state/selectors.ts`.
 */

import { useMemo, useState } from "react";

import { MoneyInput, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { PeriodoTransmisionGrid, problemasDeFila } from "../../components/PeriodoTransmisionGrid";
import { SpotBalanceBar } from "../../components/SpotBalanceBar";
import { fmtMonto, fmtPct } from "../../format";
import { esActivo, findAfiliado, findEstacion, findPlaza, estaciones } from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { oesDeOC, oiTotalSpots, type BalanceSpotsOC } from "../../state/selectors";
import type { OrdenCliente, OrdenEstacion, OrdenEstacionInput, PeriodoTransmisionRow } from "../../types";

interface OrdenEstacionFormProps {
  /** Si viene fija (desde el detalle de una OC), aquí ya no se puede cambiar de OC. */
  ocIdFijo?: string;
  /** OE ya existente a corregir (edición). Si viene, el form arranca precargado y
   *  bloquea OC/estación — el backend real no permite reasignarlas por esta vía, solo
   *  corregir tarifa/días/observaciones (ver `FROZEN_STATES_OE` del backend). */
  oe?: OrdenEstacion;
  submitting?: boolean;
  submitError?: string | null;
  onGuardar: (ocId: string, input: OrdenEstacionInput) => void;
  onCancelar: () => void;
}

const OC_ELEGIBLE = (oc: OrdenCliente) => oc.estatus_orden === "orden_cliente_con_vobo" || oc.estatus_orden === "orden_interna";

export function OrdenEstacionForm({ ocIdFijo, oe, submitting, submitError, onGuardar, onCancelar }: OrdenEstacionFormProps) {
  const isEdit = oe != null;
  const { state } = useOrdenes();
  const [ocId, setOcId] = useState<string>(ocIdFijo ?? oe?.orden_id ?? "");
  const [estacionId, setEstacionId] = useState(oe?.estacion_id ?? "");
  const [precioSpot, setPrecioSpot] = useState(oe ? String(oe.precio_spot) : "");
  const [spotsBonificables, setSpotsBonificables] = useState(oe ? String(oe.cantidad_spots_bonificables) : "0");
  const [observaciones, setObservaciones] = useState(oe?.observaciones_estacion ?? "");
  const [periodo, setPeriodo] = useState<PeriodoTransmisionRow[]>(oe?.periodo_transmision ?? []);

  const ocsElegibles = state.ordenesCliente.filter(OC_ELEGIBLE);
  const oc = ocId ? state.ordenesCliente.find((o) => o.id === ocId) : undefined;

  const estacion = estacionId ? findEstacion(estacionId) : undefined;
  const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
  const plaza = estacion ? findPlaza(estacion.plaza_id) : undefined;

  // Al editar, la propia OE ya está en `state.ordenesEstacion` con su periodo VIEJO — sin
  // excluirla aquí, el balance en vivo la contaría dos veces (una vez como "ya asignado",
  // otra vez como `totalEstaOI` con el periodo nuevo que se está editando). Mismo criterio
  // que usa el backend real (`hermanas_ids` excluye la propia OE al validar el balance).
  const otrasOEDeLaOC = useMemo(
    () => (oc ? oesDeOC(state.ordenesEstacion, oc.id).filter((o) => o.id !== oe?.id) : []),
    [oc, state.ordenesEstacion, oe?.id],
  );
  const totalEstaOI = periodo.reduce((s, p) => s + (p.spots_diarios || 0), 0);
  // Balance "en vivo": no se puede reusar `balanceSpotsOC` tal cual porque esta OI todavía
  // no existe como `OrdenEstacion` real — se arma a mano con la misma fórmula.
  const balance: BalanceSpotsOC | null = oc
    ? (() => {
        const spotsYaAsignados = otrasOEDeLaOC.reduce((s, oe) => s + oiTotalSpots(oe), 0);
        const totalOC = oc.total_spots || 0;
        const asignados = spotsYaAsignados + totalEstaOI;
        const porAsignar = totalOC - asignados;
        return {
          totalOC,
          asignados,
          porAsignar,
          pctAsignado: totalOC > 0 ? Math.min(100, (asignados / totalOC) * 100) : 0,
          sobreAsignado: asignados > totalOC,
        };
      })()
    : null;

  const precio = Number(precioSpot) || 0;
  const bonificablesRaw = Number(spotsBonificables) || 0;
  const bonificablesExcede = bonificablesRaw > totalEstaOI;
  // ADR-068: los bonificables reducen el Importe, no los spots asignados (esos siguen
  // contando para el balance de la OC, arriba).
  const spotsFacturables = Math.max(totalEstaOI - bonificablesRaw, 0);
  const importe = spotsFacturables * precio;
  const pctOIR = oc && oc.precio_unitario > 0 ? ((oc.precio_unitario - precio) / oc.precio_unitario) * 100 : 0;

  const tarifaEstMayorQueCliente = oc != null && precio > 0 && precio > oc.precio_unitario;

  const errores: string[] = [];
  if (!oc) errores.push("Selecciona la orden del cliente de origen.");
  if (oc && !estacionId) errores.push("Selecciona una estación.");
  if (oc && (!precioSpot.trim() || precio <= 0)) errores.push("Captura una tarifa por spot mayor a 0.");
  if (tarifaEstMayorQueCliente) errores.push(`La tarifa de la estación (${fmtMonto(precio)}) no puede ser mayor que la tarifa cliente (${fmtMonto(oc!.precio_unitario)}).`);
  if (periodo.length === 0) errores.push("Captura al menos un día de transmisión.");
  periodo.forEach((p, i) => {
    const problemas = oc ? problemasDeFila(p, { inicio: oc.fecha_inicio_campania, fin: oc.fecha_fin_campania }) : [];
    if (problemas.length > 0) errores.push(`Día ${i + 1}: ${problemas[0]}`);
  });
  if (balance && balance.sobreAsignado) errores.push(`Excede el total de la OC por ${Math.abs(balance.porAsignar)} spots.`);
  if (bonificablesExcede) errores.push(`Los spots bonificables (${bonificablesRaw}) no pueden exceder los spots asignados de esta OI (${totalEstaOI}).`);

  const listo = errores.length === 0;

  const onEstacionChange = (id: string) => {
    setEstacionId(id);
  };

  const guardar = () => {
    if (!oc || !listo) return;
    const input: OrdenEstacionInput = {
      estacion_id: estacionId,
      plaza_id: estacion!.plaza_id,
      precio_spot: precio,
      cantidad_spots_bonificables: bonificablesRaw,
      periodo_transmision: periodo,
      observaciones_estacion: observaciones.trim(),
    };
    onGuardar(oc.id, input);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="cat-header">
        <div className="cat-title">{oe ? `Editar: ${oe.folio_orden_interna}` : "Nueva orden interna"}</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, display: "grid", gridTemplateColumns: "1fr 320px", gap: 24, alignContent: "start" }}>
        <div>
          <div className="form-card">
            <div className="form-card-title">Orden del cliente de origen</div>
            {ocIdFijo || isEdit ? (
              <div className="fv mono">{oc?.folio_orden}</div>
            ) : (
              <>
                <SearchableSelect
                  value={ocId}
                  onChange={setOcId}
                  options={ocsElegibles.map((o) => ({ value: o.id, label: `${o.folio_orden} — ${o.numero_orden_cliente}` }))}
                />
                {ocsElegibles.length === 0 && (
                  <div className="fv muted" style={{ fontSize: 12 }}>
                    No hay órdenes del cliente elegibles (necesitan Vo.Bo. y no estar congeladas).
                  </div>
                )}
              </>
            )}
          </div>

          {oc && (
            <>
              <div className="form-card">
                <div className="form-card-title">Datos de la orden interna</div>
                <div className="fl fl-required">Estación</div>
                <select
                  className="fsel"
                  value={estacionId}
                  disabled={isEdit}
                  onChange={(e) => onEstacionChange(e.target.value)}
                  title={isEdit ? "La estación no se puede cambiar al editar — crea una OE nueva si es otra estación." : undefined}
                >
                  <option value="">Selecciona…</option>
                  {estaciones.filter(esActivo).map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.nombre_estacion} ({e.frecuencia})
                    </option>
                  ))}
                </select>
                {estacion && (
                  <div className="heredado-block" style={{ marginTop: 4 }}>
                    <div className="heredado-title">Datos heredados de la estación</div>
                    <div className="heredado-grid">
                      <div className="heredado-row">
                        <span className="heredado-lbl">Plaza</span>
                        <span className="heredado-val">{plaza?.nombre_plaza ?? "—"}</span>
                      </div>
                      <div className="heredado-row">
                        <span className="heredado-lbl">Afiliado</span>
                        <span className="heredado-val">{afiliado?.nombre_afiliado ?? "—"}</span>
                      </div>
                    </div>
                  </div>
                )}

                <div className="r2">
                  <div>
                    <div className="fl fl-required">Tarifa por spot (MXN)</div>
                    <MoneyInput
                      style={{ maxWidth: 200 }}
                      value={precioSpot}
                      onChange={setPrecioSpot}
                    />
                    {tarifaEstMayorQueCliente && (
                      <div className="fe">La tarifa de la estación no puede ser mayor que la tarifa cliente de la OC.</div>
                    )}
                  </div>
                  <div>
                    <div className="fl">Spots bonificables del afiliado</div>
                    <input
                      className="fi"
                      style={{ maxWidth: 200, fontFamily: "var(--mono)" }}
                      inputMode="numeric"
                      value={spotsBonificables}
                      onChange={(e) => setSpotsBonificables(e.target.value.replace(/\D/g, ""))}
                    />
                    {bonificablesExcede && <div className="fe">No puede exceder los spots asignados de esta OI.</div>}
                  </div>
                </div>

                <div className="fl" style={{ marginTop: 10 }}>
                  Observaciones de la estación
                </div>
                <textarea className="ftxt" rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
              </div>

              <div className="sec">Periodo de transmisión</div>
              <PeriodoTransmisionGrid
                rows={periodo}
                onChange={setPeriodo}
                rangoCampania={{ inicio: oc.fecha_inicio_campania, fin: oc.fecha_fin_campania }}
              />
            </>
          )}
        </div>

        <div>
          {oc && (
            <>
              {balance && <SpotBalanceBar balance={balance} />}
              <div className="info-panel">
                <div className="info-panel-title">Cálculos en vivo</div>
                <div className="fl">Spots en esta OI</div>
                <div className="fv mono">{totalEstaOI}</div>
                <div className="fl">Spots bonificables del afiliado</div>
                <div className="fv mono" style={{ color: "var(--red-text)" }}>{bonificablesRaw}</div>
                <div className="fl">Spots facturables</div>
                <div className="fv mono">{spotsFacturables}</div>
                <div className="fl">Importe</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                  {fmtMonto(importe)}
                </div>
                <div className="fl">% participación OIR</div>
                <div className="fv mono">{fmtPct(pctOIR)}</div>
                <div className="fv muted" style={{ marginTop: -6, fontSize: 11 }}>
                  (tarifa cliente − tarifa estación) / tarifa cliente
                </div>
              </div>
              {errores.length > 0 && (
                <div className="info-panel" style={{ borderColor: "#F5C2C2", background: "var(--red-bg)" }}>
                  <div className="info-panel-title" style={{ color: "var(--red-text)" }}>
                    Antes de guardar
                  </div>
                  {errores.map((e) => (
                    <div key={e} className="fv" style={{ fontSize: 12, color: "var(--red-text)", marginBottom: 4 }}>
                      • {e}
                    </div>
                  ))}
                </div>
              )}
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
          <button type="button" className="btn btn-sm btn-teal" onClick={guardar} disabled={submitting || !listo} title={listo ? undefined : errores[0]}>
            {submitting ? "Guardando…" : isEdit ? "Guardar cambios" : "Guardar orden interna"}
          </button>
        </div>
      </div>
    </div>
  );
}
