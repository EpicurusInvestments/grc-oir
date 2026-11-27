/** F4-03 — Dashboard de cobranza. "Al corte" de hoy: 4 KPI, aging de cuentas por
 * cobrar (barras horizontales + resumen Vigente/En riesgo/Crítico), cobranza por
 * anunciante (tabla) y cobrado vs. facturado por mes (barras duales) — mismo layout
 * del mockup aprobado. Montos CON IVA (a diferencia del Estado de resultados).
 */

import { useState } from "react";

import { fmtMonedaCorta, fmtPeriodoCorto, fmtPorcentaje } from "../format";
import { useDashboardCobranza, useExportarDashboardCobranza } from "../hooks";
import type { AgingBucket, FormatoExportacion } from "../types";

function n(v: string | null): number {
  return v == null ? 0 : Number(v);
}

const ETIQUETA_BUCKET: Record<AgingBucket, string> = {
  corriente: "Corriente (no vencida)",
  "1-30": "1-30 días",
  "31-60": "31-60 días",
  "61-90": "61-90 días",
  "90+": "90+ días",
};

/** Degradado verde → rojo por cubeta de antigüedad (pedido explícito del usuario,
 * con captura): más clara/fría cuanto menos vencida, más cálida/oscura cuanto más. */
const COLOR_BUCKET: Record<AgingBucket, string> = {
  corriente: "var(--green-text)",
  "1-30": "#6b9c2e",
  "31-60": "var(--amber)",
  "61-90": "#c9a227",
  "90+": "var(--red-text)",
};

interface KpiProps {
  etiqueta: string;
  valor: string;
  malo?: boolean;
  nota?: string;
}

function Kpi({ etiqueta, valor, malo, nota }: KpiProps) {
  return (
    <div className="kpi-box">
      <div className="kpi-lbl">{etiqueta}</div>
      <div className={`kpi-val ${malo ? "bad" : ""}`}>{valor}</div>
      {nota && <div className="kpi-sub">{nota}</div>}
    </div>
  );
}

export function DashboardCobranzaPage() {
  const { data, isLoading, isError } = useDashboardCobranza();
  const exportar = useExportarDashboardCobranza();
  const [formato, setFormato] = useState<FormatoExportacion>("xlsx");

  const totalPorCobrar = data ? n(data.total_por_cobrar) : 0;
  const vigente = data
    ? n(data.aging.find((a) => a.bucket === "corriente")?.importe ?? "0") +
      n(data.aging.find((a) => a.bucket === "1-30")?.importe ?? "0") +
      n(data.aging.find((a) => a.bucket === "31-60")?.importe ?? "0")
    : 0;
  const enRiesgo = data ? n(data.aging.find((a) => a.bucket === "61-90")?.importe ?? "0") : 0;
  const critico = data ? n(data.aging.find((a) => a.bucket === "90+")?.importe ?? "0") : 0;

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Dashboard de cobranza</div>
          <div className="cat-sub">
            Aging de cuentas por cobrar, comportamiento por cliente, tendencias de cobranza.
            Montos con IVA (dinero real a recibir).
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {data && <span className="badge b-gray">Al {data.fecha_corte}</span>}
          <select
            className="fi"
            value={formato}
            onChange={(e) => setFormato(e.target.value as FormatoExportacion)}
            aria-label="Formato de exportación"
          >
            <option value="xlsx">Excel (.xlsx)</option>
            <option value="csv">CSV</option>
          </select>
          <button
            type="button"
            className="btn btn-sm"
            disabled={exportar.isPending}
            onClick={() => exportar.mutate({ ventanaDsoDias: 90, formato })}
          >
            Exportar
          </button>
        </div>
      </div>

      {isLoading && <div className="state-msg">Cargando…</div>}
      {isError && <div className="state-msg">No se pudo cargar el dashboard de cobranza.</div>}

      {data && (
        <>
          <div className="kpi-strip">
            <Kpi
              etiqueta="Total por cobrar"
              valor={fmtMonedaCorta(data.total_por_cobrar)}
              nota={`${data.total_facturas} facturas`}
            />
            <Kpi
              etiqueta="Vencido"
              valor={fmtMonedaCorta(data.total_vencido)}
              malo={n(data.total_vencido) > 0}
              nota={
                totalPorCobrar > 0
                  ? `${fmtPorcentaje(String((n(data.total_vencido) / totalPorCobrar) * 100))} del total`
                  : undefined
              }
            />
            <Kpi
              etiqueta="DSO promedio"
              valor={data.dso_promedio != null ? `${data.dso_promedio}d` : "—"}
              nota={`ventana de ${data.ventana_dso_dias} días`}
            />
            <Kpi etiqueta="Cobrado mes" valor={fmtMonedaCorta(data.cobrado_mes)} nota={data.mes_cobrado} />
          </div>

          <div className="grid2" style={{ margin: "14px 22px" }}>
            <div className="panel">
              <div className="panel-title">
                Aging de cuentas por cobrar <span className="card-title-sub">distribución por antigüedad</span>
              </div>
              {data.aging.map((a) => (
                <div className="hbar-row" key={a.bucket}>
                  <div className="hbar-lbl">
                    {ETIQUETA_BUCKET[a.bucket]}
                    <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 400 }}>
                      {a.count} facturas
                    </div>
                  </div>
                  <div className="hbar-bg">
                    <div
                      className="hbar-fill"
                      style={{
                        width: `${totalPorCobrar > 0 ? Math.min((n(a.importe) / totalPorCobrar) * 100, 100) : 0}%`,
                        background: COLOR_BUCKET[a.bucket],
                      }}
                    />
                  </div>
                  <div className="hbar-val">
                    {fmtMonedaCorta(a.importe)}{" "}
                    <span style={{ color: "var(--text3)", fontSize: 11, fontWeight: 400 }}>
                      {totalPorCobrar > 0 ? fmtPorcentaje(String((n(a.importe) / totalPorCobrar) * 100)) : "—"}
                    </span>
                  </div>
                </div>
              ))}

              <div
                style={{
                  marginTop: 14,
                  paddingTop: 14,
                  borderTop: "1px dashed var(--border)",
                  fontSize: 12,
                  color: "var(--text2)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span>Vigente (0-60d)</span>
                  <span className="td-mono" style={{ color: "var(--green-text)", fontWeight: 600 }}>
                    {fmtMonedaCorta(String(vigente))}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span>En riesgo (61-90d)</span>
                  <span className="td-mono" style={{ color: "var(--amber-text)", fontWeight: 600 }}>
                    {fmtMonedaCorta(String(enRiesgo))}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Crítico (+90d)</span>
                  <span className="td-mono" style={{ color: "var(--red-text)", fontWeight: 600 }}>
                    {fmtMonedaCorta(String(critico))}
                  </span>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-title">
                Cobranza por anunciante <span className="card-title-sub">comportamiento</span>
              </div>
              <table className="cat-table">
                <thead>
                  <tr>
                    <th>Anunciante</th>
                    <th className="td-right">Por cobrar</th>
                    <th className="td-right">Vencido</th>
                    <th className="td-center">DSO</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_anunciante.map((c) => (
                    <tr key={c.anunciante_id}>
                      <td style={{ fontWeight: 500 }}>{c.nombre}</td>
                      <td className="td-right td-mono">{fmtMonedaCorta(c.por_cobrar)}</td>
                      <td
                        className="td-right td-mono"
                        style={{ color: n(c.vencido) > 0 ? "var(--red-text)" : "var(--text3)" }}
                      >
                        {n(c.vencido) > 0 ? fmtMonedaCorta(c.vencido) : "—"}
                      </td>
                      <td className="td-center td-mono">{c.dso != null ? `${c.dso}d` : "—"}</td>
                    </tr>
                  ))}
                  {data.por_anunciante.length === 0 && (
                    <tr>
                      <td colSpan={4} className="state-msg">
                        Sin saldo por cobrar.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel" style={{ margin: "14px 22px" }}>
            <div className="panel-title">
              Cobrado vs. facturado por mes <span className="card-title-sub">ratio de cobranza</span>
            </div>
            <div className="chart-bar">
              {(() => {
                const max = Math.max(
                  1,
                  ...data.evolucion_mensual.flatMap((p) => [n(p.facturado), n(p.cobrado)]),
                );
                return data.evolucion_mensual.map((p) => (
                  <div className="chart-col" key={p.periodo}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "flex-end",
                        width: "100%",
                        height: "100%",
                        gap: 4,
                        justifyContent: "center",
                      }}
                    >
                      <div
                        style={{
                          width: "35%",
                          background: "var(--phase)",
                          height: `${Math.max((n(p.facturado) / max) * 100, 2)}%`,
                          borderRadius: "3px 3px 0 0",
                          position: "relative",
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            position: "absolute",
                            top: -14,
                            left: "50%",
                            transform: "translateX(-50%)",
                            fontFamily: "var(--mono)",
                            color: "var(--text3)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {fmtMonedaCorta(p.facturado)}
                        </span>
                      </div>
                      <div
                        style={{
                          width: "35%",
                          background: "var(--green-text)",
                          height: `${Math.max((n(p.cobrado) / max) * 100, 2)}%`,
                          borderRadius: "3px 3px 0 0",
                          position: "relative",
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            position: "absolute",
                            top: -14,
                            left: "50%",
                            transform: "translateX(-50%)",
                            fontFamily: "var(--mono)",
                            color: "var(--green-text)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {fmtMonedaCorta(p.cobrado)}
                        </span>
                      </div>
                    </div>
                    <div className="chart-col-lbl">{fmtPeriodoCorto(p.periodo)}</div>
                  </div>
                ));
              })()}
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                gap: 18,
                fontSize: 11,
                color: "var(--text3)",
                marginTop: 14,
                paddingTop: 10,
                borderTop: "1px dashed var(--border)",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--phase)" }} />
                Facturado
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--green-text)" }} />
                Cobrado
              </span>
            </div>
          </div>
        </>
      )}
    </>
  );
}
