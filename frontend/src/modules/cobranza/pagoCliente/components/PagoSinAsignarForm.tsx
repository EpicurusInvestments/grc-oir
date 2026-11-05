/** ADR-229 (petición del usuario): captura un pago recibido SIN elegir factura
 * todavía — mismos campos que `RegistrarPagoForm.tsx` MENOS "Número de pago" (la
 * parcialidad no aplica sin una factura concreta) y sin el tope de monto contra un
 * pendiente (no hay factura de la que leerlo). Se asigna después desde el detalle de
 * "Pagos recibidos" (`AsignarFacturaPanel.tsx`).
 */

import { useState } from "react";

import { useCuentasContables, useFormasDePago, useMetodosDePago } from "../../hooks";
import type { PagoClienteCreate } from "../../types";

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onConfirm: (data: PagoClienteCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function PagoSinAsignarForm({ submitting = false, submitError, onConfirm, onCancel }: Props) {
  const metodosPago = useMetodosDePago();
  const formasPago = useFormasDePago();
  const cuentasContables = useCuentasContables();

  const [fecha, setFecha] = useState(hoy());
  const [monto, setMonto] = useState("");
  const [metodoPago, setMetodoPago] = useState("");
  const [referencia, setReferencia] = useState("");
  const [formaPago, setFormaPago] = useState("");
  const [fechaDeposito, setFechaDeposito] = useState("");
  const [cuentaContable, setCuentaContable] = useState("");
  const [error, setError] = useState<string | null>(null);

  const montoNum = Number(monto);
  const camposCompletos =
    fecha.trim() !== "" &&
    monto.trim() !== "" &&
    !Number.isNaN(montoNum) &&
    montoNum > 0 &&
    metodoPago !== "" &&
    referencia.trim() !== "" &&
    formaPago !== "" &&
    cuentaContable !== "";

  const confirmar = () => {
    if (!monto || Number.isNaN(montoNum) || montoNum <= 0) {
      setError("Captura el monto del pago.");
      return;
    }
    if (!metodoPago) {
      setError("Selecciona el método de pago.");
      return;
    }
    if (!referencia.trim()) {
      setError("Captura la referencia bancaria o del cheque.");
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
    onConfirm({
      fecha_pago_cliente: fecha,
      monto_aplicado: monto,
      metodo_pago_clave: metodoPago,
      referencia_pago: referencia.trim(),
      forma_pago_clave: formaPago,
      fecha_deposito: fechaDeposito || null,
      cuenta_contable_id: cuentaContable,
    });
  };

  return (
    <>
      <div className="dh">
        <div className="dh-name">Pago sin asignar</div>
        <div className="dh-sub">Se podrá asignar a una factura después, desde el detalle.</div>
      </div>
      <div className="db">
        <div className="form-card">
          <div className="r2">
            <div>
              <div className="fl fl-required">Fecha del pago</div>
              <input
                type="date"
                className="fi"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
            <div>
              <div className="fl fl-required">Monto aplicado</div>
              <input
                className="fi"
                inputMode="decimal"
                placeholder="0.00"
                value={monto}
                onChange={(e) => {
                  setMonto(e.target.value);
                  setError(null);
                }}
              />
            </div>
          </div>
          <div className="r2">
            <div>
              <div className="fl fl-required">Método de pago</div>
              <select
                className="fsel"
                value={metodoPago}
                onChange={(e) => setMetodoPago(e.target.value)}
              >
                <option value="">— Selecciona —</option>
                {(metodosPago.data ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.etiqueta}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="fl fl-required">Referencia bancaria</div>
              <input
                className="fi"
                placeholder="SPEI-XXXXX / CHE-XXXX"
                value={referencia}
                onChange={(e) => setReferencia(e.target.value)}
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
          <div className="fl">Fecha de depósito</div>
          <input
            type="date"
            className="fi"
            style={{ maxWidth: 260 }}
            value={fechaDeposito}
            onChange={(e) => setFechaDeposito(e.target.value)}
          />
          {error && <div className="fe">{error}</div>}
        </div>
        {submitError && (
          <div className="state-msg error" style={{ textAlign: "left" }}>
            {submitError}
          </div>
        )}
      </div>
      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-sm btn-phase"
          onClick={confirmar}
          disabled={submitting || !camposCompletos}
        >
          {submitting ? "Guardando…" : "Registrar pago sin asignar"}
        </button>
      </div>
    </>
  );
}
