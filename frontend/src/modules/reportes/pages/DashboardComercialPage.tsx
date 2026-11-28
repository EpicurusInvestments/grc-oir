/** F4-02 — Dashboard comercial. Selector de ventana (YTD/mes/trimestre), 4 KPI, Top
 * vendedores/anunciantes/categorías/agencias (barras horizontales) y evolución mensual
 * de ventas (barras verticales) — mismo layout del mockup aprobado.
 */

import { useState } from "react";

import { fmtMonedaCorta, fmtPeriodoCorto, fmtPorcentaje, mesEnCursoLocal } from "../format";
import { useDashboardComercial, useExportarDashboardComercial } from "../hooks";
import type { FormatoExportacion, VentanaComercial } from "../types";

function n(v: string | null): number {
  return v == null ? 0 : Number(v);
}

interface KpiProps {
  etiqueta: string;
  valor: string;
  nota?: string;
}

function Kpi({ etiqueta, valor, nota }: KpiProps) {
  return (
    <div className="kpi-box">
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
  color,
}: {
  etiqueta: string;
  subEtiqueta?: string;
  valor: number;
  max: number;
  nota?: string;
  color?: string;
}) {
  return (
    <div className="hbar-row">
      <div className="hbar-lbl">
        {etiqueta}
        {subEtiqueta && <div style={{ fontSize: 10, color: "var(--text3)", fontWeight: 400 }}>{subEtiqueta}</div>}
      </div>
      <div className="hbar-bg">
        <div
          className="hbar-fill"
          style={{ width: `${max > 0 ? (valor / max) * 100 : 0}%`, background: color }}
        />
      </div>
      <div className="hbar-val">
        {fmtMonedaCorta(String(valor))}
        {nota && <span style={{ color: "var(--text3)", fontSize: 11, fontWeight: 400 }}> {nota}</span>}
      </div>
    </div>
  );
}

/** Un color fijo por panel (identidad del corte, no del valor) — paleta validada con
 * `dataviz/scripts/validate_palette.js` (CVD-safe en modo claro, con la etiqueta
 * directa de cada barra como mitigación del WARN de contraste de `--aqua`). */
const COLOR_VENDEDORES = "var(--blue)";
const COLOR_ANUNCIANTES = "#00b894"; // "aqua" — no existe como token, color puntual.
const COLOR_CATEGORIAS = "var(--purple)";
const COLOR_AGENCIAS = "var(--amber)";

/** 6 colores distintos para "Evolución de ventas mensuales" (uno por barra/mes, pedido
 * explícito del usuario) — orden validado de la paleta de referencia (adjacentes
 * CVD-safe); se cicla si algún día hay más de 6 meses. */
const COLORES_EVOLUCION = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17"];

const ETIQUETA_VENTANA: Record<VentanaComercial, string> = {
  ytd: "YTD",
  mes: "Mes",
  trimestre: "Trimestre",
};

export function DashboardComercialPage() {
  const [ventana, setVentana] = useState<VentanaComercial>("mes");
  const [periodo, setPeriodo] = useState(mesEnCursoLocal());
  const { data, isLoading, isError } = useDashboardComercial(ventana, periodo);
  const exportar = useExportarDashboardComercial();
  const [formato, setFormato] = useState<FormatoExportacion>("xlsx");

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Dashboard comercial</div>
          <div className="cat-sub">
            Ventas por vendedor, anunciante, agencia y Giro Empresarial.
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
      {isError && <div className="state-msg">No se pudo cargar el dashboard comercial.</div>}

      {data && (
        <>
          <div className="kpi-strip">
            <Kpi etiqueta="Ventas" valor={fmtMonedaCorta(data.ventas_total)} nota={`${data.ordenes_total} órdenes`} />
            <Kpi etiqueta="Ticket promedio" valor={fmtMonedaCorta(data.ticket_promedio)} nota="por orden" />
            <Kpi
              etiqueta="Comisiones vendedores"
              valor={fmtMonedaCorta(data.comisiones_vendedores_total)}
              nota={
                n(data.ventas_total) > 0
                  ? `${fmtPorcentaje(String((n(data.comisiones_vendedores_total) / n(data.ventas_total)) * 100))} del total`
                  : undefined
              }
            />
            <Kpi etiqueta="Anunciantes con ventas" valor={String(data.anunciantes_con_ventas)} />
          </div>

          <div className="grid2" style={{ margin: "14px 22px" }}>
            <div className="panel">
              <div className="panel-title">
                Top vendedores <span className="card-title-sub">por ventas</span>
              </div>
              {data.top_vendedores.length === 0 && <div className="state-msg">Sin ventas en la ventana.</div>}
              {(() => {
                const max = Math.max(1, ...data.top_vendedores.map((v) => n(v.ventas)));
                return data.top_vendedores.map((v) => (
                  <HBarRow
                    key={v.vendedor_id}
                    etiqueta={v.nombre}
                    subEtiqueta={`${v.ordenes} órdenes · ${fmtMonedaCorta(v.comision_total)} comisión`}
                    valor={n(v.ventas)}
                    max={max}
                    color={COLOR_VENDEDORES}
                  />
                ));
              })()}
            </div>

            <div className="panel">
              <div className="panel-title">
                Top anunciantes <span className="card-title-sub">por ventas</span>
              </div>
              {data.top_anunciantes.length === 0 && <div className="state-msg">Sin ventas en la ventana.</div>}
              {(() => {
                const max = Math.max(1, ...data.top_anunciantes.map((a) => n(a.ventas)));
                return data.top_anunciantes.map((a) => (
                  <HBarRow
                    key={a.anunciante_id}
                    etiqueta={a.nombre}
                    subEtiqueta={`${a.ordenes} órdenes`}
                    valor={n(a.ventas)}
                    max={max}
                    color={COLOR_ANUNCIANTES}
                  />
                ));
              })()}
            </div>
          </div>

          <div className="grid2" style={{ margin: "14px 22px" }}>
            <div className="panel">
              <div className="panel-title">
                Ventas por categoría <span className="card-title-sub">Giro Empresarial</span>
              </div>
              {data.top_categorias.length === 0 && <div className="state-msg">Sin ventas en la ventana.</div>}
              {(() => {
                const max = Math.max(1, ...data.top_categorias.map((c) => n(c.ventas)));
                return data.top_categorias.map((c) => (
                  <HBarRow
                    key={c.categoria_id ?? "sin-categoria"}
                    etiqueta={c.nombre}
                    valor={n(c.ventas)}
                    max={max}
                    nota={c.pct != null ? fmtPorcentaje(c.pct) : undefined}
                    color={COLOR_CATEGORIAS}
                  />
                ));
              })()}
            </div>

            <div className="panel">
              <div className="panel-title">
                Ventas por agencia <span className="card-title-sub">comisión asociada</span>
              </div>
              {data.top_agencias.length === 0 && <div className="state-msg">Sin ventas en la ventana.</div>}
              {(() => {
                const max = Math.max(1, ...data.top_agencias.map((a) => n(a.ventas)));
                return data.top_agencias.map((a) => (
                  <HBarRow
                    key={a.agencia_id ?? "trato-directo"}
                    etiqueta={a.nombre}
                    subEtiqueta={
                      a.comision_pct != null
                        ? `${fmtPorcentaje(a.comision_pct)} comisión · ${fmtMonedaCorta(a.comision)}`
                        : "Sin comisión"
                    }
                    valor={n(a.ventas)}
                    max={max}
                    color={COLOR_AGENCIAS}
                  />
                ));
              })()}
            </div>
          </div>

          <div className="panel" style={{ margin: "14px 22px" }}>
            <div className="panel-title">Evolución de ventas mensuales</div>
            <div className="chart-bar">
              {(() => {
                const max = Math.max(1, ...data.evolucion_mensual.map((p) => n(p.ventas)));
                return data.evolucion_mensual.map((p, i) => (
                  <div className="chart-col" key={p.periodo}>
                    <div className="chart-bar-stack">
                      <div
                        className="chart-bar-fill"
                        style={{
                          height: `${Math.max((n(p.ventas) / max) * 100, 2)}%`,
                          background: COLORES_EVOLUCION[i % COLORES_EVOLUCION.length],
                        }}
                      >
                        <span className="chart-col-val" style={{ color: "var(--text2)" }}>
                          {fmtMonedaCorta(p.ventas)}
                        </span>
                      </div>
                    </div>
                    <div className="chart-col-lbl">{fmtPeriodoCorto(p.periodo)}</div>
                  </div>
                ));
              })()}
            </div>
          </div>
        </>
      )}
    </>
  );
}
