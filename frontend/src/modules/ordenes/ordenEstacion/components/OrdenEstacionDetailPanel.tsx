/** Panel de detalle de OrdenEstacion: datos heredados de la OC, estación/plaza/afiliado,
 * tabla de `periodo_transmision`, desglose económico completo (OIR/emisora) y comparación
 * de `precio_spot` contra la tarifa de referencia vigente.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import { previsualizarPdfOrdenEstacion, type TipoPdfOrdenEstacion } from "../../adapters/pdfsApi";
import { EstadoOIBadge } from "../../components/EstadoBadge";
import { IVA_RATE } from "../../constants";
import { diaDeSemana, fmtMonto, fmtPct, oGuion } from "../../format";
import { findAfiliado, findEstacion, findPlaza, tarifaReferencia } from "../../state/catalogosCache";
import { oiImporte, oiTotalSpots } from "../../state/selectors";
import type { Incidencia, OrdenCliente, OrdenEstacion } from "../../types";

interface OrdenEstacionDetailPanelProps {
  oe: OrdenEstacion;
  oc: OrdenCliente | undefined;
  incidencias: Incidencia[];
  onVerOC: () => void;
  onCapturarProgramados: () => void;
  onCapturarReales: () => void;
  onVerVerificacion: () => void;
}

export function OrdenEstacionDetailPanel({
  oe,
  oc,
  incidencias,
  onVerOC,
  onCapturarProgramados,
  onCapturarReales,
  onVerVerificacion,
}: OrdenEstacionDetailPanelProps) {
  const estacion = findEstacion(oe.estacion_id);
  const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
  const plaza = findPlaza(oe.plaza_id);

  const totalSpots = oiTotalSpots(oe);
  const importe = oiImporte(oe);
  const importeOIR = (importe * (oe.porcentaje_participacion_oir || 0)) / 100;
  const ivaOIR = importeOIR * IVA_RATE;
  const totalOIR = importeOIR + ivaOIR;
  const importeEmisora = importe - importeOIR;
  const ivaEmisora = importeEmisora * IVA_RATE;
  const totalEmisora = importeEmisora + ivaEmisora;

  const tarRef = estacion ? tarifaReferencia(oe.plaza_id, estacion.tipo_senal, oc?.duracion_spot ?? "30s") : undefined;
  const tarifaRefNeta = tarRef ? tarRef.tarifa_bruta * (1 - tarRef.descuento_pct / 100) : null;
  const desvioPct = tarifaRefNeta && tarifaRefNeta > 0 ? (oe.precio_spot / tarifaRefNeta - 1) * 100 : null;

  const incidenciasDeLaOE = incidencias.filter((i) => i.orden_interna_id === oe.id);

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{oe.folio_orden_interna}</div>
            <div className="dh-sub">
              <EstadoOIBadge estatus={oe.estatus} />
              {estacion && <span className="badge b-blue">{estacion.nombre_estacion}</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="db">
        <div className="sec">Datos heredados de la orden del cliente</div>
        {oc ? (
          <div className="rel-item" onClick={onVerOC} style={{ cursor: "pointer" }}>
            <div>
              <div className="rel-name">{oc.folio_orden}</div>
              <div className="rel-sub">{oc.producto}</div>
            </div>
            <span className="fv link">Ver OC →</span>
          </div>
        ) : (
          <div className="fv muted">La orden del cliente ya no existe.</div>
        )}

        <div className="sec">Estación / plaza / afiliado</div>
        <div className="r2">
          <div>
            <div className="fl">Estación</div>
            <div className="fv">
              {estacion?.nombre_estacion ?? "—"} <span className="muted">({estacion?.frecuencia})</span>
            </div>
          </div>
          <div>
            <div className="fl">Plaza</div>
            <div className="fv">{plaza?.nombre_plaza ?? "—"}</div>
          </div>
        </div>
        <div className="fl">Afiliado</div>
        <div className="fv">{afiliado?.nombre_afiliado ?? "—"}</div>

        <div className="sec">Periodo de transmisión</div>
        <table className="cat-table" style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th>Día</th>
              <th>Fecha</th>
              <th>Horario</th>
              <th className="td-center">Spots</th>
            </tr>
          </thead>
          <tbody>
            {oe.periodo_transmision.map((p, i) => (
              <tr key={i}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(p.fecha)}
                </td>
                <td className="td-mono">{p.fecha}</td>
                <td className="td-mono">
                  {p.hora_inicio}–{p.hora_termino}
                </td>
                <td className="td-center td-mono">{p.spots_diarios}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3} style={{ textAlign: "right", fontWeight: 600, fontSize: 11, padding: "8px 16px" }}>
                Total
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {totalSpots}
              </td>
            </tr>
          </tfoot>
        </table>

        <div className="sec">Desglose económico</div>
        <div className="r2">
          <div>
            <div className="fl">Tarifa por spot</div>
            <div className="fv mono">{fmtMonto(oe.precio_spot)}</div>
          </div>
          <div>
            <div className="fl">% participación OIR</div>
            <div className="fv mono">{fmtPct(oe.porcentaje_participacion_oir)}</div>
          </div>
        </div>
        <div className="fl">Importe (spots × tarifa)</div>
        <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
          {fmtMonto(importe)}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 11 }}>
          <div style={{ background: "var(--purple-bg)", borderRadius: "var(--r)", padding: "9px 11px" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--purple-text)", textTransform: "uppercase", marginBottom: 6 }}>
              OIR (margen)
            </div>
            <Linea label="Importe" valor={importeOIR} />
            <Linea label="IVA" valor={ivaOIR} />
            <Linea label="Total" valor={totalOIR} fuerte />
          </div>
          <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "9px 11px" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text2)", textTransform: "uppercase", marginBottom: 6 }}>Afiliado</div>
            <Linea label="Importe" valor={importeEmisora} />
            <Linea label="IVA" valor={ivaEmisora} />
            <Linea label="Total" valor={totalEmisora} fuerte />
          </div>
        </div>

        {tarifaRefNeta != null && desvioPct != null && (
          <div className="fv muted" style={{ fontSize: 11, marginTop: -6 }}>
            Tarifa de referencia (catálogo, {estacion?.tipo_senal.toUpperCase()}): {fmtMonto(tarifaRefNeta)} ·{" "}
            <span style={{ color: desvioPct >= 0 ? "var(--green-text)" : "var(--red-text)", fontWeight: 600 }}>
              {desvioPct >= 0 ? "+" : ""}
              {desvioPct.toFixed(1)}% vs. catálogo
            </span>
          </div>
        )}

        {oe.observaciones_estacion && (
          <>
            <div className="sec">Observaciones</div>
            <div className="fv muted">{oGuion(oe.observaciones_estacion)}</div>
          </>
        )}

        {incidenciasDeLaOE.length > 0 && (
          <>
            <div className="sec">Incidencias</div>
            {incidenciasDeLaOE.map((i) => (
              <div key={i.id} className="fv" style={{ fontSize: 12, marginBottom: 8 }}>
                <span className={`badge ${i.tipo === "bonificacion" ? "b-teal" : "b-red"}`}>{i.tipo}</span>{" "}
                <span style={{ color: "var(--text2)" }}>
                  {i.fecha_transmision} · {i.spots_asignados} → {i.spots_reales} spots · {fmtMonto(i.monto_ajuste)}
                </span>
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                  {i.nota_excepcion}
                </div>
              </div>
            ))}
          </>
        )}

      </div>

      <div className="df" style={{ flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, marginRight: "auto", flexWrap: "wrap" }}>
          <BotonPdf oe={oe} tipo="servicio" etiqueta="PDF #1 · Orden de servicio" />
          {oe.estatus !== "asignada_afiliado" && (
            <BotonPdf oe={oe} tipo="programados" etiqueta="PDF #2 · Programados" />
          )}
          {oe.estatus === "reales_conciliados" && <BotonPdf oe={oe} tipo="reales" etiqueta="PDF #3 · Reales" />}
        </div>
        {oe.estatus === "asignada_afiliado" && (
          <button type="button" className="btn btn-sm btn-teal" onClick={onCapturarProgramados}>
            → Capturar programados (2.2)
          </button>
        )}
        {oe.estatus === "programados_conciliados" && (
          <button type="button" className="btn btn-sm btn-teal" onClick={onCapturarReales}>
            → Capturar reales (2.3)
          </button>
        )}
        {oe.estatus === "reales_conciliados" && (
          <button type="button" className="btn btn-sm" onClick={onVerVerificacion}>
            Ver verificación →
          </button>
        )}
      </div>
    </>
  );
}

/** Botón que abre el visor del PDF (pestaña nueva, PDF incrustado + barra de
 * imprimir/guardar) — generado al vuelo por el backend con los datos más recientes,
 * no es un archivo guardado. */
function BotonPdf({ oe, tipo, etiqueta }: { oe: OrdenEstacion; tipo: TipoPdfOrdenEstacion; etiqueta: string }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <div>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => {
          setError(null);
          previsualizarPdfOrdenEstacion(oe.id, tipo, oe.folio_orden_interna).catch((e) =>
            setError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el PDF."),
          );
        }}
      >
        📄 {etiqueta}
      </button>
      {error && <div className="fe">{error}</div>}
    </div>
  );
}

function Linea({ label, valor, fuerte }: { label: string; valor: number; fuerte?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
      <span style={{ color: "var(--text2)" }}>{label}</span>
      <span style={{ fontFamily: "var(--mono)", fontWeight: fuerte ? 600 : 400, fontSize: fuerte ? 14 : 12 }}>{fmtMonto(valor)}</span>
    </div>
  );
}
