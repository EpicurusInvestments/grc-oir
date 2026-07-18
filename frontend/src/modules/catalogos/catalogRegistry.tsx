/** Registro de catálogos del explorador (gemelo del router agregador del backend).
 *
 * F0-00 deja la estructura: los grupos y entradas del sidebar (según la pantalla
 * aprobada), TODAS sin pantalla concreta todavía (`render` ausente). Desde F0-01, cada
 * catálogo registra aquí su entrada con su `render` (su pantalla lista+detalle) y el
 * explorador la muestra automáticamente.
 */

/* eslint-disable react-refresh/only-export-components --
 * Por diseño (F0-00) este registro mezcla datos de configuración (grupos, entradas) con
 * referencias a los componentes de pantalla vía `render`. No es un módulo de componentes;
 * la regla de fast-refresh (solo afecta HMR) no aplica aquí. */

import type { ReactNode } from "react";

import type { SidebarGroup } from "@/shared/ui";

import { AfiliadoCatalogPage } from "./afiliado/pages/AfiliadoCatalogPage";
import { AgenciaCatalogPage } from "./agencia/pages/AgenciaCatalogPage";
import { AnuncianteCatalogPage } from "./anunciante/pages/AnuncianteCatalogPage";
import { CategoriaCatalogPage } from "./categoria/pages/CategoriaCatalogPage";
import { ContratoCatalogPage } from "./contrato/pages/ContratoCatalogPage";
import { EmpresaFacturadoraCatalogPage } from "./empresaFacturadora/pages/EmpresaFacturadoraCatalogPage";
import { PlazaCatalogPage } from "./plaza/pages/PlazaCatalogPage";
import { TarifaCatalogPage } from "./tarifa/pages/TarifaCatalogPage";
import { VendedorCatalogPage } from "./vendedor/pages/VendedorCatalogPage";

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
  {
    key: "anunciante",
    label: "Anunciantes",
    group: "Comerciales",
    render: () => <AnuncianteCatalogPage />,
  },
  {
    key: "agencia",
    label: "Agencias",
    group: "Comerciales",
    render: () => <AgenciaCatalogPage />,
  },
  {
    key: "contrato",
    label: "Contratos",
    group: "Comerciales",
    render: () => <ContratoCatalogPage />,
  },
  {
    key: "afiliado",
    label: "Afiliados y estaciones",
    group: "Operación",
    render: () => <AfiliadoCatalogPage />,
  },
  { key: "plaza", label: "Plazas", group: "Operación", render: () => <PlazaCatalogPage /> },
  {
    key: "tarifa",
    label: "Tarifas por plaza",
    group: "Operación",
    render: () => <TarifaCatalogPage />,
  },
  {
    key: "vendedor",
    label: "Vendedores",
    group: "Soporte",
    render: () => <VendedorCatalogPage />,
  },
  {
    key: "categoria",
    label: "Categorías",
    group: "Soporte",
    render: () => <CategoriaCatalogPage />,
  },
  {
    key: "empresa_facturadora",
    label: "Empresas facturadoras",
    group: "Soporte",
    render: () => <EmpresaFacturadoraCatalogPage />,
  },
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
