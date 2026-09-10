/** Alta de MovimientoBancario (F3) — captura manual de Tesorería (canal dedicado,
 * ADR-069): el permiso del router es `pagos:leer` (nivel que Tesorería ya tenía como
 * lectora); el servicio exige `área in (TESORERIA, ADMIN)` y devuelve 403 a cualquier
 * otra área. El botón no se oculta por área (el front no conoce la matriz), solo lleva
 * un hint.
 *
 * Sin carga de archivo por lote en esta versión (`ExtractoBancarioPort` no se construyó,
 * ver ficha del módulo): esto es SIEMPRE un movimiento a la vez.
 */

import { useState } from "react";

import { AdjuntoCobranzaInput } from "../../cobranzaFactura/components/AdjuntoCobranzaInput";
import type { MovimientoBancarioCreate, TipoMovimiento } from "../../types";

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: MovimientoBancarioCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function MovimientoBancarioForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const [fecha, setFecha] = useState(hoy());
  const [tipo, setTipo] = useState<TipoMovimiento>("abono");
  const [monto, setMonto] = useState("");
  const [referencia, setReferencia] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [archivoPath, setArchivoPath] = useState<string | null>(null);
  const [archivoNombre, setArchivoNombre] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confirmar = () => {
    const montoNum = Number(monto);
    if (!monto || Number.isNaN(montoNum) || montoNum <= 0) {
      setError("Captura el monto del movimiento.");
      return;
    }
    setError(null);
    onSubmit({
      fecha_movimiento: fecha,
      tipo_movimiento: tipo,
      monto_movimiento: monto,
      referencia_bancaria: referencia.trim() || null,
      descripcion_movimiento: descripcion.trim() || null,
      archivo_path: archivoPath,
      archivo_nombre: archivoNombre,
    });
  };

  return (
    <>
      <div className="dh">
        <div className="dh-name">Nuevo movimiento bancario</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="r2">
            <div>
              <div className="fl fl-required">Fecha del movimiento</div>
              <input type="date" className="fi" value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </div>
            <div>
              <div className="fl fl-required">Tipo</div>
              <select className="fsel" value={tipo} onChange={(e) => setTipo(e.target.value as TipoMovimiento)}>
                <option value="abono">Abono (entrada)</option>
                <option value="cargo">Cargo (salida)</option>
              </select>
            </div>
          </div>
          <div className="fl fl-required">Monto</div>
          <input
            className="fi"
            inputMode="decimal"
            value={monto}
            onChange={(e) => {
              setMonto(e.target.value);
              setError(null);
            }}
          />
          <div className="r2">
            <div>
              <div className="fl">Referencia bancaria</div>
              <input
                className="fi"
                placeholder="SPEI-XXXXXXXX / TRANS-XXXXXX"
                value={referencia}
                onChange={(e) => setReferencia(e.target.value)}
              />
            </div>
            <div>
              <div className="fl">Descripción / concepto</div>
              <input className="fi" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
            </div>
          </div>
          <div className="fl">Estado de cuenta (soporte)</div>
          <AdjuntoCobranzaInput
            tipo="estado_cuenta"
            placeholder="Cargar estado de cuenta"
            value={archivoPath}
            onChange={(ref) => {
              setArchivoPath(ref);
              setArchivoNombre(ref.split("/").pop() ?? ref);
            }}
          />
          {error && <div className="fe">{error}</div>}
        </div>

        {submitError && <div className="state-msg error">{submitError}</div>}
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-sm btn-phase"
          onClick={confirmar}
          disabled={submitting}
          title="Solo Tesorería o Admin pueden capturar movimientos bancarios"
        >
          Guardar
        </button>
      </div>
    </>
  );
}
