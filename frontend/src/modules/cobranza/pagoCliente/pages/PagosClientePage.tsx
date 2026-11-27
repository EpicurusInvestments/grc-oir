/** Pagos recibidos (F3) — un pago GLOBAL por fila (no una factura aplicada por fila).
 *
 * ADR-271 (petición del usuario, "Cancelación de Pago", con desarrolladores
 * consultados): antes esta pantalla listaba una fila por cada `PagoCliente` aplicado a
 * una `CobranzaFactura` (si un pago múltiple cubría 3 facturas, aparecían 3 filas). Ahora
 * agrupa por pago (todas las filas que comparten `pago_multiple_id`, o la única fila si
 * es un pago individual) vía `useGruposPagoCliente` — columnas Fecha/Referencia/
 * Monto/Factura (cantidad)/Estatus. Al seleccionar un pago, el panel de detalle
 * (`usePagoGrupoDetalle`) muestra sus facturas aplicadas (factura/parcialidad/monto) y
 * el total real del pago.
 *
 * Botón "Cancelación de Pago": cancela TODO el pago de una sola vez (baja lógica,
 * `estatus_pago`, NUNCA borra), con motivo obligatorio, y regresa el saldo pendiente a
 * sus facturas — SÍ puede deshacer una factura ya `cobrada` (ADR-286). Fix (petición
 * del usuario): ya NO se rechaza si alguna orden tiene una comisión de agencia/
 * vendedor/afiliado autorizada o pagada con base en ese cobro — esa Requisicion
 * `autorizada` se cancela EN CASCADA (revierte su factura de proveedor a `recibida`,
 * vacía de órdenes); si ya está `pagada`, no se toca (el dinero ya salió) — ver
 * `cobranza_factura.py`, `cancelar()`.
 *
 * Solo lectura para el ALTA: capturar/asignar un pago sigue viviendo en el detalle de
 * "Cobranza de facturas" (`CobranzaFacturasPage`) o en el flujo de "Pagos no asignados"
 * de aquí mismo (ADR-229/230, sin cambios) — esta pantalla no es un segundo punto de
 * captura.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { ConfirmDialog, DetailEmpty, ListDetailLayout, SearchableSelect } from "@/shared/ui";

import { PagoMultipleForm } from "../../cobranzaFactura/components/PagoMultipleForm";
import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useAnunciantesInfo,
  useAsignarPago,
  useCancelarPago,
  useCobranzaFacturas,
  useCrearPagoNoAsignado,
  useGruposPagoCliente,
  useNoAsignados,
  usePagoGrupoDetalle,
} from "../../hooks";
import {
  ESTATUS_PAGO_LABEL,
  type PagoClienteConCobranza,
  type PagoClienteCreate,
  type PagoGrupo,
} from "../../types";
import { PagoSinAsignarForm } from "../components/PagoSinAsignarForm";

type Orden = "fecha_referencia" | "fecha_cantidad";

/** Discrimina las 2 formas de seleccionar un renglón: un pago GLOBAL (tabla principal,
 *  `PagoGrupo`) o un pago SIN ASIGNAR (pestaña "No asignados", sigue siendo un
 *  `PagoCliente` suelto — ADR-229/230, sin cambios). */
type Seleccion =
  | { tipo: "grupo"; data: PagoGrupo }
  | { tipo: "sin_asignar"; data: PagoClienteConCobranza };

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

const pluralFactura = (n: number) => (n === 1 ? "1 factura" : `${n} facturas`);

export function PagosClientePage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Seleccion | null>(null);
  // Petición del usuario: por default Fecha (desc) + Referencia (asc); el usuario puede
  // cambiar a Fecha (desc) + Cantidad de facturas (asc) desde el combo de la toolbar.
  const [orden, setOrden] = useState<Orden>("fecha_referencia");
  // ADR-229 (petición del usuario): filtro "Pagos no asignados" + captura sin factura.
  const [soloNoAsignados, setSoloNoAsignados] = useState(false);
  const [capturando, setCapturando] = useState(false);
  const [facturaDestino, setFacturaDestino] = useState("");
  // ADR-231 (petición del usuario): editable — no debe asignarse de más a la factura;
  // se precarga con el menor entre el pendiente de la factura y lo que queda del
  // huérfano, pero el usuario puede bajarlo para dejar el resto sin asignar.
  const [montoAsignar, setMontoAsignar] = useState("");
  const [asignarError, setAsignarError] = useState<string | null>(null);
  // ADR-230 (petición del usuario): repartir un huérfano con la funcionalidad de Pago
  // Múltiple, precargado con sus datos.
  const [repartiendoHuerfano, setRepartiendoHuerfano] = useState<PagoClienteConCobranza | null>(
    null,
  );
  // ADR-271: confirmación antes de cancelar un pago global.
  const [cancelando, setCancelando] = useState(false);
  const [cancelarError, setCancelarError] = useState<string | null>(null);
  // ADR-286 (petición del usuario): motivo obligatorio al cancelar.
  const [motivoCancelacion, setMotivoCancelacion] = useState("");

  const grupos = useGruposPagoCliente();
  const noAsignados = useNoAsignados();
  const crearNoAsignado = useCrearPagoNoAsignado();
  const asignarPago = useAsignarPago();
  const cancelarPago = useCancelarPago();
  const detalleGrupo = usePagoGrupoDetalle(
    selected?.tipo === "grupo" ? selected.data.pago_cliente_id : null,
  );
  const anunciantes = useAnunciantesInfo();
  const anuncianteMap = useMemo(
    () => new Map((anunciantes.data ?? []).map((a) => [a.anunciante_id, a])),
    [anunciantes.data],
  );
  // Combo "Asignar a una factura": mismas facturas disponibles que Pago Múltiple —
  // excluye las ya `cobrada` (no tienen nada pendiente que cubrir).
  const cobranzasDisponibles = useCobranzaFacturas({ page: 1, size: 100 });
  const opcionesAsignar = useMemo(
    () =>
      (cobranzasDisponibles.list.data?.items ?? [])
        .filter((c) => c.estatus_cobro !== "cobrada")
        .map((c) => ({
          value: c.cobranza_id,
          label: `${c.numero_factura ?? "—"} · ${anuncianteMap.get(c.anunciante_id)?.nombre_comercial ?? "—"}`,
        })),
    [cobranzasDisponibles.list.data, anuncianteMap],
  );
  const facturaSeleccionada = cobranzasDisponibles.list.data?.items.find(
    (c) => c.cobranza_id === facturaDestino,
  );
  const sinAsignarSeleccionado = selected?.tipo === "sin_asignar" ? selected.data : null;
  const montoAsignarNum = Number(montoAsignar) || 0;
  const errorMontoAsignar =
    facturaSeleccionada && sinAsignarSeleccionado && montoAsignar
      ? montoAsignarNum <= 0
        ? "Captura un monto válido."
        : montoAsignarNum > Number(sinAsignarSeleccionado.monto_aplicado)
          ? "No puede exceder el monto sin asignar."
          : montoAsignarNum > Number(facturaSeleccionada.importe_pendiente_cobro)
            ? "No puede exceder el pendiente de la factura."
            : null
      : null;

  const cargando = soloNoAsignados ? noAsignados.isLoading : grupos.isLoading;
  const conError = soloNoAsignados ? noAsignados.isError : grupos.isError;

  const gruposFiltrados = useMemo(() => {
    const base = grupos.data ?? [];
    const qq = q.trim().toLowerCase();
    // Petición del usuario: la búsqueda cubre referencia, fecha y monto — ya no "número
    // de pago" ni "factura" (un pago global puede cubrir varias, no una sola clave de
    // texto que buscar).
    const filtrados = qq
      ? base.filter((g) =>
          [g.referencia_pago ?? "", fmtFecha(g.fecha_pago_cliente), g.monto_pago, fmtMoneda(g.monto_pago)].some(
            (campo) => campo.toLowerCase().includes(qq),
          ),
        )
      : base;

    const ordenados = [...filtrados];
    ordenados.sort((a, b) => {
      if (a.fecha_pago_cliente !== b.fecha_pago_cliente) {
        return a.fecha_pago_cliente < b.fecha_pago_cliente ? 1 : -1; // Fecha desc
      }
      if (orden === "fecha_cantidad") {
        return a.cantidad_facturas - b.cantidad_facturas; // asc
      }
      const campoA = a.referencia_pago ?? "";
      const campoB = b.referencia_pago ?? "";
      return campoA < campoB ? -1 : campoA > campoB ? 1 : 0; // asc
    });
    return ordenados;
  }, [grupos.data, q, orden]);

  const sinAsignarFiltrados = useMemo(() => {
    const base: PagoClienteConCobranza[] = (noAsignados.data?.items ?? []).map((p) => ({
      ...p,
      cobranza: null,
    }));
    const qq = q.trim().toLowerCase();
    if (!qq) return base;
    return base.filter((p) =>
      [p.numero_pago ?? "", p.referencia_pago ?? "", fmtFecha(p.fecha_pago_cliente), p.monto_aplicado, fmtMoneda(p.monto_aplicado)].some(
        (campo) => campo.toLowerCase().includes(qq),
      ),
    );
  }, [noAsignados.data, q]);

  const itemsCount = soloNoAsignados ? sinAsignarFiltrados.length : gruposFiltrados.length;

  const hoyMes = new Date().toISOString().slice(0, 7);
  // ADR-271: un pago `cancelado` ya no cuenta como cobrado — se excluye de ambos KPIs.
  const gruposPagados = (grupos.data ?? []).filter((g) => g.estatus_pago === "pagado");
  const delMes = gruposPagados.filter((g) => g.fecha_pago_cliente.slice(0, 7) === hoyMes);
  const totalMes = delMes.reduce((s, g) => s + Number(g.monto_pago), 0);
  const totalHistorico = gruposPagados.reduce((s, g) => s + Number(g.monto_pago), 0);

  const seleccionarGrupo = (g: PagoGrupo) => {
    setSelected({ tipo: "grupo", data: g });
    setCancelarError(null);
    setMotivoCancelacion("");
  };
  const seleccionarSinAsignar = (p: PagoClienteConCobranza) => {
    setSelected({ tipo: "sin_asignar", data: p });
    setFacturaDestino("");
    setMontoAsignar("");
    setAsignarError(null);
  };

  const confirmarCancelar = () => {
    if (selected?.tipo !== "grupo" || !motivoCancelacion.trim()) return;
    setCancelarError(null);
    cancelarPago.mutate(
      { pagoId: selected.data.pago_cliente_id, motivo: motivoCancelacion.trim() },
      {
        onSuccess: () => {
          setCancelando(false);
          setMotivoCancelacion("");
          setSelected(null);
        },
        onError: (e) => {
          setCancelando(false);
          setCancelarError(mensajeDeError(e));
        },
      },
    );
  };

  const listNode = soloNoAsignados ? (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th className="td-center" style={{ width: 90 }}>Fecha</th>
            <th className="td-center" style={{ width: 260 }}>Referencia</th>
            <th className="td-center">Factura</th>
            <th className="td-center" style={{ width: 120 }}>Monto</th>
            <th className="td-center">Parcialidad</th>
            <th className="td-center">Método</th>
          </tr>
        </thead>
        <tbody>
          {sinAsignarFiltrados.map((p) => (
            <tr
              key={p.pago_cliente_id}
              className={
                selected?.tipo === "sin_asignar" && selected.data.pago_cliente_id === p.pago_cliente_id
                  ? "sel"
                  : ""
              }
              onClick={() => seleccionarSinAsignar(p)}
            >
              <td className="mono td-center" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmtFecha(p.fecha_pago_cliente)}</td>
              <td
                className="mono td-center"
                style={{ fontSize: 11, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {oGuion(p.referencia_pago)}
              </td>
              <td className="td-main mono td-center">
                <span className="badge b-amber">Sin asignar</span>
              </td>
              <td className="td-center mono" style={{ color: "var(--green-text)", fontWeight: 600 }}>
                +{fmtMoneda(p.monto_aplicado)}
              </td>
              <td className="td-center mono">{oGuion(p.numero_pago)}</td>
              <td className="td-2 td-center">{oGuion(p.metodo_pago_clave)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cargando && <div className="state-msg">Cargando pagos…</div>}
      {conError && <div className="state-msg error">No se pudo cargar el historial.</div>}
      {!cargando && !conError && sinAsignarFiltrados.length === 0 && (
        <div className="state-msg">No hay pagos sin asignar.</div>
      )}
    </>
  ) : (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th className="td-center" style={{ width: 90 }}>Fecha</th>
            <th className="td-center" style={{ width: 260 }}>Referencia</th>
            <th className="td-center" style={{ width: 120 }}>Monto</th>
            <th className="td-center">Factura</th>
            <th className="td-center">Estatus</th>
          </tr>
        </thead>
        <tbody>
          {gruposFiltrados.map((g) => (
            <tr
              key={g.pago_cliente_id}
              className={
                selected?.tipo === "grupo" && selected.data.pago_cliente_id === g.pago_cliente_id
                  ? "sel"
                  : ""
              }
              onClick={() => seleccionarGrupo(g)}
            >
              <td className="mono td-center" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmtFecha(g.fecha_pago_cliente)}</td>
              <td
                className="mono td-center"
                style={{ fontSize: 11, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {oGuion(g.referencia_pago)}
              </td>
              <td
                className="td-center mono"
                style={{
                  fontWeight: 600,
                  color: g.estatus_pago === "cancelado" ? "var(--text3)" : "var(--green-text)",
                  textDecoration: g.estatus_pago === "cancelado" ? "line-through" : undefined,
                }}
              >
                +{fmtMoneda(g.monto_pago)}
              </td>
              <td className="td-center mono">{pluralFactura(g.cantidad_facturas)}</td>
              <td className="td-center">
                <span className={`badge ${g.estatus_pago === "cancelado" ? "b-red" : "b-green"}`}>
                  {ESTATUS_PAGO_LABEL[g.estatus_pago]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cargando && <div className="state-msg">Cargando pagos…</div>}
      {conError && <div className="state-msg error">No se pudo cargar el historial.</div>}
      {!cargando && !conError && gruposFiltrados.length === 0 && (
        <div className="state-msg">Sin pagos registrados.</div>
      )}
    </>
  );

  const detalleSinAsignar = sinAsignarSeleccionado ? (
    <>
      <div className="dh">
        {/* Petición del usuario: la referencia sube arriba a la derecha, al mismo nivel
            que el monto, en negrita y con un tamaño más legible. */}
        <div className="dh-row">
          <div>
            <div className="dh-name mono" style={{ color: "var(--green-text)" }}>
              +{fmtMoneda(sinAsignarSeleccionado.monto_aplicado)}
            </div>
            <div className="dh-sub">
              <span className="badge b-amber">Sin asignar</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>
                {fmtFecha(sinAsignarSeleccionado.fecha_pago_cliente)}
              </span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="fl" style={{ justifyContent: "flex-end" }}>
              Referencia
            </div>
            <div className="mono" style={{ fontSize: 15, fontWeight: 700 }}>
              {oGuion(sinAsignarSeleccionado.referencia_pago)}
            </div>
          </div>
        </div>
      </div>
      <div className="db">
        {/* ADR-229/231 (petición del usuario): asignar después un pago capturado
            sin factura — mismas facturas disponibles que Pago Múltiple (sin
            `cobrada`). El monto es editable: no debe asignarse de más a la
            factura, el resto se queda en el propio huérfano (más chico). */}
        <div className="sec">Asignar a una factura</div>
        <div style={{ maxWidth: 420, marginBottom: 10 }}>
          <SearchableSelect
            value={facturaDestino}
            onChange={(v) => {
              setFacturaDestino(v);
              setAsignarError(null);
              const factura = cobranzasDisponibles.list.data?.items.find(
                (c) => c.cobranza_id === v,
              );
              if (factura) {
                const sugerido = Math.min(
                  Number(sinAsignarSeleccionado.monto_aplicado),
                  Number(factura.importe_pendiente_cobro),
                );
                setMontoAsignar(sugerido.toFixed(2));
              } else {
                setMontoAsignar("");
              }
            }}
            options={opcionesAsignar}
            placeholder="Buscar factura…"
          />
        </div>
        {facturaDestino && (
          <div style={{ maxWidth: 200, marginBottom: 10 }}>
            <div className="fl fl-required">Monto a asignar</div>
            <input
              className="fi mono"
              inputMode="decimal"
              value={montoAsignar}
              onChange={(e) => {
                setMontoAsignar(e.target.value);
                setAsignarError(null);
              }}
            />
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            className="btn btn-amber btn-sm"
            disabled={
              !facturaDestino ||
              !montoAsignar ||
              !!errorMontoAsignar ||
              asignarPago.isPending
            }
            onClick={() => {
              setAsignarError(null);
              asignarPago.mutate(
                {
                  pagoId: sinAsignarSeleccionado.pago_cliente_id,
                  cobranzaId: facturaDestino,
                  montoAplicado: montoAsignar,
                },
                {
                  onSuccess: () => {
                    setFacturaDestino("");
                    setMontoAsignar("");
                    setSelected(null);
                  },
                  onError: (e) => setAsignarError(mensajeDeError(e)),
                },
              );
            }}
          >
            {asignarPago.isPending ? "Asignando…" : "Asignar"}
          </button>
          {/* ADR-230 (petición del usuario): repartirlo entre varias facturas con
              la misma funcionalidad de Pago Múltiple, precargado con sus datos. */}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setRepartiendoHuerfano(sinAsignarSeleccionado)}
          >
            Repartir con Pago Múltiple
          </button>
        </div>
        {(errorMontoAsignar || asignarError) && (
          <div className="state-msg error" style={{ textAlign: "left", marginTop: 8 }}>
            {errorMontoAsignar ?? asignarError}
          </div>
        )}

        <div className="sec">Datos del pago</div>
        <div className="fl">Fecha</div>
        <div className="fv mono">{fmtFecha(sinAsignarSeleccionado.fecha_pago_cliente)}</div>
        <div className="fl">Monto aplicado</div>
        <div className="fv mono big" style={{ color: "var(--green-text)" }}>
          {fmtMoneda(sinAsignarSeleccionado.monto_aplicado)}
        </div>
        <div className="fl">Método</div>
        <div className="fv">{sinAsignarSeleccionado.metodo_pago_clave}</div>
        {sinAsignarSeleccionado.archivo_nombre && (
          <>
            <div className="fl">Comprobante</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 11px",
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                fontSize: 12,
              }}
            >
              {sinAsignarSeleccionado.archivo_nombre}
            </div>
          </>
        )}
      </div>
    </>
  ) : null;

  const detalleGrupoNode =
    selected?.tipo === "grupo" ? (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div
                className="dh-name mono"
                style={{
                  color: selected.data.estatus_pago === "cancelado" ? "var(--text3)" : "var(--green-text)",
                  textDecoration: selected.data.estatus_pago === "cancelado" ? "line-through" : undefined,
                }}
              >
                +{fmtMoneda(selected.data.monto_pago)}
              </div>
              <div className="dh-sub">
                <span className={`badge ${selected.data.estatus_pago === "cancelado" ? "b-red" : "b-green"}`}>
                  {ESTATUS_PAGO_LABEL[selected.data.estatus_pago]}
                </span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>
                  {fmtFecha(selected.data.fecha_pago_cliente)}
                </span>
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="fl" style={{ justifyContent: "flex-end" }}>
                Referencia
              </div>
              <div className="mono" style={{ fontSize: 15, fontWeight: 700 }}>
                {oGuion(selected.data.referencia_pago)}
              </div>
            </div>
          </div>
        </div>
        <div className="db">
          <div className="sec">Facturas aplicadas</div>
          {detalleGrupo.isLoading && <div className="fv muted">Cargando…</div>}
          {detalleGrupo.isError && (
            <div className="state-msg error">No se pudo cargar el detalle.</div>
          )}
          {detalleGrupo.data && detalleGrupo.data.aplicaciones.length === 0 && (
            <div className="fv muted">Este pago no tiene facturas aplicadas.</div>
          )}
          {detalleGrupo.data?.aplicaciones.map((a) => (
            <div
              key={a.pago_cliente_id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                padding: "9px 12px",
                marginBottom: 6,
                cursor: "pointer",
              }}
              onClick={() => navigate(`/cobranza?cobranza_id=${a.cobranza_id}`)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontWeight: 600 }}>{a.numero_factura ?? "—"}</span>
                <span className="mono" style={{ fontWeight: 600 }}>{fmtMoneda(a.monto_aplicado)}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--text3)", display: "flex", justifyContent: "space-between" }}>
                <span>Parcialidad {oGuion(a.numero_pago)}</span>
                <span>Ver en Cobranza de facturas →</span>
              </div>
            </div>
          ))}
          {detalleGrupo.data && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontWeight: 700,
                padding: "9px 12px",
                marginTop: 4,
                borderTop: "1px solid var(--border)",
              }}
            >
              <span>Total del pago</span>
              <span className="mono">{fmtMoneda(detalleGrupo.data.total_pago)}</span>
            </div>
          )}

          <div className="sec">Datos del pago</div>
          <div className="fl">Fecha</div>
          <div className="fv mono">{fmtFecha(selected.data.fecha_pago_cliente)}</div>
          <div className="fl">Facturas cubiertas</div>
          <div className="fv mono">{selected.data.cantidad_facturas}</div>
          {detalleGrupo.data?.motivo_cancelacion && (
            <>
              <div className="fl">Motivo de cancelación</div>
              <div className="fv">{detalleGrupo.data.motivo_cancelacion}</div>
            </>
          )}

          <div style={{ marginTop: 14 }}>
            <button
              type="button"
              className="btn btn-sm btn-danger"
              disabled={selected.data.estatus_pago === "cancelado" || detalleGrupo.isLoading}
              onClick={() => setCancelando(true)}
            >
              Cancelación de Pago
            </button>
          </div>
          {cancelarError && (
            <div className="state-msg error" style={{ textAlign: "left", marginTop: 8 }}>
              {cancelarError}
            </div>
          )}
        </div>
      </>
    ) : null;

  const detail = detalleSinAsignar ?? detalleGrupoNode ?? (
    <DetailEmpty message="Selecciona un pago para ver el detalle." />
  );

  if (repartiendoHuerfano) {
    return (
      <PagoMultipleForm
        origenHuerfano={{
          pagoId: repartiendoHuerfano.pago_cliente_id,
          fecha_pago_cliente: repartiendoHuerfano.fecha_pago_cliente,
          monto_aplicado: repartiendoHuerfano.monto_aplicado,
          forma_pago_clave: repartiendoHuerfano.forma_pago_clave,
          fecha_deposito: repartiendoHuerfano.fecha_deposito,
          referencia_pago: repartiendoHuerfano.referencia_pago,
          cuenta_contable_id: repartiendoHuerfano.cuenta_contable_id,
        }}
        onCancelar={() => setRepartiendoHuerfano(null)}
        onRegistrado={() => {
          setRepartiendoHuerfano(null);
          setSelected(null);
        }}
      />
    );
  }

  const detailNode = capturando ? (
    <PagoSinAsignarForm
      submitting={crearNoAsignado.isPending}
      submitError={crearNoAsignado.error ? mensajeDeError(crearNoAsignado.error) : null}
      onCancel={() => setCapturando(false)}
      onConfirm={(data: PagoClienteCreate) =>
        crearNoAsignado.mutate(data, { onSuccess: () => setCapturando(false) })
      }
    />
  ) : (
    detail
  );

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Pagos recibidos</div>
          <div className="cat-sub">
            Historial de pagos del cliente. Cada pago se aplica a una o varias facturas; se
            captura desde el detalle de "Cobranza de facturas".
          </div>
        </div>
        <button type="button" className="btn btn-amber btn-sm" onClick={() => setCapturando(true)}>
          + Pago sin asignar
        </button>
      </div>

      <div className="kpi-strip">
        <div className="kpi-box success">
          <div className="kpi-lbl" style={{ color: "var(--green-text)" }}>Cobrado este mes</div>
          <div className="kpi-val" style={{ color: "var(--green-text)" }}>{fmtMoneda(String(totalMes))}</div>
          <div className="kpi-sub">{delMes.length} pagos</div>
        </div>
        <div className="kpi-box">
          <div className="kpi-lbl">Total histórico</div>
          <div className="kpi-val">{fmtMoneda(String(totalHistorico))}</div>
          <div className="kpi-sub">{gruposPagados.length} pagos registrados</div>
        </div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Buscar pago, referencia, fecha o monto…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="tb-label">Estado</span>
        <button
          type="button"
          className={`fp ${soloNoAsignados ? "active" : ""}`}
          onClick={() => {
            setSoloNoAsignados((v) => !v);
            setSelected(null);
          }}
        >
          No asignados
        </button>
        <div className="tb-spacer" />
        {/* Petición del usuario: orden por default Fecha(desc)+Referencia(asc); permite
            cambiar a Fecha(desc)+Cantidad de facturas(asc). */}
        <select
          className="fsel"
          style={{ maxWidth: 260 }}
          value={orden}
          onChange={(e) => setOrden(e.target.value as Orden)}
        >
          <option value="fecha_referencia">Ordenar: Fecha y Referencia</option>
          <option value="fecha_cantidad">Ordenar: Fecha y Cantidad de facturas</option>
        </select>
        <span className="tb-count">{itemsCount} pagos</span>
      </div>

      <ListDetailLayout list={listNode} detail={detailNode} />

      <ConfirmDialog
        visible={cancelando}
        title="Cancelación de Pago"
        message={
          selected?.tipo === "grupo"
            ? `¿Cancelar este pago de ${fmtMoneda(selected.data.monto_pago)} del ${fmtFecha(selected.data.fecha_pago_cliente)}? ` +
              "Se regresará el saldo pendiente a las facturas que cubría — incluso si alguna " +
              "ya está COBRADA en su totalidad. Si alguna orden ya tiene una comisión de " +
              "agencia/vendedor/afiliado AUTORIZADA (no pagada), esa requisición se cancelará " +
              "también, automáticamente. Las comisiones ya PAGADAS no se tocan. " +
              "Si este pago viene de una Nota de Crédito aplicada a una factura que ya estaba " +
              "cobrada, no aplica aquí — en su lugar se generó una Requisición de Devolución, " +
              "que se cancela desde Requisiciones."
            : ""
        }
        confirmLabel="Cancelar pago"
        danger
        loading={cancelarPago.isPending}
        confirmDisabled={!motivoCancelacion.trim()}
        onConfirm={confirmarCancelar}
        onCancel={() => {
          setCancelando(false);
          setMotivoCancelacion("");
        }}
      >
        <label className="fl" style={{ display: "block", marginTop: 10 }}>
          Motivo de la cancelación *
        </label>
        <textarea
          className="fsel"
          style={{ width: "100%", minHeight: 70, resize: "vertical" }}
          value={motivoCancelacion}
          onChange={(e) => setMotivoCancelacion(e.target.value)}
          placeholder="Explica por qué se cancela este pago…"
        />
      </ConfirmDialog>
    </>
  );
}
