/** Panel de detalle del Contrato: anunciante, vigencia + monto, % de comisión (sensible),
 * condiciones/observaciones, adjuntos (PDF real — ADR-027), historial de cambios y la
 * MÁQUINA DE ESTADOS (solo transiciones válidas desde el estado actual, vía el endpoint
 * dedicado).
 */

import { FieldTag, StatusBadge } from "@/shared/ui";

import { fmtMonto, fmtPct } from "../format";
import { useHistorialContrato } from "../hooks";
import { ACCION_ESTADO, type Contrato, type EstadoContrato, ESTADO_BADGE, TRANSICIONES } from "../types";
import { ContratoAdjuntos } from "./ContratoAdjuntos";

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

const fmtFechaHora = (iso: string): string =>
  new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });

const CAMPO_LABEL: Record<string, string> = { porcentaje_comision_contrato: "% comisión" };
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

interface ContratoDetailPanelProps {
  contrato: Contrato;
  canWrite: boolean;
  onEdit: () => void;
  onToggleActivo: () => void;
  togglingActivo?: boolean;
  onTransicionar: (estado: EstadoContrato) => void;
  transicionando?: boolean;
  transicionError?: string | null;
}

export function ContratoDetailPanel({
  contrato,
  canWrite,
  onEdit,
  onToggleActivo,
  togglingActivo,
  onTransicionar,
  transicionando,
  transicionError,
}: ContratoDetailPanelProps) {
  const historial = useHistorialContrato(contrato.contrato_id);
  const histItems = historial.data ?? [];
  const transiciones = TRANSICIONES[contrato.estado_contrato];

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{contrato.nombre_contrato}</div>
            <div className="dh-sub">
              <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                {contrato.numero_contrato}
              </span>
              <span className={`badge ${ESTADO_BADGE[contrato.estado_contrato]}`}>
                {contrato.estado_contrato}
              </span>
              <StatusBadge activo={contrato.activo} labelActivo="Act" labelInactivo="Inact" />
            </div>
          </div>
          {canWrite && (
            <button type="button" className="btn btn-sm" onClick={onEdit}>
              Editar
            </button>
          )}
        </div>
      </div>

      <div className="db">
        <div className="sec">Anunciante</div>
        <div className="rel-item">
          <div>
            <div className="rel-name">{oGuion(contrato.anunciante_nombre)}</div>
            <div className="rel-sub mono">{oGuion(contrato.anunciante_rfc)}</div>
          </div>
        </div>

        <div className="sec">Vigencia y monto</div>
        <div className="r2">
          <div>
            <div className="fl">Inicio</div>
            <div className="fv mono">{contrato.fecha_inicio_contrato}</div>
          </div>
          <div>
            <div className="fl">Fin</div>
            <div className="fv mono">{contrato.fecha_fin_contrato}</div>
          </div>
        </div>
        <div className="fl">Monto del contrato</div>
        <div className="fv mono" style={{ fontSize: 18, fontWeight: 600 }}>
          {fmtMonto(contrato.monto_contrato, { full: true })}
        </div>
        <div className="fl">
          % comisión específica del contrato <FieldTag origin="audit" />
        </div>
        <div className="fv mono">{fmtPct(contrato.porcentaje_comision_contrato)}</div>
        <div className="fv muted" style={{ marginTop: -6, fontSize: 11 }}>
          Sobreescribe el % por defecto de la agencia cuando tiene valor.
        </div>

        <div className="sec">Condiciones comerciales</div>
        <div className="fv muted">{oGuion(contrato.condiciones_comerciales)}</div>

        {contrato.observaciones_contrato && (
          <>
            <div className="sec">Observaciones</div>
            <div className="fv muted">{contrato.observaciones_contrato}</div>
          </>
        )}

        {/* ── Adjuntos (PDF): integración real (ADR-027) ── */}
        <ContratoAdjuntos contrato={contrato} canWrite={canWrite} />

        {/* ── Máquina de estados ── */}
        {canWrite && (
          <>
            <div className="sec">Cambiar estado</div>
            {transiciones.length === 0 ? (
              <div className="fv muted">
                El contrato está «{contrato.estado_contrato}» (estado terminal): no admite más
                transiciones.
              </div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {transiciones.map((destino) => (
                  <button
                    type="button"
                    key={destino}
                    className={`btn btn-sm ${destino === "cancelado" ? "btn-danger" : ""}`}
                    disabled={transicionando}
                    onClick={() => onTransicionar(destino)}
                  >
                    {ACCION_ESTADO[destino]}
                  </button>
                ))}
              </div>
            )}
            {transicionError && (
              <div className="state-msg error" style={{ textAlign: "left", marginTop: 8 }}>
                {transicionError}
              </div>
            )}
          </>
        )}

        {/* ── Historial de cambios ── */}
        <div className="sec">Historial de cambios</div>
        {historial.isLoading && <div className="state-msg">Cargando historial…</div>}
        {historial.isError && <div className="state-msg error">No se pudo cargar el historial.</div>}
        {!historial.isLoading && !historial.isError && histItems.length === 0 && (
          <div className="fv muted">Sin cambios registrados.</div>
        )}
        {histItems.map((h) => (
          <div className="rel-item" key={h.log_cambio_parametro_id}>
            <div>
              <div className="rel-name">
                {labelCampo(h.campo)}: <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_anterior)}</span>{" "}
                → <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_nuevo)}</span>
              </div>
              <div className="rel-sub">
                {fmtFechaHora(h.fecha_cambio)} · {h.usuario}
                {h.motivo_cambio ? ` · ${h.motivo_cambio}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>

      {canWrite && (
        <div className="df">
          <button
            type="button"
            className={`btn btn-sm ${contrato.activo ? "btn-danger" : ""}`}
            disabled={togglingActivo}
            onClick={onToggleActivo}
          >
            {contrato.activo ? "Desactivar contrato" : "Activar contrato"}
          </button>
        </div>
      )}
    </>
  );
}
