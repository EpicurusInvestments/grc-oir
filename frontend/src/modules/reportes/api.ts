/** Llamadas a `/api/v1/reportes` (F4-01 — Estado de resultados). */

import { apiClient } from "@/shared/lib/apiClient";

import type {
  DashboardCobranzaRead,
  DashboardComercialRead,
  DashboardOperativoRead,
  EstadoResultadosRead,
  FormatoExportacion,
  VentanaComercial,
} from "./types";

const BASE = "/reportes";

/** Extrae `filename="..."` de la cabecera, si el navegador la expone. Duplicado a
 * propósito de `modules/facturacion/api.ts` (mismo criterio que F2/F3: no se importa
 * de otro módulo de negocio). */
function leerNombreDeContentDisposition(cabeceras: unknown): string | null {
  const valor = (cabeceras as Record<string, string> | undefined)?.["content-disposition"];
  const m = valor?.match(/filename="([^"]+)"/);
  return m ? m[1] : null;
}

export const reportesApi = {
  async estadoResultados(periodo?: string): Promise<EstadoResultadosRead> {
    const { data } = await apiClient.get<EstadoResultadosRead>(`${BASE}/estado-resultados`, {
      params: periodo ? { periodo } : undefined,
    });
    return data;
  },

  /** Descarga el `.xlsx`/`.csv` del Estado de resultados — mismo patrón de blob +
   * `<a download>` que `facturacionApi.descargarArchivoPlano` (una blob URL no lleva
   * nombre de archivo). */
  async exportarEstadoResultados(periodo: string, formato: FormatoExportacion): Promise<void> {
    const respuesta = await apiClient.get(`${BASE}/estado-resultados/exportar`, {
      params: { periodo, formato },
      responseType: "blob",
    });
    const url = URL.createObjectURL(respuesta.data as Blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download =
      leerNombreDeContentDisposition(respuesta.headers) ??
      `estado_resultados_${periodo}.${formato}`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },

  async dashboardComercial(
    ventana: VentanaComercial,
    periodo?: string,
  ): Promise<DashboardComercialRead> {
    const { data } = await apiClient.get<DashboardComercialRead>(`${BASE}/comercial`, {
      params: { ventana, ...(periodo ? { periodo } : {}) },
    });
    return data;
  },

  async exportarDashboardComercial(
    ventana: VentanaComercial,
    periodo: string | undefined,
    formato: FormatoExportacion,
  ): Promise<void> {
    const respuesta = await apiClient.get(`${BASE}/comercial/exportar`, {
      params: { ventana, ...(periodo ? { periodo } : {}), formato },
      responseType: "blob",
    });
    const url = URL.createObjectURL(respuesta.data as Blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download =
      leerNombreDeContentDisposition(respuesta.headers) ?? `dashboard_comercial.${formato}`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },

  async dashboardCobranza(mes?: string, ventanaDsoDias = 90): Promise<DashboardCobranzaRead> {
    const { data } = await apiClient.get<DashboardCobranzaRead>(`${BASE}/cobranza`, {
      params: { ventana_dso_dias: ventanaDsoDias, ...(mes ? { mes } : {}) },
    });
    return data;
  },

  async exportarDashboardCobranza(
    mes: string | undefined,
    ventanaDsoDias: number,
    formato: FormatoExportacion,
  ): Promise<void> {
    const respuesta = await apiClient.get(`${BASE}/cobranza/exportar`, {
      params: { ventana_dso_dias: ventanaDsoDias, ...(mes ? { mes } : {}), formato },
      responseType: "blob",
    });
    const url = URL.createObjectURL(respuesta.data as Blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download =
      leerNombreDeContentDisposition(respuesta.headers) ?? `dashboard_cobranza.${formato}`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },

  async dashboardOperativo(
    ventana: VentanaComercial,
    periodo?: string,
  ): Promise<DashboardOperativoRead> {
    const { data } = await apiClient.get<DashboardOperativoRead>(`${BASE}/operativo`, {
      params: { ventana, ...(periodo ? { periodo } : {}) },
    });
    return data;
  },

  async exportarDashboardOperativo(
    ventana: VentanaComercial,
    periodo: string | undefined,
    formato: FormatoExportacion,
  ): Promise<void> {
    const respuesta = await apiClient.get(`${BASE}/operativo/exportar`, {
      params: { ventana, ...(periodo ? { periodo } : {}), formato },
      responseType: "blob",
    });
    const url = URL.createObjectURL(respuesta.data as Blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download =
      leerNombreDeContentDisposition(respuesta.headers) ?? `dashboard_operativo.${formato}`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },
};
