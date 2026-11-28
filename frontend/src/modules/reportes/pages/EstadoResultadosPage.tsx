/** F4-01 — Estado de resultados (P&L), SIN IVA. Selector de mes, 4 KPI con tendencia,
 * tabla del P&L + composición de costos + indicadores clave (2 columnas), evolución de
 * utilidad neta (6 meses) y detalle histórico mensual. Layout fiel al mockup aprobado
 * `docs/referencias/pantallas/Fase_4_-_Reportes.html`.
 */

import { useState } from "react";

import {
  fmtMoneda,
  fmtMonedaCorta,
  fmtPeriodo,
  fmtPeriodoCorto,
  fmtPorcentaje,
  mesEnCursoLocal,
} from "../format";
import { useEstadoResultados, useExportarEstadoResultados } from "../hooks";
import type { EstadoResultadosPeriodo, FormatoExportacion } from "../types";

function n(v: string): number {
  return Number(v);
}

function direccionTendencia(pct: string | null): "up" | "down" | "flat" {
  if (pct == null) return "flat";
  const v = Number(pct);
  if (Number.isNaN(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}

function textoTendencia(pct: string | null): string {
  if (pct == null) return "s/d";
  const v = Number(pct);
  return Number.isNaN(v) ? "s/d" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

/** Costos directos/indirectos se muestran siempre entre paréntesis en rojo (son
 * deducciones) — los campos ya llegan como magnitud positiva del backend. */
function montoDeduccion(valor: string): string {
  return `(${fmtMoneda(valor)})`;
}

/** Utilidad bruta/neta SÍ puede ser negativa de verdad: signo con paréntesis + rojo. */
function montoConSigno(valor: string): { texto: string; clase: string } {
  const v = n(valor);
  if (v >= 0) return { texto: fmtMoneda(valor), clase: "pl-pos" };
  return { texto: `(${fmtMoneda(String(Math.abs(v)))})`, clase: "pl-neg" };
}

function totalCostosDirectos(p: EstadoResultadosPeriodo): number {
  return (
    n(p.costos_afiliados.pagado) +
    n(p.costos_agencias.pagado) +
    n(p.costos_comisiones_vendedores.pagado) +
    n(p.costo_comisiones_agencias_pagado)
  );
}

function totalCostosIndirectos(p: EstadoResultadosPeriodo): number {
  return n(p.costo_nominas) + n(p.costo_overhead);
}

interface KpiProps {
  etiqueta: string;
  valor: string;
  bueno?: boolean;
  malo?: boolean;
  tendenciaPct?: string | null;
  nota?: string;
}

function Kpi({ etiqueta, valor, bueno, malo, tendenciaPct, nota }: KpiProps) {
  const dir = tendenciaPct !== undefined ? direccionTendencia(tendenciaPct) : null;
  return (
    <div className="kpi-box">
      <div className="kpi-lbl">{etiqueta}</div>
      <div className={`kpi-val ${bueno ? "good" : ""} ${malo ? "bad" : ""}`}>{valor}</div>
      {(dir || nota) && (
        <div className="kpi-sub">
          {dir && tendenciaPct !== undefined && (
            <span className={`kpi-trend ${dir}`}>{textoTendencia(tendenciaPct ?? null)}</span>
          )}{" "}
          {nota}
        </div>
      )}
    </div>
  );
}

function Indicador({ etiqueta, valor, colorSigno }: { etiqueta: string; valor: string; colorSigno?: boolean }) {
  const malo = colorSigno && n(valor.replace("%", "")) < 0;
  return (
    <div>
      <div className="indicador-lbl">{etiqueta}</div>
      <div className={`indicador-val ${colorSigno ? (malo ? "pl-neg" : "pl-pos") : ""}`}>{valor}</div>
    </div>
  );
}

export function EstadoResultadosPage() {
  const [periodo, setPeriodo] = useState(mesEnCursoLocal());
  const { data, isLoading, isError } = useEstadoResultados(periodo);
  const exportar = useExportarEstadoResultados();
  const [formato, setFormato] = useState<FormatoExportacion>("xlsx");

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Estado de resultados</div>
          <div className="cat-sub">
            P&amp;L consolidado por periodo, sin IVA, base caja. Comparado contra el mes
            anterior.
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            type="month"
            className="fi"
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value)}
            aria-label="Periodo"
          />
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
            disabled={!data || exportar.isPending}
            onClick={() => data && exportar.mutate({ periodo: data.actual.periodo, formato })}
          >
            Exportar
          </button>
        </div>
      </div>

      {isLoading && <div className="state-msg">Cargando…</div>}
      {isError && <div className="state-msg">No se pudo cargar el Estado de resultados.</div>}

      {data && <EstadoResultadosContenido data={data} />}
    </>
  );
}

function EstadoResultadosContenido({
  data,
}: {
  data: NonNullable<ReturnType<typeof useEstadoResultados>["data"]>;
}) {
  const p = data.actual;
  const cd = totalCostosDirectos(p);
  const ci = totalCostosIndirectos(p);
  const bruta = montoConSigno(p.utilidad_bruta);
  const neta = montoConSigno(p.utilidad_neta);

  const costosDirectosLineas: Array<[string, string]> = [
    ["Pagos a afiliados", p.costos_afiliados.pagado],
    ["Pagos a agencias", p.costos_agencias.pagado],
    ["Comisiones a vendedores", p.costos_comisiones_vendedores.pagado],
  ];
  if (n(p.costo_comisiones_agencias_pagado) > 0) {
    costosDirectosLineas.push(["Comisiones a agencias (req.)", p.costo_comisiones_agencias_pagado]);
  }

  const composicion = [
    { etiqueta: "Afiliados", valor: n(p.costos_afiliados.pagado) },
    { etiqueta: "Agencias", valor: n(p.costos_agencias.pagado) },
    { etiqueta: "Comisiones vend.", valor: n(p.costos_comisiones_vendedores.pagado) },
    { etiqueta: "Nóminas", valor: n(p.costo_nominas) },
    { etiqueta: "Overhead", valor: n(p.costo_overhead) },
  ];
  const maxComposicion = Math.max(1, ...composicion.map((c) => c.valor));
  const cobrado = n(p.ingresos_cobrado);

  const maxAbsHistorico = Math.max(1, ...data.historico.map((x) => Math.abs(n(x.utilidad_neta))));

  return (
    <>
      <div className="kpi-strip">
        <Kpi etiqueta="Facturado" valor={fmtMonedaCorta(p.ingresos_facturado)} />
        <Kpi
          etiqueta="Cobrado"
          valor={fmtMonedaCorta(p.ingresos_cobrado)}
          tendenciaPct={data.tendencia.ingresos_cobrado_pct}
          nota={p.pct_cobranza != null ? `· ${fmtPorcentaje(p.pct_cobranza)} del facturado` : undefined}
        />
        <Kpi
          etiqueta="Utilidad bruta"
          valor={fmtMonedaCorta(p.utilidad_bruta)}
          bueno={n(p.utilidad_bruta) >= 0}
          malo={n(p.utilidad_bruta) < 0}
          tendenciaPct={data.tendencia.utilidad_bruta_pct}
          nota={p.margen_bruto_pct != null ? `· margen ${fmtPorcentaje(p.margen_bruto_pct)}` : undefined}
        />
        <Kpi
          etiqueta="Utilidad neta"
          valor={fmtMonedaCorta(p.utilidad_neta)}
          bueno={n(p.utilidad_neta) >= 0}
          malo={n(p.utilidad_neta) < 0}
          tendenciaPct={data.tendencia.utilidad_neta_pct}
          nota={p.margen_neto_pct != null ? `· margen ${fmtPorcentaje(p.margen_neto_pct)}` : undefined}
        />
      </div>

      <div className="grid2" style={{ margin: "14px 22px" }}>
        <div className="panel">
          <div className="panel-title">
            P&amp;L · {fmtPeriodo(p.periodo)}
            {p.en_curso && " (en curso)"}
          </div>
          <table className="pl-table">
            <tbody>
              <tr className="sec-header">
                <td colSpan={2}>Ingresos</td>
              </tr>
              <tr>
                <td>Facturado en el periodo</td>
                <td>{fmtMoneda(p.ingresos_facturado)}</td>
              </tr>
              <tr>
                <td>Cobrado en el periodo</td>
                <td>{fmtMoneda(p.ingresos_cobrado)}</td>
              </tr>
              <tr className="subtotal">
                <td>Total ingresos cobrados</td>
                <td>{fmtMoneda(p.ingresos_cobrado)}</td>
              </tr>

              <tr className="sec-header">
                <td colSpan={2}>Costos directos</td>
              </tr>
              {costosDirectosLineas.map(([etiqueta, valor]) => (
                <tr key={etiqueta}>
                  <td>{etiqueta}</td>
                  <td className="pl-neg">{montoDeduccion(valor)}</td>
                </tr>
              ))}
              <tr className="subtotal">
                <td>Total costos directos</td>
                <td className="pl-neg">{montoDeduccion(String(cd))}</td>
              </tr>

              <tr className="total">
                <td>Utilidad bruta</td>
                <td className={bruta.clase}>{bruta.texto}</td>
              </tr>

              <tr className="sec-header">
                <td colSpan={2}>Costos indirectos</td>
              </tr>
              <tr>
                <td>Nóminas</td>
                <td className="pl-neg">{montoDeduccion(p.costo_nominas)}</td>
              </tr>
              <tr>
                <td>Overhead</td>
                <td className="pl-neg">{montoDeduccion(p.costo_overhead)}</td>
              </tr>
              <tr className="subtotal">
                <td>Total costos indirectos</td>
                <td className="pl-neg">{montoDeduccion(String(ci))}</td>
              </tr>

              <tr className="total">
                <td>Utilidad neta</td>
                <td className={neta.clase}>{neta.texto}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 14 }}>
            <div className="panel-title">
              Composición de costos <span className="card-title-sub">% del cobrado</span>
            </div>
            {composicion.map((c) => (
              <div className="hbar-row" key={c.etiqueta}>
                <div className="hbar-lbl">{c.etiqueta}</div>
                <div className="hbar-bg">
                  <div
                    className="hbar-fill"
                    style={{ width: `${(c.valor / maxComposicion) * 100}%` }}
                  />
                </div>
                <div className="hbar-val">
                  {fmtMonedaCorta(String(c.valor))}{" "}
                  <span style={{ color: "var(--text3)", fontSize: 11, fontWeight: 400 }}>
                    {cobrado > 0 ? `${((c.valor / cobrado) * 100).toFixed(1)}%` : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="panel">
            <div className="panel-title">
              Indicadores clave <span className="card-title-sub">periodo actual</span>
            </div>
            <div className="grid2" style={{ gap: 14 }}>
              <Indicador etiqueta="Margen bruto" valor={fmtPorcentaje(p.margen_bruto_pct)} colorSigno />
              <Indicador etiqueta="Margen neto" valor={fmtPorcentaje(p.margen_neto_pct)} colorSigno />
              <Indicador etiqueta="% Cobranza" valor={fmtPorcentaje(p.pct_cobranza)} />
              <Indicador
                etiqueta="Costo afiliados / cobrado"
                valor={fmtPorcentaje(p.costo_afiliados_pct_cobrado)}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ margin: "14px 22px" }}>
        <div className="panel-title">
          Evolución de utilidad neta <span className="card-title-sub">6 meses</span>
        </div>
        <div className="chart-bar">
          {data.historico.map((x) => {
            const valor = n(x.utilidad_neta);
            const pctAltura = (Math.abs(valor) / maxAbsHistorico) * 100;
            const cls = x.periodo === p.periodo ? (valor >= 0 ? "pos" : "neg") : "muted";
            return (
              <div className="chart-col" key={x.periodo}>
                <div className="chart-bar-stack" title={`${fmtPeriodoCorto(x.periodo)}: ${fmtMoneda(x.utilidad_neta)}`}>
                  <div
                    className={`chart-bar-fill ${cls}`}
                    style={{ height: `${Math.max(pctAltura, 2)}%` }}
                  >
                    <span
                      className="chart-col-val"
                      style={{ color: valor >= 0 ? "var(--green-text)" : "var(--red-text)" }}
                    >
                      {fmtMonedaCorta(x.utilidad_neta)}
                    </span>
                  </div>
                </div>
                <div
                  className="chart-col-lbl"
                  style={x.periodo === p.periodo ? { fontWeight: 700, color: "var(--text2)" } : undefined}
                >
                  {fmtPeriodoCorto(x.periodo)}
                </div>
              </div>
            );
          })}
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
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--green-text)" }} />
            Mes seleccionado positivo
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--red-text)" }} />
            Mes seleccionado negativo
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--phase)" }} />
            Otros meses
          </span>
        </div>
      </div>

      <div className="panel" style={{ margin: "14px 22px" }}>
        <div className="panel-title">Detalle histórico mensual</div>
        <table className="cat-table">
          <thead>
            <tr>
              <th>Periodo</th>
              <th className="td-right">Facturado</th>
              <th className="td-right">Cobrado</th>
              <th className="td-right">Costos directos</th>
              <th className="td-right">Util. bruta</th>
              <th className="td-right">Costos indirectos</th>
              <th className="td-right">Util. neta</th>
              <th className="td-right">Margen %</th>
            </tr>
          </thead>
          <tbody>
            {data.historico.map((x) => {
              const xBruta = montoConSigno(x.utilidad_bruta);
              const xNeta = montoConSigno(x.utilidad_neta);
              return (
                <tr key={x.periodo} className={x.periodo === p.periodo ? "sel" : ""}>
                  <td className="td-mono">
                    {fmtPeriodoCorto(x.periodo)}
                    {x.en_curso && " (en curso)"}
                  </td>
                  <td className="td-right td-mono">{fmtMonedaCorta(x.ingresos_facturado)}</td>
                  <td className="td-right td-mono">{fmtMonedaCorta(x.ingresos_cobrado)}</td>
                  <td className="td-right td-mono pl-neg">{fmtMonedaCorta(String(totalCostosDirectos(x)))}</td>
                  <td className={`td-right td-mono ${xBruta.clase}`}>{fmtMonedaCorta(x.utilidad_bruta)}</td>
                  <td className="td-right td-mono pl-neg">{fmtMonedaCorta(String(totalCostosIndirectos(x)))}</td>
                  <td className={`td-right td-mono ${xNeta.clase}`}>{fmtMonedaCorta(x.utilidad_neta)}</td>
                  <td className={`td-right ${xNeta.clase}`}>{fmtPorcentaje(x.margen_neto_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
