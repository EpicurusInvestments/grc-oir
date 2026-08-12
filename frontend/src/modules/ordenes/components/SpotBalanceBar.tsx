/** Barra de balance de spots: Total / Asignados / Por asignar + barra de progreso.
 * Verde si quedó exacto, ámbar si falta por asignar, rojo si se sobre-asignó.
 * Se reutiliza en el detalle de OrdenCliente (Tanda 1) y en el alta de OrdenEstacion (Tanda 3).
 */

import type { BalanceSpotsOC } from "../state/selectors";

export function SpotBalanceBar({ balance, unidades = "estaciones" }: { balance: BalanceSpotsOC; unidades?: string }) {
  const { totalOC, asignados, porAsignar, pctAsignado, sobreAsignado } = balance;
  const tono = sobreAsignado ? "var(--red-text)" : pctAsignado === 100 ? "var(--green-text)" : "var(--amber-text)";
  const fondo = sobreAsignado ? "var(--red-bg)" : pctAsignado === 100 ? "var(--green-bg)" : "var(--surface2)";
  const borde = sobreAsignado ? "#F5C2C2" : pctAsignado === 100 ? "#A8D585" : "var(--border)";

  return (
    <div style={{ background: fondo, borderRadius: "var(--rl)", padding: "11px 13px", marginBottom: 14, border: `1px solid ${borde}` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          📊 Distribución de spots por {unidades === "estaciones" ? "estación" : unidades}
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
            Total orden
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 600 }}>{totalOC}</div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
            Asignados
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 600, color: tono }}>
            {asignados}
            {sobreAsignado ? " ⚠" : ""}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
            Por asignar
          </div>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 18,
              fontWeight: 600,
              color: porAsignar < 0 ? "var(--red-text)" : porAsignar === 0 ? "var(--green-text)" : "var(--amber-text)",
            }}
          >
            {porAsignar}
          </div>
        </div>
      </div>
      <div style={{ height: 6, background: "var(--surface3)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", background: tono, width: `${pctAsignado}%`, transition: "width .3s" }} />
      </div>
      <div style={{ fontSize: 10, color: tono, marginTop: 5, textAlign: "center", fontWeight: pctAsignado === 100 || sobreAsignado ? 600 : 400 }}>
        {porAsignar > 0
          ? `faltan ${porAsignar} spots por asignar`
          : porAsignar === 0
            ? "✓ 100% asignado"
            : `⚠ excedente de ${Math.abs(porAsignar)} spots`}
      </div>
    </div>
  );
}
