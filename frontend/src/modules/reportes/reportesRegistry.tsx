/** Registro de vistas de la fase Reportes (F4) — mismo patrón que
 * `cobranzaRegistry.tsx`/`facturacionRegistry.tsx`, con una pieza NUEVA que esos no
 * tienen: cada entrada declara qué ÁREAS la pueden ver (`areas`), espejo de la clave
 * RBAC de `app/core/security.py` que protege su endpoint — el explorador filtra sus
 * propias entradas con esto, en vez de mostrarlas siempre. Es necesario aquí y no en
 * F2/F3 porque esas fases reparten "captura vs. lectura" dentro de áreas que de todas
 * formas pueden LEER casi todo; F4 tiene vistas genuinamente cerradas (el Estado de
 * resultados es exclusivo de Dirección).
 */

/* eslint-disable react-refresh/only-export-components --
 * Igual que `cobranzaRegistry`: mezcla configuración con referencias a pantallas vía
 * `render`. No es un módulo de componentes. */

import type { SidebarGroup } from "@/shared/ui";

import { DashboardCobranzaPage } from "./pages/DashboardCobranzaPage";
import { DashboardComercialPage } from "./pages/DashboardComercialPage";
import { DashboardOperativoPage } from "./pages/DashboardOperativoPage";
import { EstadoResultadosPage } from "./pages/EstadoResultadosPage";

export interface ReportesEntry {
  key: string;
  label: string;
  group: string;
  /** Áreas que pueden ver esta vista (incluye siempre "admin", ADR-040). */
  areas: string[];
  render: () => React.ReactNode;
}

export const REPORTES_GROUPS = ["Reportes financieros", "Dashboards"] as const;

// Espejo de `RBAC["reportes_financiero"|"reportes_comercial"|"reportes_cobranza"|
// "reportes_operativo"]` en `app/core/security.py`.
const AREAS_FINANCIERO = ["admin", "direccion"];
const AREAS_COMERCIAL = ["admin", "direccion", "ventas"];
const AREAS_COBRANZA = ["admin", "direccion", "facturacion", "tesoreria", "cxc", "cxp"];
// Todas las áreas (reportes_operativo es la única vista de F4 sin restricción real).
const AREAS_OPERATIVO = [
  "admin",
  "direccion",
  "ventas",
  "facturacion",
  "tesoreria",
  "cxc",
  "cxp",
  "nominas",
];

export const reportesRegistry: ReportesEntry[] = [
  {
    key: "estado_resultados",
    label: "Estado de resultados",
    group: "Reportes financieros",
    areas: AREAS_FINANCIERO,
    render: () => <EstadoResultadosPage />,
  },
  {
    key: "dashboard_comercial",
    label: "Comercial",
    group: "Dashboards",
    areas: AREAS_COMERCIAL,
    render: () => <DashboardComercialPage />,
  },
  {
    key: "dashboard_cobranza",
    label: "Cobranza",
    group: "Dashboards",
    areas: AREAS_COBRANZA,
    render: () => <DashboardCobranzaPage />,
  },
  {
    key: "dashboard_operativo",
    label: "Operativo",
    group: "Dashboards",
    areas: AREAS_OPERATIVO,
    render: () => <DashboardOperativoPage />,
  },
];

/** Entradas visibles para un área — lo que el usuario puede ver en el menú. */
export function entradasPermitidas(area: string): ReportesEntry[] {
  return reportesRegistry.filter((e) => e.areas.includes(area));
}

export function buildReportesGroups(entries: ReportesEntry[]): SidebarGroup[] {
  return REPORTES_GROUPS.map((titulo) => ({
    title: titulo,
    items: entries.filter((e) => e.group === titulo).map((e) => ({ key: e.key, label: e.label })),
  })).filter((g) => g.items.length > 0);
}
