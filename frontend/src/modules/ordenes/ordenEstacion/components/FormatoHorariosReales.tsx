/** "Formato de Horarios Reales" (ADR-123): junto a "Evidencias de lo Transmitido" en
 * "Capturar Reales" — misma lista PLANA (sin `orden`/default), pero acepta CUALQUIER
 * formato (PDF, Excel, TXT, audio...) salvo ejecutables/scripts. Único componente del
 * módulo con validación de LISTA NEGRA en vez de blanca — el backend además revisa el
 * contenido real (firma de ejecutable de Windows) sin importar la extensión declarada.
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  descargarFormatoRealOrdenEstacionApi,
  eliminarFormatoRealOrdenEstacionApi,
  subirFormatoRealOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import { ordenEstacionFormatoRealFromApi } from "../../adapters/fromApi";
import { EXTENSIONES_PELIGROSAS_FORMATO_REAL, FORMATO_REAL_MAX_BYTES } from "../../constants";
import type { OrdenEstacionFormatoReal } from "../../types";

interface FormatoHorariosRealesProps {
  ordenEstacionId: string;
  formatos: OrdenEstacionFormatoReal[];
  onFormatosChange: (formatos: OrdenEstacionFormatoReal[]) => void;
}

export function FormatoHorariosReales({
  ordenEstacionId,
  formatos,
  onFormatosChange,
}: FormatoHorariosRealesProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata) — el backend SIEMPRE revalida, además del
    // contenido real (firma de ejecutable), no solo la extensión declarada.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if ((EXTENSIONES_PELIGROSAS_FORMATO_REAL as readonly string[]).includes(ext)) {
      setError(`Formato no permitido (ejecutable/script): .${ext}`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > FORMATO_REAL_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(FORMATO_REAL_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const dto = await subirFormatoRealOrdenEstacionApi(ordenEstacionId, archivo);
      onFormatosChange([...formatos, ordenEstacionFormatoRealFromApi(dto)]);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el archivo.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async (formato: OrdenEstacionFormatoReal) => {
    setError(null);
    try {
      await descargarFormatoRealOrdenEstacionApi(ordenEstacionId, formato.id, formato.nombre_archivo);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo descargar el archivo.");
    }
  };

  const onEliminar = async (formato: OrdenEstacionFormatoReal) => {
    setError(null);
    try {
      await eliminarFormatoRealOrdenEstacionApi(ordenEstacionId, formato.id);
      onFormatosChange(formatos.filter((f) => f.id !== formato.id));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo quitar el archivo.");
    }
  };

  return (
    <div className="form-card">
      <div className="form-card-title">Formato de Horarios Reales</div>
      <div className="form-card-sub">
        Cualquier formato (PDF, Excel, TXT, audio...) — no se permiten ejecutables ni scripts.
      </div>

      {formatos.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Sin archivos subidos todavía.
        </div>
      )}
      {formatos.map((formato) => (
        <div key={formato.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ flex: 1, fontSize: 13 }}>{formato.nombre_archivo}</span>
          <button type="button" className="btn btn-xs" onClick={() => void onDescargar(formato)}>
            Descargar
          </button>
          <button type="button" className="btn btn-xs btn-danger" onClick={() => void onEliminar(formato)}>
            Quitar
          </button>
        </div>
      ))}

      <input
        ref={inputRef}
        className="file-input"
        type="file"
        disabled={subiendo}
        onChange={(e) => void onElegir(e.target.files?.[0])}
      />
      {subiendo && (
        <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
          Subiendo…
        </span>
      )}
      {error && <div className="fe">{error}</div>}
    </div>
  );
}
