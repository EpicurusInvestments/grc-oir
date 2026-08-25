/** Registro de secciones de la fase Facturación (F2) — gemelo del de Catálogos y Seguridad.
 *
 * Los dos grupos NO son cosmética: reflejan que el módulo tiene dos claves de RBAC
 * distintas (ADR-044). «Ingresos» lo captura Facturación (`facturacion:*`) y «Costos» lo
 * captura CxP (`costos:*`). Agruparlo así hace visible en el menú una regla que de otro
 * modo solo se descubre al recibir un 403.
 */

/* eslint-disable react-refresh/only-export-components --
 * Igual que `catalogRegistry` y `seguridadRegistry`: mezcla configuración con referencias
 * a pantallas vía `render`. No es un módulo de componentes. */

import type { ReactNode } from "react";

import type { SidebarGroup } from "@/shared/ui";

import { CostosPage } from "./costoAdicional/pages/CostosPage";
import { FacturasAfiliadoPage } from "./facturaAfiliado/pages/FacturasAfiliadoPage";
import { FacturasAgenciaPage } from "./facturaAgencia/pages/FacturasAgenciaPage";
import { FacturasClientePage } from "./facturaCliente/pages/FacturasClientePage";
import { ListasParaFacturarPage } from "./facturaCliente/pages/ListasParaFacturarPage";

export interface FacturacionEntry {
  key: string;
  label: string;
  group: string;
  render?: () => ReactNode;
}

export const FACTURACION_GROUPS = ["Ingresos", "Costos"] as const;

export const facturacionRegistry: FacturacionEntry[] = [
  {
    key: "facturas_cliente",
    label: "Facturas al cliente",
    group: "Ingresos",
    render: () => <FacturasClientePage />,
  },
  {
    // Bandeja operativa, no un CRUD: órdenes cerradas que aún no tienen factura. Va con
    // Ingresos porque es el paso PREVIO a emitir la factura al cliente.
    key: "listas_para_facturar",
    label: "Listas para facturar",
    group: "Ingresos",
    render: () => <ListasParaFacturarPage />,
  },
  {
    key: "facturas_afiliado",
    label: "Facturas de afiliado",
    group: "Costos",
    render: () => <FacturasAfiliadoPage />,
  },
  {
    key: "facturas_agencia",
    label: "Facturas de agencia",
    group: "Costos",
    render: () => <FacturasAgenciaPage />,
  },
  {
    key: "costos_adicionales",
    label: "Costos adicionales",
    group: "Costos",
    render: () => <CostosPage />,
  },
];

/** Contadores por sección (los que el explorador sabe calcular). `urgent` los pinta en
 *  rojo: "Listas para facturar" es trabajo PENDIENTE, no un inventario. */
export interface ContadoresFacturacion {
  [key: string]: { count: number; urgent?: boolean } | undefined;
}

export function buildFacturacionGroups(
  entries: FacturacionEntry[],
  contadores: ContadoresFacturacion = {},
): SidebarGroup[] {
  return FACTURACION_GROUPS.map((titulo) => ({
    title: titulo,
    items: entries
      .filter((e) => e.group === titulo)
      .map((e) => ({
        key: e.key,
        label: e.label,
        count: contadores[e.key]?.count,
        urgent: contadores[e.key]?.urgent,
      })),
  })).filter((g) => g.items.length > 0);
}
