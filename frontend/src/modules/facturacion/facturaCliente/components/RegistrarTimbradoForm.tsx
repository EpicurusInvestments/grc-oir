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
 *
 * ADR-248 (petición del usuario, "NEW FEATURE"): checkbox "Facturado en sistema
 * externo" — solo IDENTIFICA la factura (p.ej. cuando en realidad se facturó en OIR),
 * el resto del flujo sigue tal cual: el monto para OIR es el que ya se calculó en este
 * sistema (`total_factura`), nunca el del folio/archivo cargado aquí.
 */

import { useState } from "react";

import { DateInput } from "@/shared/ui";

import { AdjuntoFacturaInput } from "./AdjuntoFacturaInput";
import type { TimbrarInput } from "../../types";

// ADR-269 (petición del usuario, con captura): valida la FORMA del folio fiscal
// (8-4-4-4-12 hexadecimal con guiones) — antes solo se exigía "no vacío", así que
// cualquier texto pasaba como folio fiscal. No exige estrictamente UUID v4 (el nibble
// de versión): no todos los PAC lo respetan, y lo que importa aquí es no capturar
// basura por error de dedo. Mismo patrón que el backend (`FOLIO_FISCAL_REGEX` en
// `factura_cliente.py`).
const FOLIO_FISCAL_REGEX = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/** Petición del usuario: ayuda a teclear el folio insertando los guiones solo, y a la
 * vez deja pegar un folio completo (con o sin guiones, copiado de la factura externa)
 * sin que le "estorben" los guiones — se descarta todo lo que no sea hexadecimal y se
 * reinsertan los guiones en las posiciones 8-4-4-4-12, así que tanto teclear carácter
 * por carácter como pegar de golpe terminan en el mismo resultado canónico. */
function aplicarMascaraFolio(crudo: string): string {
  const hex = crudo.replace(/[^0-9a-fA-F]/g, "").slice(0, 32);
  const partes = [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20, 32)];
  return partes.filter((p) => p !== "").join("-");
}

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
  // ADR-248 (petición del usuario, "NEW FEATURE"): solo identifica la factura — el
  // resto del flujo (el monto para OIR) sigue tal cual, viene de este sistema.
  const [facturadoExterno, setFacturadoExterno] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bug corregido (petición del usuario, con captura): el error de formato solo se
  // veía hasta dar clic en "Registrar timbrado" — si alguien tecleaba un folio mal
  // formado y no intentaba guardar todavía, no había ninguna señal. Ahora se avisa en
  // cuanto se sale del campo (`onBlur`), sin nagguear mientras todavía está escribiendo
  // (`onChange` sigue limpiando el error en cada tecla, como ya hacía).
  const validarFolioAlSalir = () => {
    const folioLimpio = folio.trim();
    if (!folioLimpio || FOLIO_FISCAL_REGEX.test(folioLimpio)) return;
    setError(
      "El folio fiscal debe ser un UUID válido (8-4-4-4-12 caracteres hexadecimales, " +
        "ej. A1B2C3D4-E5F6-7890-ABCD-EF1234567890).",
    );
  };

  const confirmar = () => {
    const folioLimpio = folio.trim();
    if (!folioLimpio) {
      setError("El folio fiscal (UUID del CFDI) es obligatorio.");
      return;
    }
    if (!FOLIO_FISCAL_REGEX.test(folioLimpio)) {
      setError(
        "El folio fiscal debe ser un UUID válido (8-4-4-4-12 caracteres hexadecimales, " +
          "ej. A1B2C3D4-E5F6-7890-ABCD-EF1234567890).",
      );
      return;
    }
    onConfirm({
      folio_fiscal_sat: folioLimpio,
      fecha_timbrado: fecha,
      serie_timbrado: serie.trim() || null,
      xml_path: xmlPath,
      pdf_path: pdfPath,
      facturado_en_sistema_externo: facturadoExterno,
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
                setFolio(aplicarMascaraFolio(e.target.value));
                setError(null);
              }}
              onBlur={validarFolioAlSalir}
            />
            <div className="r2">
              <div>
                <div className="fl fl-required">Fecha de timbrado</div>
                <DateInput value={fecha} onChange={setFecha} />
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
            <label className="check-box" style={{ marginTop: 10, marginBottom: 0 }}>
              <input
                type="checkbox"
                checked={facturadoExterno}
                onChange={(e) => setFacturadoExterno(e.target.checked)}
              />
              <div className="check-box-title">Facturado en sistema externo</div>
            </label>
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
