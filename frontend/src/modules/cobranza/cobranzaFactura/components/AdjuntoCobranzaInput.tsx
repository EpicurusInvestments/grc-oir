/** Input de adjunto de Cobranza (comprobante de pago / estado de cuenta): mismo patrón
 * clickeable que `facturacion/facturaCliente/components/AdjuntoFacturaInput.tsx` — toda
 * la caja punteada es un `<label>` que envuelve un `<input type="file">` oculto, con
 * subida real al backend (S3/local vía `AlmacenamientoPort`).
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import { adjuntosCobranzaApi, nombreDeAdjuntoCobranzaRef, type TipoAdjuntoCobranza } from "../../api";
import {
  ADJUNTO_COBRANZA_ACCEPT,
  ADJUNTO_COBRANZA_MAX_BYTES,
  EXTENSIONES_ADJUNTO_COBRANZA,
} from "../../constants";

interface AdjuntoCobranzaInputProps {
  tipo: TipoAdjuntoCobranza;
  /** Texto de la caja vacía, p.ej. "Cargar comprobante". */
  placeholder: string;
  value: string | null | undefined;
  onChange: (ref: string) => void;
  disabled?: boolean;
}

export function AdjuntoCobranzaInput({
  tipo,
  placeholder,
  value,
  onChange,
  disabled,
}: AdjuntoCobranzaInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verError, setVerError] = useState<string | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata): el backend SIEMPRE revalida extensión,
    // magic bytes y tamaño — esto no la reemplaza, la anticipa.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(EXTENSIONES_ADJUNTO_COBRANZA as readonly string[]).includes(ext)) {
      setError(`Extensión no permitida. Usa: ${EXTENSIONES_ADJUNTO_COBRANZA.join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > ADJUNTO_COBRANZA_MAX_BYTES) {
      setError(
        `El archivo excede el tamaño máximo permitido (${Math.round(ADJUNTO_COBRANZA_MAX_BYTES / 1024 / 1024)} MB).`,
      );
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const { ref } = await adjuntosCobranzaApi.subir(tipo, archivo);
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
      await adjuntosCobranzaApi.ver(value);
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
          {subiendo ? "Subiendo…" : value ? nombreDeAdjuntoCobranzaRef(value) : placeholder}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={ADJUNTO_COBRANZA_ACCEPT}
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
