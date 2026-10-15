/** PDFs de OrdenEstacion (orden de servicio / horarios programados / horarios reales) —
 * generados al vuelo por el backend (`orden_estacion_pdf.py`), no se guarda ningún
 * archivo: cada descarga refleja los datos más recientes.
 *
 * Al hacer clic se abre un visor (pestaña nueva con el PDF incrustado, `<embed>`,
 * `shared/lib/visorPdf.ts` — ADR-203, reusado también por Facturación) — no se fuerza
 * la descarga directa como con los adjuntos de `adjuntosApi.ts`.
 */

import { apiClient } from "@/shared/lib/apiClient";
import { abrirVisorPdf } from "@/shared/lib/visorPdf";

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
  abrirVisorPdf(data, `${TITULO_DOCUMENTO[tipo]} · ${folioOrdenInterna}`);
}
