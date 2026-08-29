/** Registro de la respuesta del timbrador externo — pantalla completa, mismo patrón que
 * el resto de los formularios largos del sistema (`cat-header` + tarjetas de sección).
 *
 * El sistema NUNCA timbra: estos datos los DEVUELVE el PAC y aquí solo se capturan. Al
 * confirmar, el backend promueve la orden asociada a «facturada» dentro de la misma
 * transacción (el handoff de F2, ADR-047) — el aviso no es decorativo: desde esta
 * pantalla no se ve esa orden, así que quien opera debe saber qué más se mueve.
 *
 * XML y PDF son OPCIONALES (igual que hoy en `TimbrarInput`): el prototipo aprobado los
 * marca como obligatorios, pero endurecer esa regla es una decisión de negocio aparte —
 * aquí solo se habilita la carga real (antes ni siquiera existían estos 2 campos).
 */

import { useState } from "react";

import { AdjuntoFacturaInput } from "./AdjuntoFacturaInput";
import type { TimbrarInput } from "../../types";

interface Props {
  numeroFactura: string;
  submitting?: boolean;
  /** Error del intento anterior (p.ej. rechazo del backend) — distinto del error de
   * validación local ("folio obligatorio"), que se maneja dentro del propio formulario. */
  submitError?: string | null;
  onConfirm: (data: TimbrarInput) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function RegistrarTimbradoForm({
  numeroFactura,
  submitting = false,
  submitError,
  onConfirm,
  onCancel,
}: Props) {
  const [folio, setFolio] = useState("");
  const [fecha, setFecha] = useState(hoy());
  const [serie, setSerie] = useState("");
  const [xmlPath, setXmlPath] = useState<string | null>(null);
  const [pdfPath, setPdfPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confirmar = () => {
    if (!folio.trim()) {
      setError("El folio fiscal (UUID del CFDI) es obligatorio.");
      return;
    }
    onConfirm({
      folio_fiscal_sat: folio.trim(),
      fecha_timbrado: fecha,
      serie_timbrado: serie.trim() || null,
      xml_path: xmlPath,
      pdf_path: pdfPath,
    });
  };

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Registrar respuesta del timbrado</div>
          <div className="cat-sub">
            Factura <strong>{numeroFactura}</strong>. Captura los datos que recibiste del sistema
            externo de timbrado. Al confirmar, la orden asociada pasará a <strong>facturada</strong>.
          </div>
        </div>
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          ← Cancelar
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          <div className="info-banner">
            <div className="info-banner-title">📄 Datos recibidos del sistema externo de timbrado</div>
            <div className="info-banner-msg">
              Captura el folio fiscal (UUID del SAT), la fecha de timbrado, y carga los archivos
              XML y PDF que regresa el timbrador.
            </div>
          </div>

          <div className="form-card">
            <div className="fl fl-required">Folio fiscal SAT (UUID)</div>
            <input
              className="fi"
              style={{ fontFamily: "var(--mono)", fontSize: 12 }}
              placeholder="A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
              value={folio}
              onChange={(e) => {
                setFolio(e.target.value);
                setError(null);
              }}
            />
            <div className="r2">
              <div>
                <div className="fl fl-required">Fecha de timbrado</div>
                <input
                  type="date"
                  className="fi"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </div>
              <div>
                <div className="fl">Serie / certificado (opcional)</div>
                <input
                  className="fi"
                  placeholder="Serie de timbrado"
                  value={serie}
                  onChange={(e) => setSerie(e.target.value)}
                />
              </div>
            </div>
            <div className="r2">
              <div>
                <div className="fl">Archivo XML</div>
                <AdjuntoFacturaInput
                  tipo="cfdi_xml"
                  placeholder="Cargar XML del CFDI"
                  value={xmlPath}
                  onChange={setXmlPath}
                />
              </div>
              <div>
                <div className="fl">Archivo PDF</div>
                <AdjuntoFacturaInput
                  tipo="cfdi_pdf"
                  placeholder="Cargar PDF de la factura"
                  value={pdfPath}
                  onChange={setPdfPath}
                />
              </div>
            </div>
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
        <button type="button" className="btn btn-sm btn-primary" onClick={confirmar} disabled={submitting}>
          {submitting ? "Guardando…" : "Registrar timbrado"}
        </button>
      </div>
    </>
  );
}
