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
 * ADR-226) y se mueve a la tabla como "Parcialidad" calculada POR FACTURA (cada una
 * tiene su propio historial, así que la parcialidad "último + 1" no es la misma para
 * todas las seleccionadas en un mismo lote) — viaja en el payload por renglón
 * (`PagoMultipleItem.numero_pago`), no a nivel del pago múltiple completo.
 *
 * Ajuste posterior (petición del usuario): las facturas ya `cobrada` se EXCLUYEN de la
 * tabla (antes aparecían con el checkbox deshabilitado) — no tienen nada que pagar.
 *
 * ADR-270 (petición del usuario, "Correcciones en pagos múltiples", con desarrolladores
 * consultados): el pago ya no puede quedar de más ni de menos contra lo capturado.
 * Columna "Ajuste" por renglón (-$10 a +$10, máximo 6 caracteres visibles, ej.
 * "-10.00") que se SUMA a "Monto aplicado" (que sigue siendo el pendiente de la
 * factura, sin tocar) — absorbe diferencias chicas (comisión bancaria, redondeo) para
 * cuadrar exacto, sin redondear sus 2 decimales. El contador "Ajuste" del tablero de
 * montos es la suma en vivo de todos los ajustes capturados.
 *
 * ADR-273 (petición del usuario, "Correcciones en pagos múltiples — parte 2"): a
 * diferencia de ADR-230/270 (donde una diferencia MAYOR a $10 todavía se toleraba como
 * un pago "huérfano", sin asignar, con el sobrante), AHORA el pago NUNCA puede quedar
 * por debajo del monto total capturado, sin importar la diferencia — hay que
 * seleccionar más facturas, subir los montos aplicados, o cuadrar con la columna de
 * Ajuste. El mecanismo de "huérfano" en sí sigue existiendo para OTROS flujos (captura
 * de un pago sin asignar, "Pagos recibidos" → "No asignados", `/asignar`) — aquí solo
 * se quitó la creación automática por sobrante. Si este formulario se abre para
 * REPARTIR un huérfano ya existente (prop `origenHuerfano`): precarga sus datos (fecha,
 * forma de pago, cuenta contable, referencia, fecha de depósito) y bloquea "Monto total
 * del pago" — es dinero YA recibido y documentado, no se re-captura — pero ahora debe
 * repartirse su monto COMPLETO entre las facturas elegidas, sin dejar un sobrante. El
 * payload manda `pago_origen_id` para que el backend lo borre en la MISMA transacción.
 * Misma validación en el backend (`crear_multiple`), este formulario solo evita el
 * viaje redondo cuando ya se sabe que se va a rechazar.
 */

import { useMemo, useState } from "react";

import { DateInput, SearchableSelect } from "@/shared/ui";

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
  // ADR-270: corrección -$10/+$10 por renglón, independiente de "monto aplicado".
  const [ajustes, setAjustes] = useState<Record<string, string>>({});

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
  // ADR-270: "Monto asignado" ahora incluye el ajuste (-$10/+$10) de cada renglón.
  const montoAsignado = seleccionadas.reduce(
    (s, f) => s + (Number(montos[f.cobranza_id]) || 0) + (Number(ajustes[f.cobranza_id]) || 0),
    0,
  );
  // Petición del usuario: contador "Ajuste" en el tablero — la suma en vivo de todos
  // los ajustes capturados (no solo lo que ya está metido dentro de "Monto asignado").
  const ajusteTotal = seleccionadas.reduce((s, f) => s + (Number(ajustes[f.cobranza_id]) || 0), 0);
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

  // ADR-270: el ajuste de CADA factura está acotado a -$10/+$10 — igual que
  // `facturaExcedida`, se deshabilita el botón EN VIVO, no solo al hacer clic.
  const ajusteFueraDeRango = seleccionadas.find(
    (f) => Math.abs(Number(ajustes[f.cobranza_id]) || 0) > 10,
  );
  const mensajeAjusteFueraDeRango = ajusteFueraDeRango
    ? `El ajuste de la factura ${ajusteFueraDeRango.numero_factura ?? "—"} debe estar entre ` +
      `-$10.00 y $10.00.`
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
    setAjustes({});
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
    // ADR-270: quitar la marca también descarta su ajuste (igual criterio que el monto).
    setAjustes((actual) => {
      if (!(cobranzaId in actual)) return actual;
      const copia = { ...actual };
      delete copia[cobranzaId];
      return copia;
    });
  };

  const cambiarMonto = (cobranzaId: string, valor: string) => {
    setMontos((actual) => ({ ...actual, [cobranzaId]: valor }));
  };

  // Bug corregido (reportado por el usuario, con captura): el campo de Ajuste no tenía
  // ninguna máscara — dejaba teclear cualquier cantidad de dígitos (el recuadro angosto
  // solo lo recortaba VISUALMENTE, pero el valor guardado seguía creciendo sin límite,
  // por eso el contador "Ajuste" del tablero llegaba a mostrar notación científica). Se
  // rechaza la tecla completa en cuanto el texto resultante ya no cabe en "-10.00" a
  // "10.00" con máximo 2 decimales — nunca se "corrige" después, así que tampoco hay
  // redondeo: lo que se ve es exactamente lo que se guarda.
  const esAjusteParcialValido = (texto: string): boolean => {
    if (texto === "" || texto === "-") return true;
    if (!/^-?\d{0,2}(\.\d{0,2})?$/.test(texto)) return false;
    const n = Number(texto);
    return !Number.isNaN(n) && n >= -10 && n <= 10;
  };

  const cambiarAjuste = (cobranzaId: string, valor: string) => {
    if (!esAjusteParcialValido(valor)) return;
    setAjustes((actual) => ({ ...actual, [cobranzaId]: valor }));
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
      // ADR-270: el ajuste de cada factura está acotado a -$10/+$10.
      const ajuste = Number(ajustes[f.cobranza_id]) || 0;
      if (Math.abs(ajuste) > 10) {
        setError(`El ajuste de la factura ${f.numero_factura ?? "—"} debe estar entre -$10.00 y $10.00.`);
        return;
      }
    }
    // ADR-270/272 — el pago ya no puede quedar de más ni de menos contra lo capturado:
    // "Monto asignado" (aplicado + ajuste) nunca puede exceder el total, y tampoco puede
    // quedar por debajo, sin importar la diferencia (antes, ADR-230, una diferencia
    // MAYOR a $10 se toleraba como "pago de menos"/huérfano — ya no: hay que
    // seleccionar más facturas, subir los montos, o cuadrar con la columna de Ajuste).
    const diferencia = Math.round((montoTotalNum - montoAsignado) * 100) / 100;
    if (diferencia < 0) {
      setError(
        `La suma de los montos asignados (${fmtMoneda(String(montoAsignado))}) no puede ` +
          `exceder el monto total del pago (${fmtMoneda(montoTotal)}).`,
      );
      return;
    }
    if (diferencia > 0) {
      setError(
        `El pago no cuadra exacto: falta ${fmtMoneda(String(diferencia))}. Selecciona más ` +
          `facturas, sube los montos aplicados, o usa la columna de Ajuste (hasta ±$10.00 ` +
          `por factura) para cuadrar exacto.`,
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
          ajuste: ajustes[f.cobranza_id]?.trim() ? ajustes[f.cobranza_id] : "0",
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
                quitó de aquí (ver tabla de abajo, columna "Parcialidad"). */}
            <div className="r2">
              <div>
                <div className="fl">Fecha pago</div>
                <DateInput value={fechaDeposito} onChange={setFechaDeposito} />
              </div>
              <div>
                <div className="fl fl-required">Fecha de aplicación</div>
                <DateInput value={fecha} onChange={setFecha} />
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
              {/* Petición del usuario: 4a tarjeta "Ajuste" (ancho angosto, de ~6
                  caracteres como "-10.00") con la suma en vivo de todos los ajustes
                  capturados — `gridTemplateColumns` se ajusta SOLO aquí (estilo en
                  línea), sin tocar `.mc-row` global, que reusan otras pantallas con 3
                  tarjetas. */}
              <div className="mc-row" style={{ gridTemplateColumns: "1fr 1fr 1fr auto" }}>
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
                <div className="mc" style={{ minWidth: 100 }}>
                  <div className="mc-lbl">Ajuste</div>
                  <div className="mc-val mono" style={{ width: "6ch" }}>
                    {ajusteTotal.toFixed(2)}
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
                      <th className="td-center">Fecha estimada</th>
                      <th className="td-center">Total</th>
                      <th className="td-center">Cobrado</th>
                      <th className="td-center">Pendiente</th>
                      <th className="td-center">Estado</th>
                      <th className="td-center">Parcialidad</th>
                      <th className="td-center">Monto aplicado</th>
                      <th className="td-center">Ajuste</th>
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
                          <td className="mono td-center" style={{ fontSize: 11 }}>{fmtFecha(f.fecha_estimada_cobro)}</td>
                          <td className="td-center mono">{fmtMoneda(String(totalFactura))}</td>
                          <td className="td-center mono">{oGuion(Number(f.importe_cobrado) > 0 ? fmtMoneda(f.importe_cobrado) : null)}</td>
                          <td className="td-center mono">{oGuion(Number(f.importe_pendiente_cobro) > 0 ? fmtMoneda(f.importe_pendiente_cobro) : null)}</td>
                          <td className="td-center">
                            <span className="badge">{ESTATUS_COBRO_LABEL[f.estatus_cobro]}</span>
                          </td>
                          <td className="td-center mono">{f.siguiente_numero_pago}</td>
                          <td className="td-center">
                            <input
                              className="fi mono"
                              style={{ textAlign: "right", maxWidth: 130 }}
                              inputMode="decimal"
                              disabled={!marcada}
                              value={montos[f.cobranza_id] ?? ""}
                              onChange={(e) => cambiarMonto(f.cobranza_id, e.target.value)}
                            />
                          </td>
                          <td className="td-center">
                            {/* Petición del usuario: el campo de Ajuste se ve con un
                                ancho máximo de 6 caracteres (ej. "-10.00") — el límite de
                                -$10.00/+$10.00 en sí lo valida `ajusteFueraDeRango`. */}
                            <input
                              className="fi mono"
                              // `.fi` trae `padding: 0 11px` (22px) y `box-sizing: border-box`
                              // global — sin sumarlo, "6ch" de ancho total dejaría casi sin
                              // espacio real para los 6 caracteres (ej. "-10.00").
                              style={{ textAlign: "right", width: "calc(6ch + 22px)" }}
                              inputMode="decimal"
                              disabled={!marcada}
                              value={ajustes[f.cobranza_id] ?? ""}
                              onChange={(e) => cambiarAjuste(f.cobranza_id, e.target.value)}
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
          {!mensajeExcedido && mensajeAjusteFueraDeRango && (
            <div className="state-msg error" style={{ margin: "14px 0 0", textAlign: "left" }}>
              {mensajeAjusteFueraDeRango}
            </div>
          )}
          {error && !mensajeExcedido && !mensajeAjusteFueraDeRango && (
            <div className="state-msg error" style={{ margin: "14px 0 0", textAlign: "left" }}>
              {error}
            </div>
          )}
          {crearMultiple.isError && !error && !mensajeExcedido && !mensajeAjusteFueraDeRango && (
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
          disabled={crearMultiple.isPending || !!facturaExcedida || !!ajusteFueraDeRango}
        >
          {crearMultiple.isPending ? "Guardando…" : "Registrar pago múltiple"}
        </button>
      </div>
    </>
  );
}
