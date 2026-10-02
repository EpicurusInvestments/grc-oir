/** "Evidencias de lo Transmitido" (ADR-119): audios de una OrdenEstacion ya creada,
 * capturados libremente en "Capturar Reales" (2.2 → 2.3) — subida real a S3/local
 * (mp3/wav/ogg, ≤ 15 MB), lista con descarga/baja. Reemplaza en esa pantalla a
 * `testigos_url`/`testigos_ubicacion_alterna` (esas 2 columnas siguen existiendo en la
 * base, solo dejan de capturarse aquí).
 *
 * A diferencia de "Material a Transmitir" (`MaterialATransmitir.tsx`): lista PLANA, sin
 * concepto de "default" ni override por día — mismo patrón de subida/descarga/baja,
 * simplificado.
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  descargarEvidenciaOrdenEstacionApi,
  eliminarEvidenciaOrdenEstacionApi,
  subirEvidenciaOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import { ordenEstacionEvidenciaFromApi } from "../../adapters/fromApi";
import { AUDIO_ORDEN_ACCEPT, AUDIO_ORDEN_MAX_BYTES, EXTENSIONES_AUDIO_ORDENES } from "../../constants";
import type { OrdenEstacionEvidencia } from "../../types";

interface EvidenciasTransmitidoProps {
  ordenEstacionId: string;
  evidencias: OrdenEstacionEvidencia[];
  onEvidenciasChange: (evidencias: OrdenEstacionEvidencia[]) => void;
}

export function EvidenciasTransmitido({
  ordenEstacionId,
  evidencias,
  onEvidenciasChange,
}: EvidenciasTransmitidoProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata) — el backend SIEMPRE revalida extensión,
    // magic bytes y tamaño; esto no la reemplaza, la anticipa.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(EXTENSIONES_AUDIO_ORDENES as readonly string[]).includes(ext)) {
      setError(`Formato no permitido. Usa: ${EXTENSIONES_AUDIO_ORDENES.join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > AUDIO_ORDEN_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(AUDIO_ORDEN_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const dto = await subirEvidenciaOrdenEstacionApi(ordenEstacionId, archivo);
      onEvidenciasChange([...evidencias, ordenEstacionEvidenciaFromApi(dto)]);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir la evidencia.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async (evidencia: OrdenEstacionEvidencia) => {
    setError(null);
    try {
      await descargarEvidenciaOrdenEstacionApi(ordenEstacionId, evidencia.id, evidencia.nombre_archivo);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo descargar la evidencia.");
    }
  };

  const onEliminar = async (evidencia: OrdenEstacionEvidencia) => {
    setError(null);
    try {
      await eliminarEvidenciaOrdenEstacionApi(ordenEstacionId, evidencia.id);
      onEvidenciasChange(evidencias.filter((e) => e.id !== evidencia.id));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo quitar la evidencia.");
    }
  };

  return (
    <div className="form-card">
      <div className="form-card-title">Evidencias de lo Transmitido</div>
      <div className="form-card-sub">Audios que confirman lo realmente transmitido.</div>

      {evidencias.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Sin evidencias subidas todavía.
        </div>
      )}
      {evidencias.map((evidencia) => (
        <div key={evidencia.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ flex: 1, fontSize: 13 }}>{evidencia.nombre_archivo}</span>
          <button type="button" className="btn btn-xs" onClick={() => void onDescargar(evidencia)}>
            Descargar
          </button>
          <button type="button" className="btn btn-xs btn-danger" onClick={() => void onEliminar(evidencia)}>
            Quitar
          </button>
        </div>
      ))}

      <input
        ref={inputRef}
        className="file-input"
        type="file"
        accept={AUDIO_ORDEN_ACCEPT}
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
