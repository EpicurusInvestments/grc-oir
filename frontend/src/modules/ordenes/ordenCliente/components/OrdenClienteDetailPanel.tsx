/** Panel de detalle de OrdenCliente: timeline, datos comerciales, comisiones snapshot,
 * importes, progreso de asignación de spots, órdenes internas hijas, incidencias asociadas,
 * documentos y botonera contextual (Editar, Dar Vo.Bo., Asignar estaciones, Cerrar orden).
 */

import { useState } from "react";

import { nombreDeAdjuntoRef, verAdjuntoOrden } from "../../adapters/adjuntosApi";
import { EstadoOIBadge } from "../../components/EstadoBadge";
import { CommissionSnapshotBlock } from "../../components/CommissionSnapshotBlock";
import { SpotBalanceBar } from "../../components/SpotBalanceBar";
import { Timeline } from "../../components/Timeline";
import { FROZEN_STATES } from "../../constants";
import { fmtMonto, fmtRangoFechas, oGuion } from "../../format";
import {
  findAfiliado,
  findAgencia,
  findAnunciante,
  findEstacion,
  findVendedor,
  contratos,
  empresasFacturadoras,
  marcas,
  categorias,
} from "../../state/catalogosCache";
import type { HistorialComision } from "../../state/OrdenesContext";
import { balanceSpotsOC, oesDeOC, oiImporte, oiPeriodoTexto, totalesOC } from "../../state/selectors";
import type { OrdenCliente, OrdenEstacion, Incidencia } from "../../types";

/** Mismo patrón que `CAMPO_LABEL` en `ContratoDetailPanel.tsx` (F0): nombres de campo
 * legibles para el historial de auditoría. */
const CAMPO_LABEL: Record<string, string> = {
  porcentaje_comision_vendedor_principal_snap: "% comisión vendedor principal",
  porcentaje_comision_vendedor_secundario_snap: "% comisión vendedor secundario",
  porcentaje_comision_agencia_snap: "% comisión agencia",
};
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

const fmtFechaHora = (iso: string): string => new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });

interface OrdenClienteDetailPanelProps {
  oc: OrdenCliente;
  ordenesEstacion: OrdenEstacion[];
  incidencias: Incidencia[];
  historialComisiones: HistorialComision[];
  onSeleccionarOE: (oeId: string) => void;
  onEditar: () => void;
  onAsignarEstaciones: () => void;
  onCerrar: () => void;
}

export function OrdenClienteDetailPanel({
  oc,
  ordenesEstacion,
  incidencias,
  historialComisiones,
  onSeleccionarOE,
  onEditar,
  onAsignarEstaciones,
  onCerrar,
}: OrdenClienteDetailPanelProps) {
  const anunciante = findAnunciante(oc.anunciante_id);
  const agencia = findAgencia(oc.agencia_id);
  const vendedorPrincipal = findVendedor(oc.vendedor_principal_id);
  const vendedorSecundario = findVendedor(oc.vendedor_secundario_id);
  const empresaFacturadora = empresasFacturadoras.find((e) => e.id === oc.empresa_facturadora_id);
  const marca = oc.marca_id ? marcas.find((m) => m.id === oc.marca_id) : null;
  const contrato = oc.contrato_id ? contratos.find((c) => c.id === oc.contrato_id) : null;
  const categoria = oc.categoria_id ? categorias.find((c) => c.id === oc.categoria_id) : null;

  const oes = oesDeOC(ordenesEstacion, oc.id);
  const { total } = totalesOC(oc);
  const balance = balanceSpotsOC(oc, oes);

  const congelado = FROZEN_STATES.includes(oc.estatus_orden);
  const ocConVobo = oc.estatus_orden !== "orden_cliente_sin_vobo";
  const incidenciasDeLaOC = incidencias.filter((i) => oes.some((oe) => oe.id === i.orden_interna_id));
  const historialDeLaOC = historialComisiones.filter((h) => h.entidad_id === oc.id);

  const allClosed = oes.length > 0 && oes.every((oe) => oe.estatus === "reales_conciliados");
  const puedeCerrar = oc.estatus_orden === "orden_interna" && allClosed;

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{oc.folio_orden}</div>
            <div className="dh-sub">
              <span className={`badge ${congelado ? "b-amber" : "b-teal"}`}>
                {oc.estatus_orden === "orden_cliente_sin_vobo"
                  ? "1.1 ODC sin Vo.Bo."
                  : oc.estatus_orden === "orden_cliente_con_vobo"
                    ? "1.2 Con Vo.Bo."
                    : ""}
              </span>
              {anunciante && <span className="badge b-blue">{anunciante.nombre_comercial}</span>}
              {agencia ? <span className="badge b-purple">{agencia.nombre_agencia}</span> : <span className="badge b-amber">Sin agencia</span>}
            </div>
          </div>
          <button type="button" className="btn btn-sm" onClick={onEditar}>
            Editar
          </button>
        </div>
      </div>

      <div className="db">
        <Timeline estatus={oc.estatus_orden} />

        {congelado && (
          <div
            style={{
              background: "var(--amber-bg)",
              color: "var(--amber-text)",
              borderRadius: "var(--r)",
              padding: "9px 12px",
              fontSize: 12,
              marginBottom: 14,
            }}
          >
            🔒 Esta orden está congelada ({oc.estatus_orden === "orden_cerrada" ? "orden cerrada" : "facturada/cobrada"}): se muestra en modo
            lectura. Podrás editar los % de comisión desde «Editar» (canal dedicado, autorizado por el backend).
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 6 }}>
          <Metric label="Spots" value={String(oc.total_spots)} />
          <Metric label="Precio unit." value={fmtMonto(oc.precio_unitario)} />
          <Metric label="Total c/IVA" value={fmtMonto(total)} tono="var(--purple-text)" />
        </div>

        <SpotBalanceBar balance={balance} />

        <div className="sec">Datos comerciales</div>
        <div className="r2">
          <div>
            <div className="fl">No. orden cliente</div>
            <div className="fv mono">{oc.numero_orden_cliente}</div>
          </div>
          <div>
            <div className="fl">Fecha venta</div>
            <div className="fv mono">{oc.fecha_venta}</div>
          </div>
        </div>
        <div className="fl">Vendedor principal{vendedorSecundario ? " / secundario" : ""}</div>
        <div className="fv">
          {vendedorPrincipal ? vendedorPrincipal.nombre_vendedor : "—"}
          {vendedorSecundario && <span style={{ color: "var(--text3)" }}> / {vendedorSecundario.nombre_vendedor}</span>}
        </div>
        <div className="fl">Empresa facturadora</div>
        <div className="fv">{empresaFacturadora ? empresaFacturadora.nombre_empresa : "—"}</div>
        <div className="r2">
          <div>
            <div className="fl">Contrato</div>
            <div className="fv">{contrato ? contrato.nombre_contrato : <span style={{ color: "var(--text3)" }}>Sin contrato</span>}</div>
          </div>
          <div>
            <div className="fl">Categoría</div>
            <div className="fv">{categoria ? categoria.nombre_categoria : "—"}</div>
          </div>
        </div>
        <div className="fl">Marca / Producto</div>
        <div className="fv">
          {marca ? marca.nombre_marca : "—"} <span style={{ color: "var(--text3)" }}>· {oc.producto}</span>
        </div>
        <div className="fl">Campaña</div>
        <div className="fv mono">{fmtRangoFechas(oc.fecha_inicio_campania, oc.fecha_fin_campania)}</div>

        <div className="sec">Condiciones especiales</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 11 }}>
          <span className={`badge ${oc.facturacion_directa_cliente ? "b-amber" : "b-gray"}`}>
            {oc.facturacion_directa_cliente ? "Facturación directa al cliente" : "Vía agencia"}
          </span>
          {oc.afiliado_factura_directo_al_cliente && <span className="badge b-red">Afiliado factura directo al cliente</span>}
        </div>
        {(oc.observaciones_predefinidas || oc.observaciones_libres) && (
          <div className="fv muted" style={{ fontSize: 12 }}>
            {oGuion(oc.observaciones_predefinidas)}
            {oc.observaciones_predefinidas && oc.observaciones_libres ? " · " : ""}
            {oGuion(oc.observaciones_libres)}
          </div>
        )}

        <CommissionSnapshotBlock oc={oc} total={total} />

        {/* Mismo patrón que "Historial de cambios" en ContratoDetailPanel.tsx (F0): el
            reducer ya audita cada cambio de % de comisión en `historialComisiones`, pero
            hasta ahora ninguna pantalla lo mostraba (hallazgo #12 de la revisión). */}
        <div className="sec">Historial de cambios de comisión</div>
        {historialDeLaOC.length === 0 ? (
          <div className="fv muted">Sin cambios registrados.</div>
        ) : (
          historialDeLaOC.map((h) => (
            <div className="rel-item" key={h.log_cambio_parametro_id}>
              <div>
                <div className="rel-name">
                  {labelCampo(h.campo)}: <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_anterior)}</span> →{" "}
                  <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_nuevo)}</span>
                </div>
                <div className="rel-sub">
                  {fmtFechaHora(h.fecha_cambio)} · {h.usuario}
                  {h.motivo_cambio ? ` · ${h.motivo_cambio}` : ""}
                </div>
              </div>
            </div>
          ))
        )}

        <div className="sec">
          Órdenes internas <span className="tb-count">{oes.length}</span>
        </div>
        {!ocConVobo && (
          <div
            style={{
              background: "var(--amber-bg)",
              color: "var(--amber-text)",
              borderRadius: "var(--r)",
              padding: "8px 11px",
              fontSize: 12,
              marginBottom: 10,
            }}
          >
            Esta ODC todavía no tiene Vo.Bo. de revisión (PO §2). No se pueden generar órdenes internas hasta completar el checklist.
          </div>
        )}
        {oes.length === 0 && ocConVobo && <div className="fv muted">Sin órdenes internas todavía.</div>}
        {oes.map((oe) => {
          const estacion = findEstacion(oe.estacion_id);
          const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
          const incDeOE = incidencias.filter((i) => i.orden_interna_id === oe.id);
          return (
            <button
              type="button"
              key={oe.id}
              onClick={() => onSeleccionarOE(oe.id)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                padding: "10px 12px",
                marginBottom: 7,
                fontSize: 13,
                cursor: "pointer",
                background: "var(--surface)",
                font: "inherit",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5, gap: 8 }}>
                <span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text2)", fontWeight: 500 }}>
                    {oe.folio_orden_interna}
                  </span>{" "}
                  <span style={{ fontWeight: 600 }}>{estacion?.nombre_estacion ?? "—"}</span>
                  <span style={{ color: "var(--text3)" }}> · {afiliado?.nombre_afiliado ?? "—"}</span>
                </span>
                <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {incDeOE.length > 0 && <span className="badge b-amber">⚠ {incDeOE.length} inc.</span>}
                  <EstadoOIBadge estatus={oe.estatus} />
                </span>
              </div>
              <div style={{ display: "flex", gap: 11, fontSize: 11, color: "var(--text2)", flexWrap: "wrap" }}>
                <span>{oiPeriodoTexto(oe)}</span>
                <span>
                  <strong style={{ fontFamily: "var(--mono)", color: "var(--text)" }}>{fmtMonto(oiImporte(oe), { sinDecimales: true })}</strong>
                </span>
              </div>
            </button>
          );
        })}

        {incidenciasDeLaOC.length > 0 && (
          <>
            <div className="sec">Incidencias asociadas</div>
            {incidenciasDeLaOC.map((i) => (
              <div key={i.id} className="fv" style={{ fontSize: 12, marginBottom: 8 }}>
                <span className={`badge ${i.tipo === "bonificacion" ? "b-teal" : "b-red"}`}>{i.tipo}</span>{" "}
                <span style={{ color: "var(--text2)" }}>
                  {i.fecha_transmision} · {i.spots_asignados} → {i.spots_reales} spots
                </span>
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                  {i.nota_excepcion}
                </div>
              </div>
            ))}
          </>
        )}

        <div className="sec">Documentos</div>
        {oc.odc_cerrada_ref || oc.carta_conciliacion_ref ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {oc.odc_cerrada_ref && <AdjuntoOrdenDescargaLink refAdjunto={oc.odc_cerrada_ref} />}
            {oc.carta_conciliacion_ref && <AdjuntoOrdenDescargaLink refAdjunto={oc.carta_conciliacion_ref} />}
          </div>
        ) : (
          <div className="fv muted" style={{ fontSize: 12 }}>
            Sin documentos de cierre todavía.
          </div>
        )}
      </div>

      <div className="df" style={{ flexWrap: "wrap" }}>
        {!ocConVobo && (
          <button type="button" className="btn btn-sm btn-teal" onClick={onEditar}>
            → Dar Vo.Bo. (abrir checklist)
          </button>
        )}
        {ocConVobo && (oc.estatus_orden === "orden_interna" || oc.estatus_orden === "orden_cliente_con_vobo") && (
          <button type="button" className="btn btn-sm btn-teal" onClick={onAsignarEstaciones}>
            + Asignar estaciones
          </button>
        )}
        {puedeCerrar && (
          <button type="button" className="btn btn-sm btn-amber" onClick={onCerrar}>
            Cerrar orden →
          </button>
        )}
      </div>
    </>
  );
}

/** Botón de descarga para un adjunto ya subido: muestra el nombre original (sin el
 * prefijo UUID de la clave de almacenamiento) y descarga conservando ese mismo nombre. */
function AdjuntoOrdenDescargaLink({ refAdjunto }: { refAdjunto: string }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <div>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => {
          setError(null);
          verAdjuntoOrden(refAdjunto).catch(() => setError("No se pudo descargar el documento."));
        }}
      >
        ⬇ {nombreDeAdjuntoRef(refAdjunto)}
      </button>
      {error && <div className="fe">{error}</div>}
    </div>
  );
}

function Metric({ label, value, tono }: { label: string; value: string; tono?: string }) {
  return (
    <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "10px 12px" }}>
      <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 3, letterSpacing: "0.03em", textTransform: "uppercase", fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "var(--mono)", color: tono ?? "var(--text)" }}>{value}</div>
    </div>
  );
}
