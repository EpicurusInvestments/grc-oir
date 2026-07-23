/** Sección de adjuntos (PDF) del panel de detalle del Contrato.
 *
 * Reemplaza el placeholder de "subida diferida" (ADR-020) por la integración real
 * (ADR-027): listar, subir (multi-PDF con validación tipo/tamaño en el front), ver/descargar
 * y borrar. El bucket es PRIVADO: la descarga pasa por el backend (blob con auth), nunca por
 * URL pública. Subir/borrar solo para usuarios con permiso de escritura (`canWrite`).
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import { useAdjuntosContrato } from "../hooks";
import { ADJUNTO_MAX_BYTES, type Contrato } from "../types";

const fmtTamano = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const esPdf = (f: File): boolean =>
  f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

interface ContratoAdjuntosProps {
  contrato: Contrato;
  canWrite: boolean;
}

export function ContratoAdjuntos({ contrato, canWrite }: ContratoAdjuntosProps) {
  const { listar, subir, borrar, ver } = useAdjuntosContrato(contrato.contrato_id);
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [verError, setVerError] = useState<string | null>(null);

  const adjuntos = listar.data ?? [];

  const onElegirArchivos = async (files: FileList | null) => {
    setError(null);
    if (!files || files.length === 0) return;

    // Validación en el front (el backend revalida): solo PDF, dentro del tamaño máximo.
    for (const f of Array.from(files)) {
      if (!esPdf(f)) {
        setError(`«${f.name}» no es un PDF.`);
        return;
      }
      if (f.size > ADJUNTO_MAX_BYTES) {
        setError(`«${f.name}» excede el máximo de ${fmtTamano(ADJUNTO_MAX_BYTES)}.`);
        return;
      }
    }

    // Sube secuencialmente para reportar el error del archivo concreto que falle.
    for (const f of Array.from(files)) {
      try {
        await subir.mutateAsync(f);
      } catch (e) {
        setError(e instanceof ApiRequestError ? e.message : `No se pudo subir «${f.name}».`);
        break;
      }
    }
    if (inputRef.current) inputRef.current.value = ""; // permite re-elegir el mismo archivo
  };

  const onVer = async (nombre: string) => {
    setVerError(null);
    try {
      await ver(nombre);
    } catch (e) {
      setVerError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el documento.");
    }
  };

  const onBorrar = async (nombre: string) => {
    setError(null);
    if (!window.confirm(`¿Eliminar el adjunto «${nombre}»?`)) return;
    try {
      await borrar.mutateAsync(nombre);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo eliminar el documento.");
    }
  };

  const subiendo = subir.isPending;

  return (
    <>
      <div className="sec">Adjuntos del contrato</div>

      {canWrite && (
        <div style={{ marginBottom: 8 }}>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            style={{ display: "none" }}
            onChange={(e) => void onElegirArchivos(e.target.files)}
          />
          <button
            type="button"
            className="btn btn-sm"
            disabled={subiendo}
            onClick={() => inputRef.current?.click()}
          >
            {subiendo ? "Subiendo…" : "Subir PDF"}
          </button>
          <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
            Solo PDF · máx. {fmtTamano(ADJUNTO_MAX_BYTES)}. Un nombre repetido reemplaza el
            archivo.
          </span>
        </div>
      )}

      {error && (
        <div className="state-msg error" style={{ textAlign: "left", marginBottom: 8 }}>
          {error}
        </div>
      )}

      {listar.isLoading && <div className="state-msg">Cargando adjuntos…</div>}
      {listar.isError && <div className="state-msg error">No se pudieron cargar los adjuntos.</div>}
      {!listar.isLoading && !listar.isError && adjuntos.length === 0 && (
        <div className="fv muted">Sin adjuntos.</div>
      )}

      {adjuntos.map((a) => (
        <div className="rel-item" key={a.nombre}>
          <div>
            <div className="rel-name mono">{a.nombre}</div>
            <div className="rel-sub">{fmtTamano(a.tamano_bytes)}</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" className="btn btn-sm" onClick={() => void onVer(a.nombre)}>
              Ver
            </button>
            {canWrite && (
              <button
                type="button"
                className="btn btn-sm btn-danger"
                disabled={borrar.isPending}
                onClick={() => void onBorrar(a.nombre)}
              >
                Borrar
              </button>
            )}
          </div>
        </div>
      ))}

      {verError && (
        <div className="state-msg error" style={{ textAlign: "left", marginTop: 8 }}>
          {verError}
        </div>
      )}
    </>
  );
}
