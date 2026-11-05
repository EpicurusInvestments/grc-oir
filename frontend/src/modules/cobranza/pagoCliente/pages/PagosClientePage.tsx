/** Pagos recibidos (F3) — historial de `PagoCliente` a través de todas las cobranzas.
 *
 * Solo lectura: el alta/baja de un pago vive en el detalle de "Cobranza de facturas"
 * (`CobranzaFacturasPage`), asociada siempre a UNA `CobranzaFactura` — esta pantalla es
 * el espejo cronológico que pide el mockup, no un segundo punto de captura.
 *
 * El backend no tiene un `GET` de "todos los pagos" (ver `historialPagosCliente` en
 * `api.ts`): esta vista se arma agregando por cobranza, con el límite de 100 ya conocido
 * en el resto del módulo.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { DetailEmpty, ListDetailLayout, SearchableSelect } from "@/shared/ui";

import { PagoMultipleForm } from "../../cobranzaFactura/components/PagoMultipleForm";
import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useAnunciantesInfo,
  useAsignarPago,
  useCobranzaFacturas,
  useCrearPagoNoAsignado,
  useHistorialPagosCliente,
  useNoAsignados,
} from "../../hooks";
import type { PagoClienteConCobranza, PagoClienteCreate } from "../../types";
import { PagoSinAsignarForm } from "../components/PagoSinAsignarForm";

type Orden = "fecha_referencia" | "fecha_factura";

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

export function PagosClientePage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<PagoClienteConCobranza | null>(null);
  // Petición del usuario: por default Fecha (desc) + Referencia (asc); el usuario puede
  // cambiar a Fecha (desc) + Factura (asc) desde el combo de la toolbar.
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

  const historial = useHistorialPagosCliente();
  const noAsignados = useNoAsignados();
  const crearNoAsignado = useCrearPagoNoAsignado();
  const asignarPago = useAsignarPago();
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
  const montoAsignarNum = Number(montoAsignar) || 0;
  const errorMontoAsignar =
    facturaSeleccionada && selected && montoAsignar
      ? montoAsignarNum <= 0
        ? "Captura un monto válido."
        : montoAsignarNum > Number(selected.monto_aplicado)
          ? "No puede exceder el monto sin asignar."
          : montoAsignarNum > Number(facturaSeleccionada.importe_pendiente_cobro)
            ? "No puede exceder el pendiente de la factura."
            : null
      : null;

  const cargando = soloNoAsignados ? noAsignados.isLoading : historial.isLoading;
  const conError = soloNoAsignados ? noAsignados.isError : historial.isError;
  const itemsBase = useMemo<PagoClienteConCobranza[]>(
    () =>
      soloNoAsignados
        ? (noAsignados.data?.items ?? []).map((p) => ({ ...p, cobranza: null }))
        : (historial.data ?? []),
    [soloNoAsignados, noAsignados.data, historial.data],
  );

  const items = useMemo(() => {
    const qq = q.trim().toLowerCase();
    // Petición del usuario: la búsqueda cubre fecha, referencia, factura y monto — no solo
    // referencia. Se compara contra el texto formateado (como se ve en la tabla) y también
    // contra el valor crudo del monto, para que "800" encuentre "$800.00".
    const filtrados = qq
      ? itemsBase.filter((p) =>
          [
            fmtFecha(p.fecha_pago_cliente),
            p.referencia_pago ?? "",
            p.cobranza?.numero_factura ?? "",
            p.monto_aplicado,
            fmtMoneda(p.monto_aplicado),
          ].some((campo) => campo.toLowerCase().includes(qq)),
        )
      : itemsBase;

    const ordenados = [...filtrados];
    ordenados.sort((a, b) => {
      if (a.fecha_pago_cliente !== b.fecha_pago_cliente) {
        return a.fecha_pago_cliente < b.fecha_pago_cliente ? 1 : -1; // Fecha desc
      }
      const [campoA, campoB] =
        orden === "fecha_referencia"
          ? [a.referencia_pago ?? "", b.referencia_pago ?? ""]
          : [a.cobranza?.numero_factura ?? "", b.cobranza?.numero_factura ?? ""];
      return campoA < campoB ? -1 : campoA > campoB ? 1 : 0; // asc
    });
    return ordenados;
  }, [itemsBase, q, orden]);

  const hoyMes = new Date().toISOString().slice(0, 7);
  const delMes = (historial.data ?? []).filter((p) => p.fecha_pago_cliente.slice(0, 7) === hoyMes);
  const totalMes = delMes.reduce((s, p) => s + Number(p.monto_aplicado), 0);
  const totalHistorico = (historial.data ?? []).reduce((s, p) => s + Number(p.monto_aplicado), 0);

  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Referencia</th>
            <th>Factura</th>
            <th className="td-right">Monto</th>
            <th className="td-center">Número de parcialidad</th>
            <th>Método</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr
              key={p.pago_cliente_id}
              className={selected?.pago_cliente_id === p.pago_cliente_id ? "sel" : ""}
              onClick={() => {
                setSelected(p);
                setFacturaDestino("");
                setMontoAsignar("");
                setAsignarError(null);
              }}
            >
              <td className="mono" style={{ fontSize: 11 }}>{fmtFecha(p.fecha_pago_cliente)}</td>
              <td className="mono" style={{ fontSize: 11 }}>{oGuion(p.referencia_pago)}</td>
              <td className="td-main mono">
                {p.cobranza ? (
                  p.cobranza.numero_factura ?? "—"
                ) : (
                  <span className="badge b-amber">Sin asignar</span>
                )}
              </td>
              <td className="td-right mono" style={{ color: "var(--green-text)", fontWeight: 600 }}>
                +{fmtMoneda(p.monto_aplicado)}
              </td>
              <td className="td-center mono">{oGuion(p.numero_pago)}</td>
              <td className="td-2">{oGuion(p.metodo_pago_clave)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cargando && <div className="state-msg">Cargando pagos…</div>}
      {conError && <div className="state-msg error">No se pudo cargar el historial.</div>}
      {!cargando && !conError && items.length === 0 && (
        <div className="state-msg">
          {soloNoAsignados ? "No hay pagos sin asignar." : "Sin pagos registrados."}
        </div>
      )}
    </>
  );

  const detail = selected ? (
    <>
      <div className="dh">
        {/* Petición del usuario: la referencia sube arriba a la derecha, al mismo nivel
            que el monto, en negrita y con un tamaño más legible. */}
        <div className="dh-row">
          <div>
            <div className="dh-name mono" style={{ color: "var(--green-text)" }}>
              +{fmtMoneda(selected.monto_aplicado)}
            </div>
            <div className="dh-sub">
              {selected.cobranza ? (
                <span className="badge b-green">Aplicado</span>
              ) : (
                <span className="badge b-amber">Sin asignar</span>
              )}
              <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>
                {fmtFecha(selected.fecha_pago_cliente)}
              </span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="fl" style={{ justifyContent: "flex-end" }}>
              Referencia
            </div>
            <div className="mono" style={{ fontSize: 15, fontWeight: 700 }}>
              {oGuion(selected.referencia_pago)}
            </div>
          </div>
        </div>
      </div>
      <div className="db">
        {selected.cobranza ? (
          <>
            <div className="sec">Factura aplicada</div>
            <div
              style={{ border: "1px solid var(--border)", borderRadius: "var(--r)", padding: "11px 13px", cursor: "pointer" }}
              onClick={() => navigate(`/cobranza?factura_id=${selected.cobranza?.factura_id}`)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 600, marginBottom: 3 }}>
                <span className="mono">{selected.cobranza.numero_factura ?? "—"}</span>
                <span className="mono">
                  {fmtMoneda(
                    String(
                      Number(selected.cobranza.importe_cobrado) + Number(selected.cobranza.importe_pendiente_cobro),
                    ),
                  )}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--text3)" }}>Ver en Cobranza de facturas →</div>
            </div>
          </>
        ) : (
          <>
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
                      Number(selected.monto_aplicado),
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
                      pagoId: selected.pago_cliente_id,
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
                onClick={() => setRepartiendoHuerfano(selected)}
              >
                Repartir con Pago Múltiple
              </button>
            </div>
            {(errorMontoAsignar || asignarError) && (
              <div className="state-msg error" style={{ textAlign: "left", marginTop: 8 }}>
                {errorMontoAsignar ?? asignarError}
              </div>
            )}
          </>
        )}

        <div className="sec">Datos del pago</div>
        <div className="fl">Fecha</div>
        <div className="fv mono">{fmtFecha(selected.fecha_pago_cliente)}</div>
        <div className="fl">Monto aplicado</div>
        <div className="fv mono big" style={{ color: "var(--green-text)" }}>
          {fmtMoneda(selected.monto_aplicado)}
        </div>
        <div className="fl">Método</div>
        <div className="fv">{selected.metodo_pago_clave}</div>
        {selected.archivo_nombre && (
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
              {selected.archivo_nombre}
            </div>
          </>
        )}
      </div>
    </>
  ) : (
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
            Historial de pagos del cliente. Cada pago se aplica a una cobranza específica;
            se captura desde el detalle de "Cobranza de facturas".
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
          <div className="kpi-sub">{(historial.data ?? []).length} pagos registrados</div>
        </div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Buscar fecha, referencia, factura o monto…"
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
            cambiar a Fecha(desc)+Factura(asc). */}
        <select
          className="fsel"
          style={{ maxWidth: 260 }}
          value={orden}
          onChange={(e) => setOrden(e.target.value as Orden)}
        >
          <option value="fecha_referencia">Ordenar: Fecha y Referencia</option>
          <option value="fecha_factura">Ordenar: Fecha y Factura</option>
        </select>
        <span className="tb-count">{items.length} pagos</span>
      </div>

      <ListDetailLayout list={listNode} detail={detailNode} />
    </>
  );
}
