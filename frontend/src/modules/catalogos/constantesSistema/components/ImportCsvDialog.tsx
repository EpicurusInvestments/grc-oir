/** Diálogo de importación masiva CSV de constantes (flujo dry-run → confirmar).
 *
 * 1. El Admin elige un .csv y el modo de duplicados.
 * 2. "Previsualizar" sube con commit=false → muestra el REPORTE (creadas/actualizadas/
 *    omitidas/rechazadas + detalle por fila con motivos) SIN escribir.
 * 3. Solo si el Admin confirma, se re-sube el mismo archivo con commit=true para aplicar.
 *
 * Los errores estructurales (400/413: columnas faltantes, no-UTF-8, tamaño/filas) se muestran
 * de forma clara y no aplican nada. Al aplicar, el hook invalida la lista y los conteos.
 */

import { Dialog } from "primereact/dialog";
import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import { useImportarConstantes } from "../hooks";
import type { EstadoFila, ModoDuplicados, ResultadoImportacion } from "../types";

const MODOS: { value: ModoDuplicados; label: string; ayuda: string }[] = [
  { value: "actualizar", label: "Actualizar (upsert)", ayuda: "Si la clave ya existe, actualiza su descripción/valor/estatus." },
  { value: "omitir", label: "Omitir", ayuda: "Si la clave ya existe, se conserva sin cambios." },
  { value: "rechazar", label: "Rechazar", ayuda: "Si la clave ya existe, la fila se rechaza." },
];

const ESTADO_BADGE: Record<EstadoFila, string> = {
  creada: "b-green",
  actualizada: "b-teal",
  omitida: "b-gray",
  rechazada: "b-red",
};

const ESTADO_LABEL: Record<EstadoFila, string> = {
  creada: "Creada",
  actualizada: "Actualizada",
  omitida: "Omitida",
  rechazada: "Rechazada",
};

interface ImportCsvDialogProps {
  visible: boolean;
  onClose: () => void;
}

export function ImportCsvDialog({ visible, onClose }: ImportCsvDialogProps) {
  const importar = useImportarConstantes();

  const [archivo, setArchivo] = useState<File | null>(null);
  const [modo, setModo] = useState<ModoDuplicados>("actualizar");
  const [reporte, setReporte] = useState<ResultadoImportacion | null>(null);
  const [aplicado, setAplicado] = useState<ResultadoImportacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setArchivo(null);
    setModo("actualizar");
    setReporte(null);
    setAplicado(null);
    setError(null);
  };

  const cerrar = () => {
    reset();
    onClose();
  };

  // Cualquier cambio de archivo/modo invalida la previsualización previa.
  const cambiarArchivo = (f: File | null) => {
    setArchivo(f);
    setReporte(null);
    setAplicado(null);
    setError(null);
  };

  const cambiarModo = (m: ModoDuplicados) => {
    setModo(m);
    setReporte(null);
    setAplicado(null);
    setError(null);
  };

  const ejecutar = async (commit: boolean) => {
    if (!archivo) return;
    setError(null);
    try {
      const rep = await importar.mutateAsync({ archivo, commit, modo });
      if (commit) setAplicado(rep);
      else setReporte(rep);
    } catch (e) {
      if (e instanceof ApiRequestError) {
        setError(e.message);
        return;
      }
      throw e;
    }
  };

  const rep = aplicado ?? reporte;
  const aplicable = reporte ? reporte.creadas + reporte.actualizadas : 0;

  return (
    <Dialog
      header="Importar constantes desde CSV"
      visible={visible}
      onHide={cerrar}
      style={{ width: 720, maxWidth: "95vw" }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 13 }}>
        {/* Instrucciones */}
        <div style={{ color: "var(--text2)", lineHeight: 1.5 }}>
          El archivo debe ser <strong>.csv</strong> con las columnas{" "}
          <span className="mono">grupo, clave, descripcion, valor, activo</span>. Primero se
          previsualiza (no se escribe nada); luego confirmas para aplicar.
        </div>

        {/* Selección de archivo + modo */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 260px" }}>
            <div className="fl">Archivo CSV</div>
            <input
              type="file"
              accept=".csv,text/csv"
              className="fi"
              disabled={!!aplicado}
              onChange={(e) => cambiarArchivo(e.target.files?.[0] ?? null)}
            />
          </div>
          <div style={{ flex: "1 1 220px" }}>
            <div className="fl">Duplicados</div>
            <select
              className="fsel"
              value={modo}
              disabled={!!aplicado}
              onChange={(e) => cambiarModo(e.target.value as ModoDuplicados)}
            >
              {MODOS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--text3)" }}>
          {MODOS.find((m) => m.value === modo)?.ayuda}
        </div>

        {/* Error estructural (nada se aplicó) */}
        {error && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {error}
          </div>
        )}

        {/* Reporte (previsualización o resultado aplicado) */}
        {rep && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontWeight: 600 }}>
              {aplicado ? "Importación aplicada" : "Previsualización (aún no se aplica nada)"} ·{" "}
              {rep.total_filas} fila(s)
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className="badge b-green">Creadas: {rep.creadas}</span>
              <span className="badge b-teal">Actualizadas: {rep.actualizadas}</span>
              <span className="badge b-gray">Omitidas: {rep.omitidas}</span>
              <span className="badge b-red">Rechazadas: {rep.rechazadas}</span>
            </div>

            {rep.filas.length > 0 && (
              <div style={{ maxHeight: 280, overflow: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
                <table className="cat-table">
                  <thead>
                    <tr>
                      <th style={{ width: 48 }}>#</th>
                      <th style={{ width: 120 }}>Grupo</th>
                      <th style={{ width: 90 }}>Clave</th>
                      <th style={{ width: 100 }}>Estado</th>
                      <th>Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rep.filas.map((f) => (
                      <tr key={f.numero}>
                        <td className="td-mono">{f.numero}</td>
                        <td>{f.grupo ?? "—"}</td>
                        <td className="td-mono">{f.clave ?? "—"}</td>
                        <td>
                          <span className={`badge ${ESTADO_BADGE[f.estado]}`}>
                            {ESTADO_LABEL[f.estado]}
                          </span>
                        </td>
                        <td className="td-2" style={{ color: "var(--text2)" }}>
                          {f.motivo ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Acciones */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          {!aplicado && (
            <>
              <button type="button" className="btn btn-sm" onClick={cerrar} disabled={importar.isPending}>
                Cancelar
              </button>
              {!reporte ? (
                <button
                  type="button"
                  className="btn btn-sm btn-phase"
                  disabled={!archivo || importar.isPending}
                  onClick={() => ejecutar(false)}
                >
                  {importar.isPending ? "Procesando…" : "Previsualizar"}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-sm btn-phase"
                  disabled={aplicable === 0 || importar.isPending}
                  title={aplicable === 0 ? "No hay filas por crear ni actualizar." : undefined}
                  onClick={() => ejecutar(true)}
                >
                  {importar.isPending ? "Aplicando…" : `Confirmar e importar (${aplicable})`}
                </button>
              )}
            </>
          )}
          {aplicado && (
            <button type="button" className="btn btn-sm btn-phase" onClick={cerrar}>
              Cerrar
            </button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
