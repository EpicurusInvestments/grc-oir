/** Input de adjunto de Facturación (XML/PDF del CFDI timbrado): mismo patrón que
 * `ordenes/components/AdjuntoOrdenInput.tsx` (ADR-042) — subida real al backend
 * (S3/local vía `AlmacenamientoPort`). Un solo archivo por campo; uno nuevo reemplaza la
 * referencia anterior (no se borra el anterior en el almacenamiento, solo deja de estar
 * referenciado).
 *
 * A diferencia de `AdjuntoOrdenInput` (input nativo visible), aquí toda la caja punteada
 * es clickeable (`<label>` envolviendo un `<input type="file">` oculto) — mismo look que
 * "Cargar XML del CFDI"/"Cargar PDF de la factura" del prototipo aprobado, pero con
 * subida real en vez de una caja decorativa sin función (ADR-051).
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  adjuntosFacturacionApi,
  nombreDeAdjuntoFacturacionRef,
  type TipoAdjuntoFacturacion,
} from "../../api";
import { ADJUNTO_FACTURACION_ACCEPT, ADJUNTO_FACTURACION_MAX_BYTES, EXTENSIONES_ADJUNTO_FACTURACION } from "../../constants";

interface AdjuntoFacturaInputProps {
  tipo: TipoAdjuntoFacturacion;
  /** Texto de la caja vacía, p.ej. "Cargar XML del CFDI". */
  placeholder: string;
  value: string | null | undefined;
  onChange: (ref: string) => void;
  disabled?: boolean;
}

export function AdjuntoFacturaInput({
  tipo,
  placeholder,
  value,
  onChange,
  disabled,
}: AdjuntoFacturaInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verError, setVerError] = useState<string | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata): el backend SIEMPRE revalida extensión,
    // magic bytes y tamaño — esto no reemplaza esa validación, la anticipa.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(EXTENSIONES_ADJUNTO_FACTURACION as readonly string[]).includes(ext)) {
      setError(`Extensión no permitida. Usa: ${EXTENSIONES_ADJUNTO_FACTURACION.join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > ADJUNTO_FACTURACION_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(ADJUNTO_FACTURACION_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const { ref } = await adjuntosFacturacionApi.subir(tipo, archivo);
      onChange(ref);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el archivo.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onVer = async () => {
    if (!value) return;
    setVerError(null);
    try {
      await adjuntosFacturacionApi.ver(value);
    } catch (e) {
      setVerError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el documento.");
    }
  };

  return (
    <div>
      <label className={`dropzone${value ? " has-file" : ""}`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          <path d="M7 2v6M4 5l3-3 3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {subiendo ? "Subiendo…" : value ? nombreDeAdjuntoFacturacionRef(value) : placeholder}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={ADJUNTO_FACTURACION_ACCEPT}
          disabled={disabled || subiendo}
          onChange={(e) => void onElegir(e.target.files?.[0])}
        />
      </label>
      {!subiendo && value && (
        <button type="button" className="btn btn-sm" onClick={() => void onVer()}>
          Descargar
        </button>
      )}
      {error && <div className="fe">{error}</div>}
      {verError && <div className="fe">{verError}</div>}
    </div>
  );
}
