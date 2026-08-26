/** Registro de la respuesta del timbrador externo.
 *
 * El sistema NUNCA timbra: estos datos los DEVUELVE el PAC y aquí solo se capturan.
 *
 * El aviso sobre la OrdenCliente no es decorativo: al confirmar, el backend promueve la
 * orden a «facturada» dentro de la misma transacción (el handoff de F2), y desde esta
 * pantalla no se ve esa orden. Quien opera debe saber qué más se mueve.
 *
 * Usa el `Dialog` de PrimeReact, igual que `ConfirmDialog`: no se inventan modales.
 */

import { Button } from "primereact/button";
import { Dialog } from "primereact/dialog";
import { useState } from "react";

interface Props {
  visible: boolean;
  numeroFactura: string;
  submitting?: boolean;
  onConfirm: (data: { folio_fiscal_sat: string; fecha_timbrado: string }) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function TimbrarDialog({
  visible,
  numeroFactura,
  submitting = false,
  onConfirm,
  onCancel,
}: Props) {
  const [folio, setFolio] = useState("");
  const [fecha, setFecha] = useState(hoy());
  const [error, setError] = useState<string | null>(null);

  const confirmar = () => {
    if (!folio.trim()) {
      setError("El folio fiscal (UUID del CFDI) es obligatorio.");
      return;
    }
    onConfirm({ folio_fiscal_sat: folio.trim(), fecha_timbrado: fecha });
  };

  const footer = (
    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
      <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
        Cancelar
      </button>
      <Button label="Confirmar timbrado" loading={submitting} onClick={confirmar} />
    </div>
  );

  return (
    <Dialog
      header={`Registrar timbrado · ${numeroFactura}`}
      visible={visible}
      onHide={onCancel}
      footer={footer}
      style={{ width: 460 }}
    >
      <p style={{ fontSize: 13, color: "var(--text2)", marginTop: 0 }}>
        Captura lo que devolvió el timbrador externo. Al confirmar, la orden asociada pasará
        a <strong>facturada</strong>.
      </p>

      <div className="fg">
        <label className="fl" htmlFor="folio_fiscal_sat">
          Folio fiscal (UUID del CFDI) <span className="req">*</span>
        </label>
        <input
          id="folio_fiscal_sat"
          className="in mono"
          value={folio}
          onChange={(e) => {
            setFolio(e.target.value);
            setError(null);
          }}
        />
      </div>

      <div className="fg">
        <label className="fl" htmlFor="fecha_timbrado">
          Fecha de timbrado <span className="req">*</span>
        </label>
        <input
          id="fecha_timbrado"
          type="date"
          className="in"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
      </div>

      {error && <div className="state-msg error">{error}</div>}
    </Dialog>
  );
}
