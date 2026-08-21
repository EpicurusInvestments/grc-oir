/** Input de adjunto de orden (ODC, carta de conciliación, reporte de afiliado): reemplaza
 * el placeholder "simulado" (solo capturaba el nombre) por una subida real al backend
 * (S3/local vía `AlmacenamientoPort` — ver `adapters/adjuntosApi.ts`). Un solo archivo por
 * campo; un nuevo archivo REEMPLAZA la referencia anterior (no se borra el anterior en el
 * almacenamiento — solo deja de estar referenciado).
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  nombreDeAdjuntoRef,
  subirAdjuntoOrden,
  verAdjuntoOrden,
  type TipoAdjuntoOrden,
} from "../adapters/adjuntosApi";
import { ADJUNTO_ORDEN_ACCEPT, ADJUNTO_ORDEN_MAX_BYTES, EXTENSIONES_ADJUNTO_ORDENES } from "../constants";

interface AdjuntoOrdenInputProps {
  tipo: TipoAdjuntoOrden;
  value: string | null | undefined;
  onChange: (ref: string) => void;
  disabled?: boolean;
}

export function AdjuntoOrdenInput({ tipo, value, onChange, disabled }: AdjuntoOrdenInputProps) {
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
    if (!(EXTENSIONES_ADJUNTO_ORDENES as readonly string[]).includes(ext)) {
      setError(`Extensión no permitida. Usa: ${EXTENSIONES_ADJUNTO_ORDENES.join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > ADJUNTO_ORDEN_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(ADJUNTO_ORDEN_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const { ref } = await subirAdjuntoOrden(tipo, archivo);
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
      await verAdjuntoOrden(value);
    } catch (e) {
      setVerError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el documento.");
    }
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={ADJUNTO_ORDEN_ACCEPT}
        disabled={disabled || subiendo}
        onChange={(e) => void onElegir(e.target.files?.[0])}
      />
      {subiendo && (
        <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
          Subiendo…
        </span>
      )}
      {!subiendo && value && (
        <div style={{ marginTop: 4 }}>
          <button type="button" className="btn btn-sm" onClick={() => void onVer()}>
            Descargar: {nombreDeAdjuntoRef(value)}
          </button>
        </div>
      )}
      {error && <div className="fe">{error}</div>}
      {verError && <div className="fe">{verError}</div>}
    </div>
  );
}
