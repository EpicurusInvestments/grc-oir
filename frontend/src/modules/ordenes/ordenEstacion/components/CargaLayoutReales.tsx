/** "Carga de Órdenes Reales Desde Layout" (ADR-146/ADR-147/ADR-149/ADR-154, petición del
 * usuario): junto a "Formato de Horarios Reales Enviado al Cliente" en "Capturar
 * Reales" — lista BLANCA de extensiones, pero SOLO csv (ADR-154: se quitaron xlsx/xls/
 * txt — el parseo nunca los entendió, solo se guardaban sin procesar; restringir evita
 * que el usuario suba un formato que el sistema no va a aplicar).
 *
 * ADR-147/ADR-149: el backend parsea el csv (columnas Estacion, Fecha, Hora, Spots —
 * sumando los Spots de filas con la misma fecha+hora) y separa cada fecha+hora en:
 * `aplicados` (coincide con un día ya existente — reemplaza su override de reales) o
 * `nuevos` (no existe — se ofrece como día NUEVO a crear si el usuario avanza a 2.3,
 * mismo criterio que asignar una hora distinta al crear la OE). Una fila que no se pudo
 * usar (estación distinta, valor inválido) se ignora y se reporta aquí, sin tumbar el
 * resto. Lo que sí aplica/es nuevo se manda al padre (`onAplicado`) para que reemplace
 * COMPLETO lo cargado en la tabla de "Capturar Reales" — un día que no viene en el
 * archivo vuelve a mostrar su valor programado.
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  descargarLayoutRealOrdenEstacionApi,
  eliminarLayoutRealOrdenEstacionApi,
  subirLayoutRealOrdenEstacionApi,
} from "../../adapters/escrituraApi";
import {
  layoutRealAplicadoFromApi,
  layoutRealErrorFromApi,
  layoutRealNuevoFromApi,
  ordenEstacionLayoutRealFromApi,
} from "../../adapters/fromApi";
import { EXTENSIONES_LAYOUT_REALES, LAYOUT_REAL_ACCEPT, LAYOUT_REAL_MAX_BYTES } from "../../constants";
import type {
  LayoutRealAplicado,
  LayoutRealError,
  LayoutRealNuevo,
  OrdenEstacionLayoutReal,
} from "../../types";

interface CargaLayoutRealesProps {
  ordenEstacionId: string;
  layouts: OrdenEstacionLayoutReal[];
  onLayoutsChange: (layouts: OrdenEstacionLayoutReal[]) => void;
  onAplicado: (aplicados: LayoutRealAplicado[], nuevos: LayoutRealNuevo[]) => void;
}

export function CargaLayoutReales({
  ordenEstacionId,
  layouts,
  onLayoutsChange,
  onAplicado,
}: CargaLayoutRealesProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{
    aplicados: number;
    nuevos: number;
    errores: LayoutRealError[];
  } | null>(null);

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    setResultado(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata) — el backend SIEMPRE revalida, además del
    // contenido real cuando la extensión lo permite verificar.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(EXTENSIONES_LAYOUT_REALES as readonly string[]).includes(ext)) {
      setError(`Formato no permitido. Usa: ${EXTENSIONES_LAYOUT_REALES.join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > LAYOUT_REAL_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(LAYOUT_REAL_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const dto = await subirLayoutRealOrdenEstacionApi(ordenEstacionId, archivo);
      onLayoutsChange([...layouts, ordenEstacionLayoutRealFromApi(dto.archivo)]);

      const aplicados = dto.aplicados.map(layoutRealAplicadoFromApi);
      const nuevos = dto.nuevos.map(layoutRealNuevoFromApi);
      const errores = dto.errores.map(layoutRealErrorFromApi);
      if (aplicados.length > 0 || nuevos.length > 0 || errores.length > 0) {
        onAplicado(aplicados, nuevos);
        setResultado({ aplicados: aplicados.length, nuevos: nuevos.length, errores });
      }
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el archivo.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async (layout: OrdenEstacionLayoutReal) => {
    setError(null);
    try {
      await descargarLayoutRealOrdenEstacionApi(ordenEstacionId, layout.id, layout.nombre_archivo);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo descargar el archivo.");
    }
  };

  const onEliminar = async (layout: OrdenEstacionLayoutReal) => {
    setError(null);
    try {
      await eliminarLayoutRealOrdenEstacionApi(ordenEstacionId, layout.id);
      onLayoutsChange(layouts.filter((l) => l.id !== layout.id));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo quitar el archivo.");
    }
  };

  return (
    <div className="form-card">
      <div className="form-card-title">Carga de Órdenes Reales Desde Layout</div>
      <div className="form-card-sub">Archivo de layout para actualizar la tabla de reales — formato csv.</div>

      {layouts.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Sin archivos subidos todavía.
        </div>
      )}
      {layouts.map((layout) => (
        <div key={layout.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ flex: 1, fontSize: 13 }}>{layout.nombre_archivo}</span>
          <button type="button" className="btn btn-xs" onClick={() => void onDescargar(layout)}>
            Descargar
          </button>
          <button type="button" className="btn btn-xs btn-danger" onClick={() => void onEliminar(layout)}>
            Quitar
          </button>
        </div>
      ))}

      <input
        ref={inputRef}
        className="file-input"
        type="file"
        accept={LAYOUT_REAL_ACCEPT}
        disabled={subiendo}
        onChange={(e) => void onElegir(e.target.files?.[0])}
      />
      {subiendo && (
        <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
          Subiendo…
        </span>
      )}
      {error && <div className="fe">{error}</div>}
      {resultado && (
        <div className="fv" style={{ fontSize: 11, marginTop: 6 }}>
          {resultado.aplicados > 0 && (
            <div style={{ color: "var(--green-text)" }}>
              Se aplicaron {resultado.aplicados} día(s) a la tabla de reales.
            </div>
          )}
          {resultado.nuevos > 0 && (
            <div style={{ color: "var(--amber-text, #b45309)" }}>
              {resultado.nuevos} día(s) nuevo(s) listo(s) para crear al avanzar a 2.3.
            </div>
          )}
          {resultado.errores.length > 0 && (
            <div style={{ color: "var(--red-text)", marginTop: 4 }}>
              {resultado.errores.length} fila(s) no se aplicaron:
              <ul style={{ margin: "2px 0 0 16px", padding: 0 }}>
                {resultado.errores.map((e, i) => (
                  <li key={i}>
                    {e.fila > 0 ? `Fila ${e.fila}: ` : ""}
                    {e.motivo}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
