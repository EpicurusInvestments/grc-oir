/** Búsqueda de colonias por código postal (SEPOMEX) — usada por el domicilio
 * estructurado de Anunciante/EmpresaFacturadora (ver `shared/ui/DomicilioPostalInput`). */

import { apiClient } from "@/shared/lib/apiClient";

import type { AsentamientoPostal } from "./types";

/** Lista vacía si el CP no existe en el catálogo (o aún no se sembró) — nunca 404. */
export async function buscarCodigoPostal(codigoPostal: string): Promise<AsentamientoPostal[]> {
  const { data } = await apiClient.get<AsentamientoPostal[]>(
    `/catalogos/codigos-postales/${encodeURIComponent(codigoPostal)}`,
  );
  return data;
}
