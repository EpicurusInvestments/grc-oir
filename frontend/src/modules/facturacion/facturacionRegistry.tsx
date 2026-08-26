/** Registro de secciones de la fase Facturación (F2) — gemelo del de Catálogos y Seguridad.
 *
 * Los grupos y sus etiquetas son los de la pantalla aprobada
 * (`docs/referencias/pantallas/Fase_2_-_Facturacion.html`): «Facturación al cliente»,
 * «Facturas recibidas» y «Costos».
 *
 * De paso reflejan las dos claves de RBAC del módulo (ADR-044): el primer grupo lo captura
 * Facturación (`facturacion:*`) y los otros dos CxP (`costos:*`), así que el menú hace
 * visible una regla que si no solo se descubre al recibir un 403.
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

/** Grupos y orden EXACTOS de la pantalla aprobada `Fase_2_-_Facturacion.html`. */
export const FACTURACION_GROUPS = [
  "Facturación al cliente",
  "Facturas recibidas",
  "Costos",
] as const;

export const facturacionRegistry: FacturacionEntry[] = [
  {
    // Bandeja operativa, no un CRUD: órdenes cerradas que aún no tienen factura. Va
    // PRIMERA a propósito: es el "qué me falta hacer hoy", el paso previo a emitir la
    // factura, y por eso también es la sección con la que abre el explorador.
    key: "listas_para_facturar",
    label: "Listas para facturar",
    group: "Facturación al cliente",
    render: () => <ListasParaFacturarPage />,
  },
  {
    key: "facturas_cliente",
    label: "Facturas al cliente",
    group: "Facturación al cliente",
    render: () => <FacturasClientePage />,
  },
  {
    key: "facturas_afiliado",
    label: "De afiliados",
    group: "Facturas recibidas",
    render: () => <FacturasAfiliadoPage />,
  },
  {
    key: "facturas_agencia",
    label: "De agencias",
    group: "Facturas recibidas",
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
