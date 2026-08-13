/** Panel de detalle de una Incidencia: contexto completo (OI, estación, afiliado), la
 * diferencia del día que la generó y el ajuste económico resultante. Solo lectura — no hay
 * edición ni alta manual (nace siempre de `avanzarAReales`).
 */

import { fmtMonto } from "../../format";
import { findAfiliado, findEstacion, findPlaza } from "../../state/catalogosCache";
import type { Incidencia, OrdenEstacion } from "../../types";

interface IncidenciaDetailPanelProps {
  incidencia: Incidencia;
  oe: OrdenEstacion | undefined;
  onVerOE: () => void;
  onVerVerificacion: () => void;
}

export function IncidenciaDetailPanel({ incidencia, oe, onVerOE, onVerVerificacion }: IncidenciaDetailPanelProps) {
  const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
  const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
  const plaza = oe ? findPlaza(oe.plaza_id) : undefined;

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{incidencia.fecha_transmision}</div>
            <div className="dh-sub">
              <span className={`badge ${incidencia.tipo === "bonificacion" ? "b-teal" : "b-red"}`}>{incidencia.tipo}</span>
              {oe && <span className="badge b-blue">{oe.folio_orden_interna}</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="db">
        <div className="sec">Origen</div>
        {oe ? (
          <div className="fv">
            Orden interna <strong style={{ fontFamily: "var(--mono)" }}>{oe.folio_orden_interna}</strong> ·{" "}
            {estacion?.nombre_estacion ?? "—"} · {afiliado?.nombre_afiliado ?? "—"}
            {plaza && <span className="muted"> ({plaza.nombre_plaza})</span>}
          </div>
        ) : (
          <div className="fv muted">La orden interna ya no existe.</div>
        )}

        <div className="sec">Comparación del día</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 11 }}>
          <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "10px 12px" }}>
            <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 3, textTransform: "uppercase", fontWeight: 600 }}>
              Asignados
            </div>
            <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "var(--mono)" }}>{incidencia.spots_asignados}</div>
          </div>
          <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "10px 12px" }}>
            <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 3, textTransform: "uppercase", fontWeight: 600 }}>Reales</div>
            <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "var(--mono)" }}>{incidencia.spots_reales}</div>
          </div>
          <div
            style={{
              background: incidencia.diferencia >= 0 ? "var(--teal-bg)" : "var(--red-bg)",
              borderRadius: "var(--r)",
              padding: "10px 12px",
            }}
          >
            <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 3, textTransform: "uppercase", fontWeight: 600 }}>
              Diferencia
            </div>
            <div
              style={{
                fontSize: 17,
                fontWeight: 600,
                fontFamily: "var(--mono)",
                color: incidencia.diferencia >= 0 ? "var(--green-text)" : "var(--red-text)",
              }}
            >
              {incidencia.diferencia >= 0 ? "+" : ""}
              {incidencia.diferencia}
            </div>
          </div>
        </div>

        <div className="fl">Monto de ajuste</div>
        <div
          className="fv mono"
          style={{ fontSize: 18, fontWeight: 600, color: incidencia.monto_ajuste >= 0 ? "var(--green-text)" : "var(--red-text)" }}
        >
          {incidencia.monto_ajuste >= 0 ? "+" : ""}
          {fmtMonto(incidencia.monto_ajuste)}
        </div>

        <div className="sec">Nota de excepción</div>
        <div className="fv muted">{incidencia.nota_excepcion}</div>

        <div className="sec">Registrada</div>
        <div className="fv mono">{incidencia.created_at}</div>
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onVerOE} disabled={!oe}>
          Ver orden interna →
        </button>
        <button type="button" className="btn btn-sm" onClick={onVerVerificacion} disabled={!oe}>
          Ver verificación →
        </button>
      </div>
    </>
  );
}
