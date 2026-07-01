/** Registro de catálogos del explorador (gemelo del router agregador del backend).
 *
 * F0-00 deja la estructura: los grupos y entradas del sidebar (según la pantalla
 * aprobada), TODAS sin pantalla concreta todavía (`render` ausente). Desde F0-01, cada
 * catálogo registra aquí su entrada con su `render` (su pantalla lista+detalle) y el
 * explorador la muestra automáticamente.
 */

import type { ReactNode } from "react";

import type { SidebarGroup } from "@/shared/ui";

export interface CatalogEntry {
  key: string;
  label: string;
  group: string;
  count?: number;
  /** Pantalla del catálogo. Si falta, el explorador muestra "no implementado". */
  render?: () => ReactNode;
}

/** Orden de grupos como en la pantalla aprobada. */
export const CATALOG_GROUPS = ["Comerciales", "Operación", "Soporte", "Configuración"] as const;

/** Entradas iniciales (placeholders). F0-01+ añade `render` a cada una. */
export const catalogRegistry: CatalogEntry[] = [
  { key: "anunciante", label: "Anunciantes", group: "Comerciales" },
  { key: "agencia", label: "Agencias", group: "Comerciales" },
  { key: "contrato", label: "Contratos", group: "Comerciales" },
  { key: "afiliado", label: "Afiliados y estaciones", group: "Operación" },
  { key: "plaza", label: "Plazas", group: "Operación" },
  { key: "tarifa", label: "Tarifas por plaza", group: "Operación" },
  { key: "vendedor", label: "Vendedores", group: "Soporte" },
  { key: "categoria", label: "Categorías", group: "Soporte" },
  { key: "constantes", label: "Constantes del sistema", group: "Configuración" },
];

/** Construye los grupos del sidebar a partir del registry, respetando CATALOG_GROUPS. */
export function buildSidebarGroups(registry: CatalogEntry[]): SidebarGroup[] {
  return CATALOG_GROUPS.map((title) => ({
    title,
    items: registry
      .filter((e) => e.group === title)
      .map((e) => ({ key: e.key, label: e.label, count: e.count })),
  })).filter((g) => g.items.length > 0);
}
