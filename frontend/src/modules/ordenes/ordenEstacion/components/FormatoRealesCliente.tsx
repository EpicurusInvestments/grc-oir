/** "Cargar Formato de Horarios Reales Enviado al Cliente" (ADR-146, petición del
 * usuario): junto a "Carga de Órdenes Reales Desde Layout" en "Capturar Reales" — misma
 * lista negra que `FormatoHorariosReales.tsx` (cualquier formato salvo
 * ejecutables/scripts), PERO además excluye audio: Word, Excel, TXT, PowerPoint, PDF e
 * imágenes sí; audio no.
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  descargarFormatoRealClienteOrdenEstacionApi,
  eliminarFormatoRealClienteOrdenEstacionApi,
  subirFormatoRealClienteOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import { ordenEstacionFormatoRealClienteFromApi } from "../../adapters/fromApi";
import { EXTENSIONES_PELIGROSAS_FORMATO_REAL_CLIENTE, FORMATO_REAL_CLIENTE_MAX_BYTES } from "../../constants";
import type { OrdenEstacionFormatoRealCliente } from "../../types";

interface FormatoRealesClienteProps {
  ordenEstacionId: string;
  formatos: OrdenEstacionFormatoRealCliente[];
  onFormatosChange: (formatos: OrdenEstacionFormatoRealCliente[]) => void;
}

export function FormatoRealesCliente({
  ordenEstacionId,
  formatos,
  onFormatosChange,
}: FormatoRealesClienteProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata) — el backend SIEMPRE revalida, además del
    // contenido real (firma de ejecutable), no solo la extensión declarada.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if ((EXTENSIONES_PELIGROSAS_FORMATO_REAL_CLIENTE as readonly string[]).includes(ext)) {
      setError(`Formato no permitido (ejecutable/script/audio): .${ext}`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > FORMATO_REAL_CLIENTE_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(FORMATO_REAL_CLIENTE_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const dto = await subirFormatoRealClienteOrdenEstacionApi(ordenEstacionId, archivo);
      onFormatosChange([...formatos, ordenEstacionFormatoRealClienteFromApi(dto)]);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el archivo.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async (formato: OrdenEstacionFormatoRealCliente) => {
    setError(null);
    try {
      await descargarFormatoRealClienteOrdenEstacionApi(ordenEstacionId, formato.id, formato.nombre_archivo);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo descargar el archivo.");
    }
  };

  const onEliminar = async (formato: OrdenEstacionFormatoRealCliente) => {
    setError(null);
    try {
      await eliminarFormatoRealClienteOrdenEstacionApi(ordenEstacionId, formato.id);
      onFormatosChange(formatos.filter((f) => f.id !== formato.id));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo quitar el archivo.");
    }
  };

  return (
    <div className="form-card">
      <div className="form-card-title">Cargar Formato de Horarios Reales Enviado al Cliente</div>
      <div className="form-card-sub">
        Word, Excel, TXT, PowerPoint, PDF e imágenes — no se permiten ejecutables ni audio.
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
