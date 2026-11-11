/** Pago múltiple (ADR-225, petición del usuario) — pantalla completa, análoga a
 * `facturacion/facturaCliente/pages/ListasParaFacturarPage.tsx` (ADR-064/ADR-201): un
 * checkbox separa "por Anunciante" / "por Agencia" (mutuamente excluyentes), un combo
 * elige el cliente concreto, y se listan sus facturas pendientes con checkbox + monto
 * editable por renglón.
 *
 * A diferencia de ADR-064 (una sola línea de Detalle CONSOLIDADA en el archivo del
 * timbrador), aquí CADA factura seleccionada se registra como su propio `PagoCliente`
 * (con su propio monto) — no hay "consolidación": el backend ya lo resuelve así
 * (`crear_multiple`, un `PagoCliente` por renglón, mismo `pago_multiple_id`).
 *
 * ADR-227 (petición del usuario): a diferencia del diseño original (que no topaba
 * "monto aplicado" contra el pendiente de cada factura, igual que el pago sencillo),
 * AQUÍ sí se bloquea el guardado si algún renglón excede su propio pendiente — el
 * backend no lo exige, así que es una validación SOLO de este formulario. También:
 * "Número de pago" deja de capturarse a mano (igual que en `RegistrarPagoForm.tsx`,
 * ADR-226) y se mueve a la tabla como "Número de Parcialidad" calculada POR FACTURA
 * (cada una tiene su propio historial, así que la parcialidad "último + 1" no es la
 * misma para todas las seleccionadas en un mismo lote) — viaja en el payload por
 * renglón (`PagoMultipleItem.numero_pago`), no a nivel del pago múltiple completo.
 *
 * Ajuste posterior (petición del usuario): las facturas ya `cobrada` se EXCLUYEN de la
 * tabla (antes aparecían con el checkbox deshabilitado) — no tienen nada que pagar.
 *
 * ADR-230 (petición del usuario) — "pago de menos": si el monto total no se cubre por
 * completo, el sobrante se guarda como un pago "huérfano" (sin asignar, visible en
 * "Pagos recibidos"). Ese huérfano se puede abrir de nuevo AQUÍ MISMO (prop
 * `origenHuerfano`) para repartirlo entre una o varias facturas: precarga sus datos
 * (fecha, forma de pago, cuenta contable, referencia, fecha de depósito) y bloquea
 * "Monto total del pago" — es dinero YA recibido y documentado, no se re-captura. El
 * payload manda `pago_origen_id` para que el backend lo borre en la MISMA transacción
 * (si vuelve a sobrar algo, nace un huérfano nuevo y más chico).
 */

import { useMemo, useState } from "react";

import { SearchableSelect } from "@/shared/ui";

import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useAgenciasInfo,
  useAnunciantesInfo,
  useCobranzaFacturas,
  useCrearPagoMultiple,
  useCuentasContables,
  useFormasDePago,
} from "../../hooks";
import { ESTATUS_COBRO_LABEL, type PagoHuerfanoOrigen } from "../../types";

type Modo = "anunciante" | "agencia";

const hoy = () => new Date().toISOString().slice(0, 10);

interface Props {
  onCancelar: () => void;
  onRegistrado: () => void;
  /** ADR-230: si se abre para repartir un pago sin asignar ya existente. */
  origenHuerfano?: PagoHuerfanoOrigen | null;
}

export function PagoMultipleForm({ onCancelar, onRegistrado, origenHuerfano }: Props) {
  const [modo, setModo] = useState<Modo>("anunciante");
  const [clienteId, setClienteId] = useState("");

  const [fecha, setFecha] = useState(origenHuerfano?.fecha_pago_cliente ?? hoy());
  const [montoTotal, setMontoTotal] = useState(origenHuerfano?.monto_aplicado ?? "");
  const [formaPago, setFormaPago] = useState(origenHuerfano?.forma_pago_clave ?? "");
  const [fechaDeposito, setFechaDeposito] = useState(origenHuerfano?.fecha_deposito ?? "");
  const [referencia, setReferencia] = useState(origenHuerfano?.referencia_pago ?? "");
  const [cuentaContable, setCuentaContable] = useState(origenHuerfano?.cuenta_contable_id ?? "");
  // ADR-256 (petición del usuario, "NEW FEATURE"): mismo criterio que "Facturado en
  // sistema externo" (ADR-248) — solo identifica el pago, sin ningún efecto hoy.
  const [pagadoExterno, setPagadoExterno] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Montos por renglón — SOLO existen para facturas marcadas (seleccionadas). Quitar la
  // marca descarta el monto capturado; volver a marcarla lo recarga con el pendiente.
  const [montos, setMontos] = useState<Record<string, string>>({});

  const anunciantes = useAnunciantesInfo();
  const agencias = useAgenciasInfo();
  const formasPago = useFormasDePago();
  const cuentasContables = useCuentasContables();
  const crearMultiple = useCrearPagoMultiple();

  const filtros = useMemo(
    () =>
      clienteId === ""
        ? null
        : modo === "anunciante"
          ? { anunciante_id: clienteId, size: 100 }
          : { agencia_id: clienteId, size: 100 },
    [clienteId, modo],
  );
  const { list } = useCobranzaFacturas(filtros ?? { size: 1, page: 1 });
  // Petición del usuario: las facturas ya `cobrada` no tienen nada que pagar — se
  // excluyen de la lista (antes solo se deshabilitaba su checkbox, pero seguían ahí).
  const facturas = useMemo(
    () =>
      filtros ? (list.data?.items ?? []).filter((f) => f.estatus_cobro !== "cobrada") : [],
    [filtros, list.data],
  );

  const seleccionadas = useMemo(
    () => facturas.filter((f) => montos[f.cobranza_id] !== undefined),
    [facturas, montos],
  );
  const montoAsignado = seleccionadas.reduce((s, f) => s + (Number(montos[f.cobranza_id]) || 0), 0);
  const montoTotalNum = Number(montoTotal) || 0;
  const montoPorAsignar = montoTotalNum - montoAsignado;

  // Petición del usuario: el monto de CADA factura no puede exceder su propio pendiente
  // (no se permiten pagos de más) — el botón se deshabilita EN VIVO mientras exista
  // algún renglón así, no solo al hacer clic.
  const facturaExcedida = seleccionadas.find(
    (f) => Number(montos[f.cobranza_id]) > Number(f.importe_pendiente_cobro),
  );
  const mensajeExcedido = facturaExcedida
    ? `El monto de la factura ${facturaExcedida.numero_factura ?? "—"} ` +
      `(${fmtMoneda(montos[facturaExcedida.cobranza_id])}) no puede exceder su pendiente ` +
      `(${fmtMoneda(facturaExcedida.importe_pendiente_cobro)}).`
    : null;

  // Petición del usuario: cambiar de cliente (o de modo Anunciante/Agencia) invalida
  // los datos del pago ya capturados — evita arrastrar por error Forma de pago/Cuenta
  // contable/montos pensados para OTRO cliente. ADR-230: si se está repartiendo un
  // huérfano, esos datos son del pago YA recibido (fijos) — cambiar de cliente solo
  // debe limpiar la selección de facturas, no los datos del pago.
  const limpiarCamposPago = () => {
    if (!origenHuerfano) {
      setFecha(hoy());
      setMontoTotal("");
      setFormaPago("");
      setFechaDeposito("");
      setReferencia("");
      setCuentaContable("");
      setPagadoExterno(false);
    }
    setMontos({});
    setError(null);
  };

  const onElegirModo = (nuevo: Modo) => {
    setModo(nuevo);
    setClienteId("");
    limpiarCamposPago();
  };

  const alternarFactura = (cobranzaId: string, pendiente: string) => {
    setMontos((actual) => {
      const copia = { ...actual };
      if (cobranzaId in copia) {
        delete copia[cobranzaId];
      } else {
        copia[cobranzaId] = pendiente;
      }
      return copia;
    });
  };

  const cambiarMonto = (cobranzaId: string, valor: string) => {
    setMontos((actual) => ({ ...actual, [cobranzaId]: valor }));
  };

  const confirmar = () => {
    if (!clienteId) {
      setError(modo === "anunciante" ? "Selecciona el anunciante." : "Selecciona la agencia.");
      return;
    }
    if (!fecha.trim()) {
      setError("Captura la fecha de aplicación.");
      return;
    }
    if (!montoTotal || montoTotalNum <= 0) {
      setError("Captura el monto total del pago.");
      return;
    }
    if (!formaPago) {
      setError("Selecciona la forma de pago.");
      return;
    }
    if (!cuentaContable) {
      setError("Selecciona la cuenta contable.");
      return;
    }
    if (seleccionadas.length === 0) {
      setError("Selecciona al menos una factura a pagar.");
      return;
    }
    for (const f of seleccionadas) {
      const monto = Number(montos[f.cobranza_id]);
      if (!montos[f.cobranza_id] || Number.isNaN(monto) || monto <= 0) {
        setError(`Captura un monto válido para la factura ${f.numero_factura ?? "—"}.`);
        return;
      }
      // Petición del usuario: el monto de cada factura no puede sobrepasar lo
      // pendiente de ESA factura (no se permiten pagos de más en el pago múltiple).
      const pendiente = Number(f.importe_pendiente_cobro);
      if (monto > pendiente) {
        setError(
          `El monto de la factura ${f.numero_factura ?? "—"} (${fmtMoneda(montos[f.cobranza_id])}) ` +
            `no puede exceder su pendiente (${fmtMoneda(f.importe_pendiente_cobro)}).`,
        );
        return;
      }
    }
    if (montoAsignado > montoTotalNum) {
      setError(
        `La suma de los montos asignados (${fmtMoneda(String(montoAsignado))}) no puede ` +
          `exceder el monto total del pago (${fmtMoneda(montoTotal)}).`,
      );
      return;
    }

    crearMultiple.mutate(
      {
        fecha_pago_cliente: fecha,
        monto_total_pago: montoTotal,
        forma_pago_clave: formaPago,
        fecha_deposito: fechaDeposito || null,
        referencia_pago: referencia.trim() || null,
        cuenta_contable_id: cuentaContable,
        pagos: seleccionadas.map((f) => ({
          cobranza_id: f.cobranza_id,
          monto_aplicado: montos[f.cobranza_id],
          numero_pago: f.siguiente_numero_pago,
        })),
        pago_origen_id: origenHuerfano?.pagoId ?? null,
        pagado_en_sistema_externo: pagadoExterno,
      },
      {
        onSuccess: onRegistrado,
        onError: (e: unknown) => {
          const mensaje =
            e && typeof e === "object" && "message" in e ? String(e.message) : null;
          setError(mensaje ?? "Ocurrió un error inesperado.");
        },
      },
    );
  };

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Pago de Múltiples Facturas</div>
          <div className="cat-sub">
            {origenHuerfano ? (
              <>
                Repartiendo el pago sin asignar de <strong>{fmtMoneda(origenHuerfano.monto_aplicado)}</strong>{" "}
                capturado el {fmtFecha(origenHuerfano.fecha_pago_cliente)}.
              </>
            ) : (
              "Un solo pago recibido, repartido entre varias facturas del mismo anunciante o agencia."
            )}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-sm"
          onClick={onCancelar}
          disabled={crearMultiple.isPending}
        >
          ← Cancelar
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        <div style={{ maxWidth: 1000, margin: "0 auto" }}>
          <div className="form-card">
            <div className="form-card-title">¿A quién se le paga?</div>
            <div style={{ display: "flex", gap: 20, marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input
                  type="checkbox"
                  checked={modo === "anunciante"}
                  onChange={() => onElegirModo("anunciante")}
                />
                Pagar Múltiples Facturas del Anunciante
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input
                  type="checkbox"
                  checked={modo === "agencia"}
                  onChange={() => onElegirModo("agencia")}
                />
                Pagar Múltiples Facturas de la Agencia
              </label>
            </div>
            <div className="fl fl-required">{modo === "anunciante" ? "Anunciante" : "Agencia"}</div>
            <div style={{ maxWidth: 420 }}>
              <SearchableSelect
                value={clienteId}
                onChange={(v) => {
                  setClienteId(v);
                  limpiarCamposPago();
                }}
                options={
                  modo === "anunciante"
                    ? (anunciantes.data ?? []).map((a) => ({
                        value: a.anunciante_id,
                        label: a.nombre_comercial,
                      }))
                    : (agencias.data ?? []).map((a) => ({
                        value: a.agencia_id,
                        label: a.nombre_agencia,
                      }))
                }
              />
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Datos del pago recibido</div>
            {/* Petición del usuario: orden Fecha pago/Fecha aplicación, Forma de pago/
                Cuenta contable, Referencia bancaria/Monto total — "Número de pago" se
                quitó de aquí (ver tabla de abajo, columna "Número de Parcialidad"). */}
            <div className="r2">
              <div>
                <div className="fl">Fecha pago</div>
                <input
                  type="date"
                  className="fi"
                  value={fechaDeposito}
                  onChange={(e) => setFechaDeposito(e.target.value)}
                />
              </div>
              <div>
                <div className="fl fl-required">Fecha de aplicación</div>
                <input
                  type="date"
                  className="fi"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </div>
            </div>
            <div className="r2">
              <div>
                <div className="fl fl-required">Forma de pago</div>
                <select
                  className="fsel"
                  value={formaPago}
                  onChange={(e) => setFormaPago(e.target.value)}
                >
                  <option value="">— Selecciona —</option>
                  {(formasPago.data ?? []).map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <div className="fl fl-required">Cuenta contable</div>
                <select
                  className="fsel"
                  value={cuentaContable}
                  onChange={(e) => setCuentaContable(e.target.value)}
                >
                  <option value="">— Selecciona —</option>
                  {(cuentasContables.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="r2">
              <div>
                <div className="fl">Referencia bancaria</div>
                <input
                  className="fi"
                  placeholder="SPEI-XXXXX / CHE-XXXX"
                  value={referencia}
                  onChange={(e) => setReferencia(e.target.value)}
                />
              </div>
              <div>
                <div className="fl fl-required">Monto total del pago</div>
                <input
                  className="fi"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={montoTotal}
                  disabled={!!origenHuerfano}
                  onChange={(e) => {
                    setMontoTotal(e.target.value);
                    setError(null);
                  }}
                />
              </div>
            </div>
            <label className="check-box" style={{ marginTop: 10, marginBottom: 0 }}>
              <input
                type="checkbox"
                checked={pagadoExterno}
                onChange={(e) => setPagadoExterno(e.target.checked)}
              />
              <div className="check-box-title">Pagado en sistema externo</div>
            </label>
          </div>

          {clienteId && (
            <>
              <div className="mc-row">
                <div className="mc">
                  <div className="mc-lbl">Monto total</div>
                  <div className="mc-val">{fmtMoneda(montoTotal || "0")}</div>
                </div>
                <div className="mc" style={{ background: montoAsignado > 0 ? "var(--green-bg)" : undefined }}>
                  <div className="mc-lbl">Monto asignado</div>
                  <div className="mc-val" style={{ color: montoAsignado > 0 ? "var(--green-text)" : undefined }}>
                    {fmtMoneda(String(montoAsignado))}
                  </div>
                </div>
                <div
                  className="mc"
                  style={{
                    background:
                      montoPorAsignar < 0 ? "var(--red-bg)" : montoPorAsignar > 0 ? "var(--amber-bg)" : undefined,
                  }}
                >
                  <div className="mc-lbl">Monto por asignar</div>
                  <div
                    className="mc-val"
                    style={{
                      color: montoPorAsignar < 0 ? "var(--red-text)" : montoPorAsignar > 0 ? "var(--amber-text)" : undefined,
                    }}
                  >
                    {fmtMoneda(String(montoPorAsignar))}
                  </div>
                </div>
              </div>

              <div className="sec">Facturas disponibles ({facturas.length})</div>
              {list.isLoading && <div className="state-msg">Cargando facturas…</div>}
              {!list.isLoading && facturas.length === 0 && (
                <div className="state-msg">
                  No hay facturas para {modo === "anunciante" ? "este anunciante" : "esta agencia"}.
                </div>
              )}
              {facturas.length > 0 && (
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th className="td-center">Sel.</th>
                      <th>Factura</th>
                      <th>Fecha estimada</th>
                      <th className="td-right">Total</th>
                      <th className="td-right">Cobrado</th>
                      <th className="td-right">Pendiente</th>
                      <th className="td-center">Estado</th>
                      <th className="td-center">Número de Parcialidad</th>
                      <th className="td-right">Monto aplicado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {facturas.map((f) => {
                      const marcada = f.cobranza_id in montos;
                      const totalFactura = Number(f.importe_cobrado) + Number(f.importe_pendiente_cobro);
                      return (
                        <tr key={f.cobranza_id} className={marcada ? "sel" : ""}>
                          <td className="td-center">
                            <input
                              type="checkbox"
                              checked={marcada}
                              onChange={() => alternarFactura(f.cobranza_id, f.importe_pendiente_cobro)}
                            />
                          </td>
                          <td className="td-main mono">{f.numero_factura ?? "—"}</td>
                          <td className="mono" style={{ fontSize: 11 }}>{fmtFecha(f.fecha_estimada_cobro)}</td>
                          <td className="td-right mono">{fmtMoneda(String(totalFactura))}</td>
                          <td className="td-right mono">{oGuion(Number(f.importe_cobrado) > 0 ? fmtMoneda(f.importe_cobrado) : null)}</td>
                          <td className="td-right mono">{oGuion(Number(f.importe_pendiente_cobro) > 0 ? fmtMoneda(f.importe_pendiente_cobro) : null)}</td>
                          <td className="td-center">
                            <span className="badge">{ESTATUS_COBRO_LABEL[f.estatus_cobro]}</span>
                          </td>
                          <td className="td-center mono">{f.siguiente_numero_pago}</td>
                          <td className="td-right">
                            <input
                              className="fi mono"
                              style={{ textAlign: "right", maxWidth: 130 }}
                              inputMode="decimal"
                              disabled={!marcada}
                              value={montos[f.cobranza_id] ?? ""}
                              onChange={(e) => cambiarMonto(f.cobranza_id, e.target.value)}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </>
          )}

          {mensajeExcedido && (
            <div className="state-msg error" style={{ margin: "14px 0 0", textAlign: "left" }}>
              {mensajeExcedido}
            </div>
          )}
          {error && !mensajeExcedido && (
            <div className="state-msg error" style={{ margin: "14px 0 0", textAlign: "left" }}>
              {error}
            </div>
          )}
          {crearMultiple.isError && !error && !mensajeExcedido && (
            <div className="state-msg error" style={{ margin: "14px 0 0", textAlign: "left" }}>
              Ocurrió un error al registrar el pago múltiple.
            </div>
          )}
        </div>
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancelar} disabled={crearMultiple.isPending}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-sm btn-phase"
          onClick={confirmar}
          disabled={crearMultiple.isPending || !!facturaExcedida}
        >
          {crearMultiple.isPending ? "Guardando…" : "Registrar pago múltiple"}
        </button>
      </div>
    </>
  );
}
