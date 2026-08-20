/** Adjuntos de Órdenes (antes "simulados"): un solo endpoint genérico de subida/descarga
 * para los 5 campos que lo necesitan — ver `backend/app/modules/ordenes/adjuntos.py`.
 * El bucket es privado: la descarga SIEMPRE pasa por el backend (blob con auth), nunca
 * por URL pública, igual que los adjuntos de Contrato.
 */

import { apiClient, postFormData } from "@/shared/lib/apiClient";

export type TipoAdjuntoOrden =
  | "odc"
  | "cierre_odc"
  | "cierre_carta"
  | "reporte_reales"
  | "reporte_programados";

export interface AdjuntoOrdenSubido {
  ref: string;
  nombre_archivo: string;
}

/** Sube el archivo (multipart) bajo el prefijo del `tipo`; el backend valida extensión
 * (lista blanca), magic bytes y tamaño. Devuelve la clave real (`ref`) a guardar en el
 * campo `_ref` de la orden. */
export function subirAdjuntoOrden(tipo: TipoAdjuntoOrden, archivo: File): Promise<AdjuntoOrdenSubido> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  return postFormData<AdjuntoOrdenSubido>(`/ordenes/adjuntos?tipo=${tipo}`, fd);
}

/** Abre el adjunto en una pestaña nueva (blob servido por el backend, con auth). */
export async function verAdjuntoOrden(ref: string): Promise<void> {
  const { data } = await apiClient.get<Blob>("/ordenes/adjuntos", {
    params: { ref },
    responseType: "blob",
  });
  const url = URL.createObjectURL(data);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** La clave real es `<prefijo><uuid_hex>_<nombre>` (ver backend) — para mostrar solo el
 * nombre original al usuario, sin el prefijo ni el UUID. */
export function nombreDeAdjuntoRef(ref: string): string {
  const base = ref.split("/").pop() ?? ref;
  const idx = base.indexOf("_");
  return idx >= 0 ? base.slice(idx + 1) : base;
}
