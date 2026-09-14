/** Registro de secciones de la fase Cobranza y Pagos (F3) — gemelo del de Facturación.
 *
 * Los grupos y su orden son los de la pantalla aprobada
 * (`docs/referencias/pantallas/Fase_3_-_Cobranza.html`): «Cobranza al cliente», «Pagos a
 * proveedores», «Tesorería» y «Vistas operativas».
 *
 * De paso reflejan las dos claves de RBAC del módulo (ADR-044): el primer grupo lo
 * captura CxC (`cobranza:*`), los otros dos CxP/Tesorería (`pagos:*`, con el canal
 * dedicado de Tesorería del ADR-073 dentro del servicio).
 *
 * "Vistas operativas" no son pantallas nuevas: son las MISMAS páginas con un filtro
 * inicial preseleccionado (`filtroInicial`), igual que `showFiltered()` en el mockup.
 */

/* eslint-disable react-refresh/only-export-components --
 * Igual que `facturacionRegistry`: mezcla configuración con referencias a pantallas vía
 * `render`. No es un módulo de componentes. */

import type { SidebarGroup } from "@/shared/ui";

import { CobranzaFacturasPage } from "./cobranzaFactura/pages/CobranzaFacturasPage";
import { MovimientosBancariosPage } from "./movimientoBancario/pages/MovimientosBancariosPage";
import { PagosClientePage } from "./pagoCliente/pages/PagosClientePage";
import { RequisicionesPage } from "./requisicion/pages/RequisicionesPage";

export interface CobranzaEntry {
  key: string;
  label: string;
  group: string;
  render: () => React.ReactNode;
}

/** Grupos y orden EXACTOS de la pantalla aprobada `Fase_3_-_Cobranza.html`. */
export const COBRANZA_GROUPS = [
  "Cobranza al cliente",
  "Pagos a proveedores",
  "Tesorería",
  "Vistas operativas",
] as const;

export const cobranzaRegistry: CobranzaEntry[] = [
  {
    key: "cobranza_factura",
    label: "Cobranza de facturas",
    group: "Cobranza al cliente",
    render: () => <CobranzaFacturasPage />,
  },
  {
    key: "pago_cliente",
    label: "Pagos recibidos",
    group: "Cobranza al cliente",
    render: () => <PagosClientePage />,
  },
  {
    key: "requisicion",
    label: "Requisiciones",
    group: "Pagos a proveedores",
    render: () => <RequisicionesPage />,
  },
  {
    key: "movimiento_bancario",
    label: "Movimientos bancarios",
    group: "Tesorería",
    render: () => <MovimientosBancariosPage />,
  },
  {
    key: "cobranzas_vencidas",
    label: "Cobranzas vencidas",
    group: "Vistas operativas",
    render: () => <CobranzaFacturasPage filtroInicial="vencidas" />,
  },
  {
    key: "por_autorizar",
    label: "Por autorizar",
    group: "Vistas operativas",
    render: () => <RequisicionesPage filtroInicial="pendiente" />,
  },
  {
    key: "por_pagar",
    label: "Por pagar",
    group: "Vistas operativas",
    render: () => <RequisicionesPage filtroInicial="autorizada" />,
  },
  {
    key: "sin_conciliar",
    label: "Sin conciliar",
    group: "Vistas operativas",
    render: () => <MovimientosBancariosPage filtroInicial="sin_conciliar" />,
  },
];

/** Contadores por sección. `urgent` lo decide el explorador (ver `CobranzaExplorerPage`):
 *  marca las 4 "vistas operativas" en rojo — son trabajo PENDIENTE, no inventario (mismo
 *  criterio que "Listas para facturar" en F2). */
export interface ContadoresCobranza {
  [key: string]: { count: number; urgent?: boolean } | undefined;
}

export function buildCobranzaGroups(
  entries: CobranzaEntry[],
  contadores: ContadoresCobranza = {},
): SidebarGroup[] {
  return COBRANZA_GROUPS.map((titulo) => ({
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
