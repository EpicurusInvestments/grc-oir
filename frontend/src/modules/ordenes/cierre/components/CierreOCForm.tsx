/** Cierre de la OrdenCliente (estado 2 → 3): resumen de lo transmitido vs. lo vendido,
 * ajuste neto por incidencias, montos de comisión (con auto-fill visible si algún % de
 * comisión seguía vacío) y carga simulada de dos documentos. Se permite cerrar sin ellos,
 * con advertencia ámbar y registro de qué faltó — nunca bloqueado por los documentos, solo
 * por la casilla de confirmación.
 *
 * La precondición (al menos una OI, todas en 2.3) la valida quien abre este formulario
 * (el botón "Cerrar orden →" del detalle de la OC solo aparece cuando ya se cumple).
 */

import { useState } from "react";

import type { CerrarOCInput } from "../../state/OrdenesContext";
import { IVA_RATE } from "../../constants";
import { fmtMonto } from "../../format";
import { findAgencia, findVendedor } from "../../state/catalogosCache";
import { ajusteIncidenciasDeOEs, totalRealDeOE, totalesOC } from "../../state/selectors";
import type { Incidencia, OrdenCliente, OrdenEstacion } from "../../types";

interface CierreOCFormProps {
  oc: OrdenCliente;
  oesDeLaOC: OrdenEstacion[];
  incidencias: Incidencia[];
  submitting?: boolean;
  submitError?: string | null;
  onConfirmar: (input: CerrarOCInput) => void;
  onCancelar: () => void;
}

export function CierreOCForm({ oc, oesDeLaOC, incidencias, submitting, submitError, onConfirmar, onCancelar }: CierreOCFormProps) {
  const [odcCerradaRef, setOdcCerradaRef] = useState<string | null>(oc.odc_cerrada_ref ?? null);
  const [cartaRef, setCartaRef] = useState<string | null>(oc.carta_conciliacion_ref ?? null);
  const [confirmado, setConfirmado] = useState(false);

  const vp = findVendedor(oc.vendedor_principal_id);
  const vs = findVendedor(oc.vendedor_secundario_id);
  const ag = findAgencia(oc.agencia_id);

  const comisionVp = oc.porcentaje_comision_vendedor_principal_snap ?? vp?.porcentaje_comision_default ?? null;
  const comisionVs = oc.vendedor_secundario_id ? (oc.porcentaje_comision_vendedor_secundario_snap ?? vs?.porcentaje_comision_default ?? null) : null;
  const comisionAg = oc.agencia_id ? (oc.porcentaje_comision_agencia_snap ?? ag?.porcentaje_comision_agencia_default ?? null) : null;

  const fixes: string[] = [];
  if (oc.porcentaje_comision_vendedor_principal_snap == null && comisionVp != null) fixes.push(`% vendedor principal → ${comisionVp}% (default del catálogo)`);
  if (oc.vendedor_secundario_id && oc.porcentaje_comision_vendedor_secundario_snap == null && comisionVs != null)
    fixes.push(`% vendedor secundario → ${comisionVs}% (default del catálogo)`);
  if (oc.agencia_id && oc.porcentaje_comision_agencia_snap == null && comisionAg != null) fixes.push(`% agencia → ${comisionAg}% (default del catálogo)`);

  const { total } = totalesOC(oc);
  const montoVp = comisionVp != null ? (total * comisionVp) / 100 : null;
  const montoVs = comisionVs != null ? (total * comisionVs) / 100 : null;
  const montoAg = comisionAg != null ? (total * comisionAg) / 100 : null;

  const totalTransmitido = oesDeLaOC.reduce((s, oe) => s + totalRealDeOE(oe), 0);
  const totalVendido = oc.total_spots;
  const ajusteIncidencias = ajusteIncidenciasDeOEs(incidencias, oesDeLaOC);

  const faltantes: ("odc_cerrada" | "carta_conciliacion")[] = [
    ...(!odcCerradaRef ? (["odc_cerrada"] as const) : []),
    ...(!cartaRef ? (["carta_conciliacion"] as const) : []),
  ];

  const confirmar = () => {
    onConfirmar({
      odcCerradaRef,
      cartaConciliacionRef: cartaRef,
      documentosFaltantes: faltantes,
      comisiones: { vp: comisionVp, vs: comisionVs, ag: comisionAg },
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div className="cat-header">
        <div className="cat-title">Cerrar orden — {oc.folio_orden}</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, maxWidth: 640 }}>
        <div className="sec">Transmitido vs. vendido</div>
        <div className="mc-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "10px 12px" }}>
            <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", fontWeight: 600 }}>Vendido</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 600 }}>{totalVendido}</div>
          </div>
          <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "10px 12px" }}>
            <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", fontWeight: 600 }}>Transmitido (real)</div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 18,
                fontWeight: 600,
                color: totalTransmitido === totalVendido ? "var(--green-text)" : "var(--amber-text)",
              }}
            >
              {totalTransmitido}
            </div>
          </div>
        </div>

        <div className="sec">Ajuste por incidencias</div>
        <div className="fv mono" style={{ fontSize: 16, fontWeight: 600, color: ajusteIncidencias >= 0 ? "var(--green-text)" : "var(--red-text)" }}>
          {ajusteIncidencias >= 0 ? "+" : ""}
          {fmtMonto(ajusteIncidencias)}
        </div>

        <div className="sec">Montos de comisión (IVA {(IVA_RATE * 100).toFixed(0)}% incluido en el total)</div>
        {fixes.length > 0 && (
          <div style={{ background: "var(--amber-bg)", color: "var(--amber-text)", borderRadius: "var(--r)", padding: "8px 11px", fontSize: 12, marginBottom: 10 }}>
            ⚠ Snapshots de comisión llenados automáticamente: {fixes.join(" · ")}
          </div>
        )}
        {montoVp != null && (
          <div className="fv" style={{ fontSize: 13 }}>
            Vendedor principal ({comisionVp}%): <span className="mono">{fmtMonto(montoVp)}</span>
          </div>
        )}
        {montoVs != null && (
          <div className="fv" style={{ fontSize: 13 }}>
            Vendedor secundario ({comisionVs}%): <span className="mono">{fmtMonto(montoVs)}</span>
          </div>
        )}
        {montoAg != null && (
          <div className="fv" style={{ fontSize: 13 }}>
            Agencia ({comisionAg}%): <span className="mono">{fmtMonto(montoAg)}</span>
          </div>
        )}

        <div className="sec">Documentos de cierre</div>
        <div className="fl">ODC cerrada del cliente (simulado)</div>
        <input type="file" style={{ fontSize: 12 }} onChange={(e) => setOdcCerradaRef(e.target.files?.[0]?.name ?? null)} />
        {odcCerradaRef && (
          <div className="fv mono" style={{ fontSize: 12, marginTop: 4, marginBottom: 10 }}>
            📎 {odcCerradaRef}
          </div>
        )}
        <div className="fl" style={{ marginTop: 8 }}>
          Carta de Conciliación firmada (simulado)
        </div>
        <input type="file" style={{ fontSize: 12 }} onChange={(e) => setCartaRef(e.target.files?.[0]?.name ?? null)} />
        {cartaRef && (
          <div className="fv mono" style={{ fontSize: 12, marginTop: 4 }}>
            📎 {cartaRef}
          </div>
        )}

        {faltantes.length > 0 && (
          <div style={{ background: "var(--amber-bg)", color: "var(--amber-text)", borderRadius: "var(--r)", padding: "8px 11px", fontSize: 12, marginTop: 12 }}>
            ⚠ Se cerrará sin {faltantes.map((f) => (f === "odc_cerrada" ? "la ODC cerrada" : "la Carta de Conciliación")).join(" ni ")}. Quedará
            registro de que faltó.
          </div>
        )}

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginTop: 16, cursor: "pointer" }}>
          <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} />
          Confirmo que la información de cierre es correcta.
        </label>
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
            className="btn btn-sm btn-amber"
            onClick={confirmar}
            disabled={submitting || !confirmado}
            title={confirmado ? undefined : "Marca la confirmación para habilitar el cierre."}
          >
            Cerrar orden → Estado 3
          </button>
        </div>
      </div>
    </div>
  );
}
