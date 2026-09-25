/** "Material a Transmitir" (ADR-103): audios de una OrdenEstacion ya creada — subida
 * real a S3/local (mp3/wav/ogg, ≤ 15 MB), lista con descarga/baja. El PRIMERO de la
 * lista es el DEFAULT que usan los días sin asignación propia (ver el selector de
 * audio por día en `PeriodoTransmisionGrid.tsx`).
 *
 * Requiere un `orden_estacion_id` real (subir un audio no tiene sentido antes de
 * guardar la OE) — por eso se muestra en `OrdenEstacionDetailPanel.tsx` (el detalle, a
 * la par de los PDFs — petición del usuario tras revisar el flujo en vivo) y también en
 * `OrdenEstacionForm.tsx` cuando `oe` ya existe (edición), con su propio estado
 * independiente en cada lugar.
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  descargarAudioOrdenEstacionApi,
  eliminarAudioOrdenEstacionApi,
  listarAudiosOrdenEstacionApi,
  subirAudioOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import { ordenEstacionAudioFromApi } from "../../adapters/fromApi";
import { AUDIO_ORDEN_ACCEPT, AUDIO_ORDEN_MAX_BYTES, EXTENSIONES_AUDIO_ORDENES } from "../../constants";
import type { OrdenEstacionAudio } from "../../types";

interface MaterialATransmitirProps {
  ordenEstacionId: string;
  audios: OrdenEstacionAudio[];
  onAudiosChange: (audios: OrdenEstacionAudio[]) => void;
}

export function MaterialATransmitir({ ordenEstacionId, audios, onAudiosChange }: MaterialATransmitirProps) {
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
      const dto = await subirAudioOrdenEstacionApi(ordenEstacionId, archivo);
      onAudiosChange([...audios, ordenEstacionAudioFromApi(dto)]);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el audio.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async (audio: OrdenEstacionAudio) => {
    setError(null);
    try {
      await descargarAudioOrdenEstacionApi(ordenEstacionId, audio.id, audio.nombre_archivo);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo descargar el audio.");
    }
  };

  const onEliminar = async (audio: OrdenEstacionAudio) => {
    setError(null);
    try {
      await eliminarAudioOrdenEstacionApi(ordenEstacionId, audio.id);
      // El backend renumera los que quedan (el nuevo primero pasa a ser el default) —
      // se recarga la lista completa en vez de filtrar en el cliente, para reflejar
      // exactamente ese renumerado sin duplicar su lógica aquí.
      const restantes = await listarAudiosOrdenEstacionApi(ordenEstacionId);
      onAudiosChange(restantes.map(ordenEstacionAudioFromApi));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo quitar el audio.");
    }
  };

  return (
    <div className="form-card">
      <div className="form-card-title">Material a Transmitir</div>
      <div className="form-card-sub">
        Audios que se van a transmitir. El primero de la lista es el que usan los días sin una asignación propia.
      </div>

      {audios.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Sin audios subidos todavía.
        </div>
      )}
      {audios.map((audio, idx) => (
        <div key={audio.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span className={`badge ${idx === 0 ? "b-teal" : "b-gray"}`} style={{ fontSize: 10 }}>
            {idx === 0 ? "Default" : `#${idx + 1}`}
          </span>
          <span style={{ flex: 1, fontSize: 13 }}>{audio.nombre_archivo}</span>
          <button type="button" className="btn btn-xs" onClick={() => void onDescargar(audio)}>
            Descargar
          </button>
          <button type="button" className="btn btn-xs btn-danger" onClick={() => void onEliminar(audio)}>
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
