/** Panel de detalle de una Verificación derivada: comparación día a día de lo programado
 * (efectivo) contra lo real, con badge de diferencia por día y el origen explícito
 * ("vista derivada de la orden interna OE-xxx") — ver `VerificacionDerivada` en types.ts.
 */

import { diaDeSemana } from "../../format";
import { findAfiliado, findEstacion, findPlaza } from "../../state/catalogosCache";
import type { Incidencia, OrdenEstacion, VerificacionDerivada } from "../../types";

interface VerificacionDetailPanelProps {
  verificacion: VerificacionDerivada;
  oe: OrdenEstacion | undefined;
  incidencias: Incidencia[];
  onVerOE: () => void;
}

export function VerificacionDetailPanel({ verificacion, oe, incidencias, onVerOE }: VerificacionDetailPanelProps) {
  const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
  const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
  const plaza = oe ? findPlaza(oe.plaza_id) : undefined;

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{verificacion.folioOrdenInterna}</div>
            <div className="dh-sub">
              <span className="badge b-teal">Reconciliada</span>
              {estacion && <span className="badge b-blue">{estacion.nombre_estacion}</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="db">
        <div
          style={{
            background: "var(--surface2)",
            borderRadius: "var(--r)",
            padding: "9px 12px",
            fontSize: 12,
            color: "var(--text2)",
            marginBottom: 14,
          }}
        >
          Vista derivada de la orden interna{" "}
          <strong style={{ fontFamily: "var(--mono)" }}>{verificacion.folioOrdenInterna}</strong> — no existe como registro propio; se
          calcula a partir de lo programado (efectivo) y lo real capturados en la OI. Llegar a 2.3 ya implica que quedó reconciliada.
        </div>

        <div className="sec">Estación / plaza / afiliado</div>
        <div className="r2">
          <div>
            <div className="fl">Estación</div>
            <div className="fv">{estacion?.nombre_estacion ?? "—"}</div>
          </div>
          <div>
            <div className="fl">Plaza</div>
            <div className="fv">{plaza?.nombre_plaza ?? "—"}</div>
          </div>
        </div>
        <div className="fl">Afiliado</div>
        <div className="fv">{afiliado?.nombre_afiliado ?? "—"}</div>

        <div className="sec">Comparación día a día</div>
        <table className="cat-table" style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th>Día</th>
              <th>Fecha</th>
              <th className="td-center">Programado</th>
              <th className="td-center">Real</th>
              <th className="td-center">Diferencia</th>
            </tr>
          </thead>
          <tbody>
            {verificacion.dias.map((d) => (
              <tr key={d.fecha} style={d.diferenciaSpots !== 0 ? { background: "var(--amber-bg)" } : undefined}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(d.fecha)}
                </td>
                <td className="td-mono">{d.fecha}</td>
                <td className="td-center td-mono">{d.programado.spots_diarios}</td>
                <td className="td-center td-mono">{d.real.spots_diarios}</td>
                <td className="td-center">
                  {d.diferenciaSpots === 0 ? (
                    <span style={{ fontSize: 11, color: "var(--green-text)" }}>sin diferencia</span>
                  ) : d.diferenciaSpots > 0 ? (
                    <span className="badge b-teal">+{d.diferenciaSpots}</span>
                  ) : (
                    <span className="badge b-red">{d.diferenciaSpots}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} style={{ textAlign: "right", fontWeight: 600, fontSize: 11, padding: "8px 16px" }}>
                Total
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {verificacion.totalProgramado}
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {verificacion.totalReal}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>

        {incidencias.length > 0 && (
          <>
            <div className="sec">Incidencias generadas</div>
            {incidencias.map((i) => (
              <div key={i.id} className="fv" style={{ fontSize: 12, marginBottom: 8 }}>
                <span className={`badge ${i.tipo === "bonificacion" ? "b-teal" : "b-red"}`}>{i.tipo}</span>{" "}
                <span style={{ color: "var(--text2)" }}>
                  {i.fecha_transmision} · {i.spots_asignados} → {i.spots_reales} spots
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onVerOE}>
          Ver orden interna →
        </button>
      </div>
    </>
  );
}
