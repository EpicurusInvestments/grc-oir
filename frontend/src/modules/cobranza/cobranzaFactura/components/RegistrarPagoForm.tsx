/** Registro de un pago del cliente — pantalla completa, mismo patrón que
 * `facturacion/facturaCliente/components/RegistrarTimbradoForm.tsx` (`cat-header` +
 * tarjetas de sección, validación manual en vez de RHF/Zod: aquí el único campo con una
 * regla no trivial es el tope de `monto_aplicado` contra el pendiente, más simple de
 * expresar así que con un resolver).
 *
 * `archivo_path`/`archivo_nombre` son OPCIONALES en el backend (`PagoClienteCreate`): el
 * comprobante ayuda a la conciliación pero no la bloquea si CxC lo sube después.
 *
 * No hay campo de "notas": el mockup aprobado tiene un textarea de observaciones, pero
 * `PagoCliente` no tiene una columna para guardarlas — agregarlo aquí sería una promesa
 * de guardado que el backend no cumple.
 */

import { useState } from "react";

import { fmtMoneda } from "../../format";
import { useMetodosDePago } from "../../hooks";
import type { CobranzaFactura, PagoClienteCreate } from "../../types";
import { AdjuntoCobranzaInput } from "./AdjuntoCobranzaInput";

interface Props {
  cobranza: CobranzaFactura;
  numeroFactura: string;
  anunciante: string;
  submitting?: boolean;
  submitError?: string | null;
  onConfirm: (data: PagoClienteCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function RegistrarPagoForm({
  cobranza,
  numeroFactura,
  anunciante,
  submitting = false,
  submitError,
  onConfirm,
  onCancel,
}: Props) {
  const metodosPago = useMetodosDePago();
  const pendiente = Number(cobranza.importe_pendiente_cobro);

  const [fecha, setFecha] = useState(hoy());
  const [monto, setMonto] = useState("");
  const [metodoPago, setMetodoPago] = useState("");
  const [referencia, setReferencia] = useState("");
  const [archivoPath, setArchivoPath] = useState<string | null>(null);
  const [archivoNombre, setArchivoNombre] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confirmar = () => {
    const montoNum = Number(monto);
    if (!monto || Number.isNaN(montoNum) || montoNum <= 0) {
      setError("Captura el monto del pago.");
      return;
    }
    if (montoNum > pendiente) {
      setError(`El monto excede el saldo pendiente (${fmtMoneda(cobranza.importe_pendiente_cobro)}).`);
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
    onConfirm({
      fecha_pago_cliente: fecha,
      monto_aplicado: monto,
      metodo_pago_clave: metodoPago,
      referencia_pago: referencia.trim(),
      archivo_path: archivoPath,
      archivo_nombre: archivoNombre,
    });
  };

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Registrar pago del cliente</div>
          <div className="cat-sub">
            Factura <strong>{numeroFactura}</strong> · {anunciante} · Pendiente:{" "}
            {fmtMoneda(cobranza.importe_pendiente_cobro)}
          </div>
        </div>
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          ← Cancelar
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <div className="heredado-block">
            <div className="heredado-title">Resumen de la cobranza</div>
            <div className="heredado-grid">
              <div className="heredado-row">
                <span className="heredado-lbl">Factura</span>
                <span className="heredado-val mono">{numeroFactura}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">Total factura</span>
                <span className="heredado-val mono">{fmtMoneda(cobranza.importe_pendiente_cobro)}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">Ya cobrado</span>
                <span className="heredado-val mono">{fmtMoneda(cobranza.importe_cobrado)}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">Pendiente</span>
                <span className="heredado-val mono" style={{ fontWeight: 600 }}>
                  {fmtMoneda(cobranza.importe_pendiente_cobro)}
                </span>
              </div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Datos del pago recibido</div>
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
                  placeholder={pendiente.toFixed(2)}
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
                <div className="fl fl-required">Referencia bancaria / cheque</div>
                <input
                  className="fi"
                  placeholder="SPEI-XXXXXXXX / CHE-XXXXXX"
                  value={referencia}
                  onChange={(e) => setReferencia(e.target.value)}
                />
              </div>
            </div>
            <div className="fl">Comprobante (PDF, imagen)</div>
            <AdjuntoCobranzaInput
              tipo="comprobante_pago"
              placeholder="Cargar comprobante"
              value={archivoPath}
              onChange={(ref) => {
                setArchivoPath(ref);
                setArchivoNombre(ref.split("/").pop() ?? ref);
              }}
            />
            {error && <div className="fe">{error}</div>}
          </div>

          {submitError && (
            <div className="state-msg error" style={{ margin: "0 0 14px", textAlign: "left" }}>
              {submitError}
            </div>
          )}
        </div>
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="button" className="btn btn-sm btn-phase" onClick={confirmar} disabled={submitting}>
          {submitting ? "Guardando…" : "Registrar pago"}
        </button>
      </div>
    </>
  );
}
