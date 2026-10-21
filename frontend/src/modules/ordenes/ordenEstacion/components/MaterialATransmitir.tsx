/** "Material a Transmitir" (ADR-103): audios de una OrdenEstacion ya creada — subida
 * real a S3/local (mp3/wav/ogg, ≤ 15 MB), lista con descarga/baja. ADR-187: cada SPOT
 * recibe su propio material por posición (orden de esta lista) — ver el multi-select de
 * "Material a Transmitir" por fecha en `PeriodoTransmisionGrid.tsx`.
 *
 * Requiere un `orden_estacion_id` real (subir un audio no tiene sentido antes de
 * guardar la OE) — por eso se muestra en `OrdenEstacionDetailPanel.tsx` (el detalle, a
 * la par de los PDFs — petición del usuario tras revisar el flujo en vivo) y también en
 * `OrdenEstacionForm.tsx` cuando `oe` ya existe (edición), con su propio estado
 * independiente en cada lugar.
 *
 * ADR-211 (petición del usuario): en el detalle ya NO se permite subir material nuevo
 * desde ahí (`permitirSubir={false}`) — solo ver/descargar/quitar lo que ya existe; para
 * agregar más hay que entrar a "Editar". En el formulario de edición sigue permitido.
 *
 * ADR-213 (petición del usuario): en el detalle tampoco se permite QUITAR material
 * (`permitirQuitar={false}`) — ahí solo se ve/descarga; para eliminar uno hay que entrar
 * a "Editar". En edición sigue permitido.
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
  /** ADR-211 (petición del usuario): `false` oculta el selector de archivos para subir
   *  material nuevo — usado en el detalle de la OE (`OrdenEstacionDetailPanel.tsx`),
   *  donde ya no se permite agregar material desde ahí (solo ver/descargar/quitar). En
   *  edición (`OrdenEstacionForm.tsx`) sigue permitido — default `true`. */
  permitirSubir?: boolean;
  /** ADR-213 (petición del usuario): `false` oculta el botón "Quitar" de cada audio —
   *  mismo criterio que `permitirSubir`, usado en el detalle de la OE. En edición sigue
   *  permitido — default `true`. */
  permitirQuitar?: boolean;
}

export function MaterialATransmitir({
  ordenEstacionId,
  audios,
  onAudiosChange,
  permitirSubir = true,
  permitirQuitar = true,
}: MaterialATransmitirProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ADR-197 (petición del usuario): el selector de archivos del sistema operativo solo
  // dejaba elegir UNO a la vez (sin `multiple`, Windows no permite Ctrl/Shift-clic para
  // varios) — ahora se pueden elegir varios de un jalón; se suben uno por uno, EN
  // ORDEN (no en paralelo, `Promise.all`): el orden de subida es el que define la
  // posición de cada spot (ADR-187), así que subir en paralelo podría dejarlos en un
  // orden distinto al que el usuario los eligió. Un archivo inválido o que falla NO
  // tumba a los demás — se acumulan los errores y se siguen subiendo el resto.
  const onElegir = async (archivos: FileList | null) => {
    setError(null);
    if (!archivos || archivos.length === 0) return;

    const errores: string[] = [];
    setSubiendo(true);
    try {
      let audiosActuales = audios;
      for (const archivo of Array.from(archivos)) {
        // Validación en el front (UX inmediata) — el backend SIEMPRE revalida extensión,
        // magic bytes y tamaño; esto no la reemplaza, la anticipa.
        const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
        if (!(EXTENSIONES_AUDIO_ORDENES as readonly string[]).includes(ext)) {
          errores.push(`${archivo.name}: formato no permitido (usa ${EXTENSIONES_AUDIO_ORDENES.join(", ")}).`);
          continue;
        }
        if (archivo.size > AUDIO_ORDEN_MAX_BYTES) {
          errores.push(
            `${archivo.name}: excede el tamaño máximo permitido (${Math.round(AUDIO_ORDEN_MAX_BYTES / 1024 / 1024)} MB).`,
          );
          continue;
        }
        try {
          const dto = await subirAudioOrdenEstacionApi(ordenEstacionId, archivo);
          audiosActuales = [...audiosActuales, ordenEstacionAudioFromApi(dto)];
          onAudiosChange(audiosActuales);
        } catch (e) {
          errores.push(`${archivo.name}: ${e instanceof ApiRequestError ? e.message : "no se pudo subir"}.`);
        }
      }
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
    if (errores.length > 0) setError(errores.join(" "));
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
        Audios que se van a transmitir. Cada spot de un día recibe su material por este orden de captura
        (spot 1 → #1, spot 2 → #2…, repitiendo si hay menos materiales que spots).
      </div>

      {audios.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Sin audios subidos todavía.
        </div>
      )}
      {audios.map((audio, idx) => (
        <div key={audio.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span className="badge b-gray" style={{ fontSize: 10 }}>
            #{idx + 1}
          </span>
          <span style={{ flex: 1, fontSize: 13 }}>{audio.nombre_archivo}</span>
          <button type="button" className="btn btn-xs" onClick={() => void onDescargar(audio)}>
            Descargar
          </button>
          {permitirQuitar && (
            <button type="button" className="btn btn-xs btn-danger" onClick={() => void onEliminar(audio)}>
              Quitar
            </button>
          )}
        </div>
      ))}

      {permitirSubir && (
        <>
          <input
            ref={inputRef}
            className="file-input"
            type="file"
            multiple
            accept={AUDIO_ORDEN_ACCEPT}
            disabled={subiendo}
            onChange={(e) => void onElegir(e.target.files)}
          />
          {subiendo && (
            <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
              Subiendo…
            </span>
          )}
        </>
      )}
      {error && <div className="fe">{error}</div>}
    </div>
  );
}
