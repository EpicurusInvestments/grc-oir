/** F4-04 — Dashboard operativo. Selector de ventana (YTD/mes/trimestre), 4 KPI,
 * cumplimiento por estación (ordenado vs. ejecutado), incidencias por afiliado (los 5
 * tipos) y composición de incidencias — mismo layout del mockup aprobado, con la tabla
 * de estaciones usando el patrón `.cat-table` ya existente (el mockup usa `.r-table`,
 * clase que no existe en este tema).
 */

import { useState } from "react";

import { fmtPorcentaje, mesEnCursoLocal } from "../format";
import { useDashboardOperativo, useExportarDashboardOperativo } from "../hooks";
import type { FormatoExportacion, TipoIncidencia, VentanaComercial } from "../types";

function fmtEntero(v: number): string {
  return v.toLocaleString("es-MX");
}

interface KpiProps {
  etiqueta: string;
  valor: string;
  nota?: string;
  tono?: "warn" | "danger";
}

function Kpi({ etiqueta, valor, nota, tono }: KpiProps) {
  return (
    <div className={`kpi-box ${tono ?? ""}`}>
      <div className="kpi-lbl">{etiqueta}</div>
      <div className="kpi-val">{valor}</div>
      {nota && <div className="kpi-sub">{nota}</div>}
    </div>
  );
}

function HBarRow({
  etiqueta,
  subEtiqueta,
  valor,
  max,
  nota,
  alerta,
  color,
}: {
  etiqueta: string;
  subEtiqueta?: string;
  valor: number;
  max: number;
  nota?: string;
  alerta?: boolean;
  color?: string;
}) {
  return (
    <div className="hbar-row" style={{ gridTemplateColumns: "170px 1fr 70px" }}>
      <div className="hbar-lbl">
        {etiqueta}
        {subEtiqueta && (
          <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 400 }}>{subEtiqueta}</div>
        )}
      </div>
      <div className="hbar-bg">
        <div
          className="hbar-fill"
          style={{ width: `${max > 0 ? (valor / max) * 100 : 0}%`, background: color }}
        />
      </div>
      <div className="hbar-val">
        {fmtEntero(valor)}
        {nota && (
          <span
            style={{
              color: alerta ? "var(--red-text)" : "var(--text3)",
              fontSize: 11,
              fontWeight: alerta ? 700 : 400,
            }}
          >
            {" "}
            {nota}
          </span>
        )}
      </div>
    </div>
  );
}

/** Paletas validadas con `dataviz/scripts/validate_palette.js` (CVD-safe, orden
 * adyacente de la paleta de referencia) — mismo criterio que
 * `DashboardComercialPage.tsx` (no se comparte entre páginas, cada una define la suya). */
const COLOR_POR_TIPO_INCIDENCIA: Record<TipoIncidencia, string> = {
  faltante: "#257de0",
  excedente: "#f47230",
  cambio_horario: "#00b894",
  cambio_fecha: "#f2a600",
  spot_no_emitido: "#ee7fac",
};

/** Un color distinto por afiliado (cantidad variable) — se cicla si hay más de 6. La
 * tasa de incidencias (>10%) ya no se marca con el color de la barra (ahora lleva la
 * identidad del afiliado): se resalta en rojo/negrita el texto de la tasa en su lugar. */
const COLORES_AFILIADO = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17"];

/** Umbrales del mockup aprobado (99/97/95%) — color inline porque es un degradado de 4
 * tonos sobre el VALOR de una celda, no un estado binario como `.pl-pos`/`.pl-neg`. */
function colorCumplimiento(pct: number | null): string {
  if (pct == null) return "var(--text)";
  if (pct >= 99) return "var(--green-text)";
  if (pct >= 97) return "var(--text)";
  if (pct >= 95) return "var(--amber-text)";
  return "var(--red-text)";
}

const ETIQUETA_VENTANA: Record<VentanaComercial, string> = {
  ytd: "YTD",
  mes: "Mes",
  trimestre: "Trimestre",
};

const ETIQUETA_TIPO_INCIDENCIA: Record<TipoIncidencia, string> = {
  faltante: "Faltante",
  excedente: "Excedente",
  cambio_horario: "Cambio de horario",
  cambio_fecha: "Cambio de fecha",
  spot_no_emitido: "Spot no emitido",
};

export function DashboardOperativoPage() {
  const [ventana, setVentana] = useState<VentanaComercial>("mes");
  const [periodo, setPeriodo] = useState(mesEnCursoLocal());
  const { data, isLoading, isError } = useDashboardOperativo(ventana, periodo);
  const exportar = useExportarDashboardOperativo();
  const [formato, setFormato] = useState<FormatoExportacion>("xlsx");

  const pctGeneral = data?.cumplimiento_general_pct == null ? null : Number(data.cumplimiento_general_pct);
  const tonoGeneral: KpiProps["tono"] =
    pctGeneral == null ? undefined : pctGeneral >= 98 ? undefined : pctGeneral >= 95 ? "warn" : "danger";

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Dashboard operativo</div>
          <div className="cat-sub">
            Cumplimiento de transmisión, incidencias por afiliado y eficiencia operativa.
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <select
            className="fi"
            value={ventana}
            onChange={(e) => setVentana(e.target.value as VentanaComercial)}
            aria-label="Ventana"
          >
            {Object.entries(ETIQUETA_VENTANA).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
          <input
            type="month"
            className="fi"
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value)}
            aria-label="Periodo de referencia"
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
            disabled={exportar.isPending}
            onClick={() => exportar.mutate({ ventana, periodo, formato })}
          >
            Exportar
          </button>
        </div>
      </div>

      {isLoading && <div className="state-msg">Cargando…</div>}
      {isError && <div className="state-msg">No se pudo cargar el dashboard operativo.</div>}

      {data && (
        <>
          <div className="kpi-strip">
            <Kpi
              etiqueta="Cumplimiento general"
              valor={fmtPorcentaje(data.cumplimiento_general_pct)}
              nota={`${fmtEntero(data.spots_transmitidos_total)} de ${fmtEntero(data.spots_ordenados_total)} spots`}
              tono={tonoGeneral}
            />
            <Kpi etiqueta="Spots transmitidos" valor={fmtEntero(data.spots_transmitidos_total)} />
            <Kpi etiqueta="Incidencias" valor={fmtEntero(data.incidencias_total)} />
            <Kpi etiqueta="Afiliados activos" valor={fmtEntero(data.afiliados_activos)} />
          </div>

          <div className="grid2" style={{ margin: "14px 22px" }}>
            <div className="panel">
              <div className="panel-title">
                Cumplimiento por estación <span className="card-title-sub">ejecutado / ordenado</span>
              </div>
              {data.cumplimiento_por_estacion.length === 0 && (
                <div className="state-msg">Sin días verificados en la ventana.</div>
              )}
              {data.cumplimiento_por_estacion.length > 0 && (
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th>Estación</th>
                      <th className="td-right">Ordenado</th>
                      <th className="td-right">Ejecutado</th>
                      <th className="td-right">% Cumpl.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cumplimiento_por_estacion.map((e) => {
                      const pct = e.pct_cumplimiento == null ? null : Number(e.pct_cumplimiento);
                      return (
                        <tr key={e.estacion_id}>
                          <td className="td-main">{e.nombre_estacion}</td>
                          <td className="td-right td-mono">{fmtEntero(e.ordenado)}</td>
                          <td className="td-right td-mono">{fmtEntero(e.ejecutado)}</td>
                          <td
                            className="td-right td-mono"
                            style={{ color: colorCumplimiento(pct), fontWeight: 600 }}
                          >
                            {fmtPorcentaje(e.pct_cumplimiento)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            <div className="panel">
              <div className="panel-title">
                Incidencias por afiliado <span className="card-title-sub">{ETIQUETA_VENTANA[ventana]}</span>
              </div>
              {data.incidencias_por_afiliado.length === 0 && (
                <div className="state-msg">Sin incidencias en la ventana.</div>
              )}
              {(() => {
                const max = Math.max(1, ...data.incidencias_por_afiliado.map((a) => a.total));
                return data.incidencias_por_afiliado.map((a, i) => (
                  <HBarRow
                    key={a.afiliado_id}
                    etiqueta={a.nombre_afiliado}
                    subEtiqueta={`Falt. ${a.faltantes} · Exc. ${a.excedentes} · Horario ${a.cambios_horario} · Fecha ${a.cambios_fecha} · No emit. ${a.spots_no_emitidos}`}
                    valor={a.total}
                    max={max}
                    nota={a.tasa_pct != null ? fmtPorcentaje(a.tasa_pct) : undefined}
                    alerta={a.alerta}
                    color={COLORES_AFILIADO[i % COLORES_AFILIADO.length]}
                  />
                ));
              })()}
              {data.incidencias_por_afiliado.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: "1px dashed var(--border)",
                    fontSize: 11,
                    color: "var(--text3)",
                  }}
                >
                  Tasa = incidencias / OE totales del afiliado. Por encima de 10% activa revisión.
                </div>
              )}
            </div>
          </div>

          <div className="panel" style={{ margin: "14px 22px" }}>
            <div className="panel-title">Composición de incidencias</div>
            {data.composicion_incidencias.every((c) => c.total === 0) && (
              <div className="state-msg">Sin incidencias en la ventana.</div>
            )}
            {(() => {
              const max = Math.max(1, ...data.composicion_incidencias.map((c) => c.total));
              return data.composicion_incidencias.map((c) => (
                <HBarRow
                  key={c.tipo_incidencia}
                  etiqueta={ETIQUETA_TIPO_INCIDENCIA[c.tipo_incidencia]}
                  valor={c.total}
                  max={max}
                  nota={c.pct != null ? fmtPorcentaje(c.pct) : undefined}
                  color={COLOR_POR_TIPO_INCIDENCIA[c.tipo_incidencia]}
                />
              ));
            })()}
          </div>
        </>
      )}
    </>
  );
}
