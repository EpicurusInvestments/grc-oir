/** Panel de detalle de OrdenEstacion: datos heredados de la OC, estación/plaza/afiliado,
 * tabla de `periodo_transmision`, desglose económico completo (OIR/emisora) y comparación
 * de `precio_spot` contra la tarifa de referencia (catálogo de Tarifas, por estación).
 */

import { useEffect, useState } from "react";

import { contactoAfiliadoApi } from "@/modules/catalogos/afiliado/api";
import { DURACION_SPOT_OPCIONES, PRODUCTO_OPCIONES } from "@/modules/catalogos/tarifa/types";
import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  enviarCorreoOrdenTransmisionApi,
  listarAudiosOrdenEstacionApi,
  listarEnviosCorreoOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import { logEnvioCorreoFromApi, ordenEstacionAudioFromApi } from "../../adapters/fromApi";
import { previsualizarPdfOrdenEstacion, type TipoPdfOrdenEstacion } from "../../adapters/pdfsApi";
import { EstadoOIBadge } from "../../components/EstadoBadge";
import { IVA_RATE } from "../../constants";
import { diaDeSemana, fmtMonto, fmtPct, oGuion } from "../../format";
import { findAfiliado, findEstacion, findPlaza, tarifaReferencia } from "../../state/catalogosCache";
import { oiImporte, oiTotalSpots } from "../../state/selectors";
import type { Incidencia, LogEnvioCorreo, OrdenCliente, OrdenEstacion, OrdenEstacionAudio } from "../../types";
import { MaterialATransmitir } from "./MaterialATransmitir";

interface OrdenEstacionDetailPanelProps {
  oe: OrdenEstacion;
  oc: OrdenCliente | undefined;
  incidencias: Incidencia[];
  onVerOC: () => void;
  onEditar: () => void;
  onCapturarReales: () => void;
  onVerVerificacion: () => void;
}

export function OrdenEstacionDetailPanel({
  oe,
  oc,
  incidencias,
  onVerOC,
  onEditar,
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

  // ADR-106: la duración es propia de la OE, ya no heredada de la OC.
  const tarRef = estacion
    ? tarifaReferencia(estacion.id, estacion.tipo_senal, oe.duracion_spot, oe.producto_tarifa ?? undefined)
    : undefined;
  const tarifaRefNeta = tarRef ? tarRef.tarifa_bruta * (1 - tarRef.descuento_pct / 100) : null;
  const desvioPct = tarifaRefNeta && tarifaRefNeta > 0 ? (oe.precio_spot / tarifaRefNeta - 1) * 100 : null;

  const incidenciasDeLaOE = incidencias.filter((i) => i.orden_interna_id === oe.id);

  // ADR-105/ADR-120: historial de envíos por correo — se recarga al cambiar de OE. El
  // envío "bundle" (`orden_transmision`) ya no es por-PDF, así que el último envío
  // exitoso se muestra UNA vez para toda la OE, sin importar qué botón lo disparó.
  const [envios, setEnvios] = useState<LogEnvioCorreo[]>([]);
  useEffect(() => {
    let cancelado = false;
    listarEnviosCorreoOrdenEstacionApi(oe.id)
      .then((dtos) => {
        if (!cancelado) setEnvios(dtos.map(logEnvioCorreoFromApi));
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, [oe.id]);
  const ultimoEnvio = envios.find((e) => e.tipoPdf === "orden_transmision" && e.exitoso);

  // ADR-120: "Enviar por correo" se deshabilita si el afiliado no tiene ningún contacto
  // ACTIVO con correo cargado (`ContactoAfiliado`) — se avisa antes de intentar, no se
  // deja fallar el envío.
  const [puedeEnviarCorreo, setPuedeEnviarCorreo] = useState(false);
  useEffect(() => {
    let cancelado = false;
    if (!afiliado) {
      setPuedeEnviarCorreo(false);
      return;
    }
    contactoAfiliadoApi
      .listPorAfiliado(afiliado.id, { activo: true, size: 100 })
      .then((page) => {
        if (!cancelado) {
          setPuedeEnviarCorreo(page.items.some((c) => (c.email_contacto ?? "").trim() !== ""));
        }
      })
      .catch(() => {
        if (!cancelado) setPuedeEnviarCorreo(false);
      });
    return () => {
      cancelado = true;
    };
  }, [afiliado]);

  // ADR-103 (corrección): "Material a Transmitir" vive aquí, en el detalle — igual que
  // los PDFs — para que se pueda subir/descargar/quitar audio sin tener que entrar a
  // "Editar" primero. Se recarga al cambiar de OE.
  const [audios, setAudios] = useState<OrdenEstacionAudio[]>([]);
  useEffect(() => {
    let cancelado = false;
    listarAudiosOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) setAudios(dtos.map(ordenEstacionAudioFromApi));
    });
    return () => {
      cancelado = true;
    };
  }, [oe.id]);

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
          {/* Corrige errores de captura: el backend real solo lo permite en
              'borrador'/'asignada' (spec), que en este vocabulario v5 caen ambos en
              "asignada_afiliado" — el único sub-estado antes de empezar a transmitir. */}
          {oe.estatus === "asignada_afiliado" && (
            <button type="button" className="btn btn-sm" onClick={onEditar}>
              Editar
            </button>
          )}
        </div>
      </div>

      <div className="db">
        <div className="sec">Datos heredados de la Orden de Servicio</div>
        {oc ? (
          <div className="rel-item" onClick={onVerOC} style={{ cursor: "pointer" }}>
            <div>
              <div className="rel-name">{oc.folio_orden}</div>
              <div className="rel-sub">{oc.producto}</div>
            </div>
            <span className="fv link">Ver OC →</span>
          </div>
        ) : (
          <div className="fv muted">La Orden de Servicio ya no existe.</div>
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
              <th />
            </tr>
          </thead>
          <tbody>
            {oe.periodo_transmision.map((p, i) => (
              <tr key={i} style={p.cancelada ? { opacity: 0.55 } : undefined}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(p.fecha)}
                </td>
                <td className="td-mono">{p.fecha}</td>
                <td className="td-mono">
                  {p.hora_inicio}–{p.hora_termino}
                </td>
                <td className="td-center td-mono">{p.spots_diarios}</td>
                <td style={{ fontSize: 11, color: "var(--red-text)", fontWeight: 600 }}>
                  {p.cancelada ? "Cancelado" : ""}
                </td>
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
              <td />
            </tr>
          </tfoot>
        </table>

        <div className="sec">Desglose económico</div>
        <div className="r2">
          <div>
            <div className="fl">Producto</div>
            <div className="fv">{oe.producto_tarifa ? etiquetaProducto(oe.producto_tarifa) : "—"}</div>
          </div>
          <div>
            <div className="fl">Duración</div>
            <div className="fv">{etiquetaDuracion(oe.duracion_spot)}</div>
          </div>
        </div>
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

        <MaterialATransmitir ordenEstacionId={oe.id} audios={audios} onAudiosChange={setAudios} />
      </div>

      <div className="df" style={{ flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginRight: "auto" }}>
          <FilaPdf
            oe={oe}
            tipo="servicio"
            etiqueta="PDF #1 · Orden de servicio"
            puedeEnviarCorreo={puedeEnviarCorreo}
            onEnviado={(log) => setEnvios((prev) => [log, ...prev])}
          />
          {/* ADR-121: ya no gateado por sub-estado — los horarios "programados" se
              capturan desde el alta (2.2 ya no es un paso manual separado). */}
          <FilaPdf
            oe={oe}
            tipo="programados"
            etiqueta="PDF #2 · Programados"
            puedeEnviarCorreo={puedeEnviarCorreo}
            onEnviado={(log) => setEnvios((prev) => [log, ...prev])}
          />
          {oe.estatus === "reales_conciliados" && (
            <FilaPdf
              oe={oe}
              tipo="reales"
              etiqueta="PDF #3 · Reales"
              puedeEnviarCorreo={puedeEnviarCorreo}
              onEnviado={(log) => setEnvios((prev) => [log, ...prev])}
            />
          )}
          {ultimoEnvio && (
            <div className="fv muted" style={{ fontSize: 11 }}>
              Orden de Transmisión enviada a {ultimoEnvio.destinatarioEmail} el{" "}
              {fmtFechaHora(ultimoEnvio.fechaEnvio)}
            </div>
          )}
        </div>
        {/* ADR-121: "Capturar Programados" (2.2) ya no es un paso manual — se salta
            directo a "Capturar Reales" desde "asignada_afiliado" (los datos que 2.2
            capturaba ya se capturan desde el alta). `programados_conciliados` se
            conserva por si alguna OE ya avanzó por la vía anterior (legado). */}
        {(oe.estatus === "asignada_afiliado" || oe.estatus === "programados_conciliados") && (
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

/** ADR-120: al hacer clic en un PDF, en vez de abrirlo directo se propone "Enviar por
 * correo" (el paquete fijo de la Orden de Transmisión — mismo destino sin importar cuál
 * de los 3 PDFs disparó el diálogo) o "Imprimir" (abre el PDF, como antes — el propio
 * visor nativo del navegador ya trae su botón de imprimir). "Enviar por correo" se
 * deshabilita si el afiliado no tiene ningún contacto activo con correo cargado. */
function FilaPdf({
  oe,
  tipo,
  etiqueta,
  puedeEnviarCorreo,
  onEnviado,
}: {
  oe: OrdenEstacion;
  tipo: TipoPdfOrdenEstacion;
  etiqueta: string;
  puedeEnviarCorreo: boolean;
  onEnviado: (log: LogEnvioCorreo) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const imprimir = () => {
    setError(null);
    previsualizarPdfOrdenEstacion(oe.id, tipo, oe.folio_orden_interna)
      .then(() => setAbierto(false))
      .catch((e) => setError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el PDF."));
  };

  const enviarCorreo = async () => {
    setEnviando(true);
    setError(null);
    try {
      const dto = await enviarCorreoOrdenTransmisionApi(oe.id);
      onEnviado(logEnvioCorreoFromApi(dto));
      setAbierto(false);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo enviar el correo.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            setError(null);
            setAbierto((v) => !v);
          }}
        >
          📄 {etiqueta}
        </button>
        {abierto && (
          <>
            <button
              type="button"
              className="btn btn-sm btn-teal"
              disabled={enviando || !puedeEnviarCorreo}
              title={
                puedeEnviarCorreo
                  ? undefined
                  : "El afiliado no tiene contactos activos con correo cargado."
              }
              onClick={enviarCorreo}
            >
              {enviando ? "Enviando…" : "✉️ Enviar por correo"}
            </button>
            <button type="button" className="btn btn-sm" disabled={enviando} onClick={imprimir}>
              🖨️ Imprimir
            </button>
            <button type="button" className="btn btn-sm" disabled={enviando} onClick={() => setAbierto(false)}>
              Cancelar
            </button>
          </>
        )}
      </div>
      {error && <div className="fe">{error}</div>}
    </div>
  );
}

function fmtFechaHora(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("es-MX", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function etiquetaProducto(valor: string): string {
  return PRODUCTO_OPCIONES.find((p) => p.value === valor)?.label ?? valor;
}

function etiquetaDuracion(valor: string): string {
  return DURACION_SPOT_OPCIONES.find((d) => d.value === valor)?.label ?? valor;
}

function Linea({ label, valor, fuerte }: { label: string; valor: number; fuerte?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
      <span style={{ color: "var(--text2)" }}>{label}</span>
      <span style={{ fontFamily: "var(--mono)", fontWeight: fuerte ? 600 : 400, fontSize: fuerte ? 14 : 12 }}>{fmtMonto(valor)}</span>
    </div>
  );
}
