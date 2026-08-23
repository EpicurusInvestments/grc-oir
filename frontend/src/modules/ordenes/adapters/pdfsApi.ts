/** PDFs de OrdenEstacion (orden de servicio / horarios programados / horarios reales) —
 * generados al vuelo por el backend (`orden_estacion_pdf.py`), no se guarda ningún
 * archivo: cada descarga refleja los datos más recientes.
 *
 * Al hacer clic se abre un visor (pestaña nueva con el PDF incrustado, `<embed>`) — no
 * se fuerza la descarga directa como con los adjuntos de `adjuntosApi.ts`. El propio
 * visor nativo de PDF del navegador ya trae sus botones de imprimir/descargar; la barra
 * inferior solo ofrece "Cerrar" (un botón de "Imprimir" propio se probó y no hacía nada
 * de forma confiable entre navegadores sobre el `<embed>`, así que se quitó).
 */

import { apiClient } from "@/shared/lib/apiClient";

export type TipoPdfOrdenEstacion = "servicio" | "programados" | "reales";

const TITULO_DOCUMENTO: Record<TipoPdfOrdenEstacion, string> = {
  servicio: "Orden de servicio",
  programados: "Horarios programados",
  reales: "Horarios reales",
};

export async function previsualizarPdfOrdenEstacion(
  ordenEstacionId: string,
  tipo: TipoPdfOrdenEstacion,
  folioOrdenInterna: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(`/ordenes/estaciones/${ordenEstacionId}/pdf/${tipo}`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(data);
  const ventana = window.open("", "_blank", "width=900,height=1100");
  if (!ventana) {
    URL.revokeObjectURL(url);
    throw new Error("El navegador bloqueó la ventana emergente. Habilita las ventanas emergentes para ver el PDF.");
  }

  const titulo = `${TITULO_DOCUMENTO[tipo]} · ${folioOrdenInterna}`;
  ventana.document.write(`<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>${titulo}</title>
<style>
  html, body { margin: 0; height: 100%; background: #525659; }
  embed { width: 100%; height: calc(100% - 46px); border: 0; display: block; }
  .print-bar {
    position: fixed; bottom: 0; left: 0; right: 0; height: 46px;
    background: #1a1a1a; color: #fff; display: flex; align-items: center;
    justify-content: center; gap: 14px; font-family: system-ui, -apple-system, sans-serif; font-size: 13px;
  }
  .print-bar button {
    background: #fff; color: #1a1a1a; border: 0; padding: 6px 14px;
    border-radius: 3px; cursor: pointer; font-weight: 600; font-size: 12px;
  }
</style>
</head>
<body>
  <embed src="${url}" type="application/pdf">
  <div class="print-bar">
    Vista previa del PDF
    <button onclick="window.close()">Cerrar</button>
  </div>
</body>
</html>`);
  ventana.document.close();
  ventana.addEventListener("beforeunload", () => URL.revokeObjectURL(url));
}
