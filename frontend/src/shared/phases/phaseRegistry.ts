/** Registro de fases del sistema GRC-OIR — FUENTE ÚNICA.
 *
 * El Dashboard (Home) y el menú lateral global (AppNavDrawer) se generan iterando este
 * arreglo. Hoy solo F0 (Catálogos) está construida y por eso es la única `enabled`.
 *
 * Para ACTIVAR una fase futura cuando se construya:
 *   1. `enabled: true`
 *   2. asignar su `route` (y montarla en `app/router.tsx`)
 * No hace falta tocar el Dashboard ni el Drawer: se reflejan solos en tarjeta y menú.
 *
 * El color por fase sigue la convención de la propuesta (frontend/CLAUDE.md):
 *   F0 morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo.
 * `accent` mapea a las clases de acento definidas en theme.css (.pc-accent-*).
 */

import catalogosPng from "@/modules/dashboard/assets/catalogos.png";
import catalogosWebp from "@/modules/dashboard/assets/catalogos.webp";
import cobranzaPagosPng from "@/modules/dashboard/assets/cobranza-pagos.png";
import cobranzaPagosWebp from "@/modules/dashboard/assets/cobranza-pagos.webp";
import facturacionPng from "@/modules/dashboard/assets/facturacion.png";
import facturacionWebp from "@/modules/dashboard/assets/facturacion.webp";
import ordenesPng from "@/modules/dashboard/assets/ordenes.png";
import ordenesWebp from "@/modules/dashboard/assets/ordenes.webp";
import reportesPng from "@/modules/dashboard/assets/reportes.png";
import reportesWebp from "@/modules/dashboard/assets/reportes.webp";
import seguridadPng from "@/modules/dashboard/assets/seguridad.png";
import seguridadWebp from "@/modules/dashboard/assets/seguridad.webp";

export type PhaseAccent = "purple" | "teal" | "blue" | "amber" | "gray" | "red";

export interface PhaseEntry {
  /** Clave estable de la fase (f0..f5). */
  key: string;
  /** Código visible ("F0"..."F5"). */
  code: string;
  /** Nombre de la fase. */
  name: string;
  /** Descripción de una línea. */
  description: string;
  /** Color de acento por fase (clase .pc-accent-* en theme.css). */
  accent: PhaseAccent;
  /** Ilustración optimizada (WebP principal + PNG fallback). */
  imageWebp: string;
  imagePng: string;
  /** Ruta destino. `null` mientras la fase no esté construida. */
  route: string | null;
  /** Solo las fases construidas son navegables; el resto se muestran "Próximamente". */
  enabled: boolean;
}

export const phaseRegistry: PhaseEntry[] = [
  {
    key: "f0",
    code: "F0",
    name: "Catálogos",
    description:
      "Fuente única de datos maestros: anunciantes, agencias, afiliados, tarifas y más.",
    accent: "purple",
    imageWebp: catalogosWebp,
    imagePng: catalogosPng,
    route: "/catalogos",
    enabled: true,
  },
  {
    key: "f1",
    code: "F1",
    name: "Órdenes",
    description:
      "Captura de órdenes, derivación a estaciones, verificación e incidencias.",
    accent: "teal",
    imageWebp: ordenesWebp,
    imagePng: ordenesPng,
    route: null,
    enabled: false,
  },
  {
    key: "f2",
    code: "F2",
    name: "Facturación",
    description:
      "Preparación de facturas, folio fiscal externo y costos de afiliados y agencias.",
    accent: "blue",
    imageWebp: facturacionWebp,
    imagePng: facturacionPng,
    route: null,
    enabled: false,
  },
  {
    key: "f3",
    code: "F3",
    name: "Cobranza y Pagos",
    description: "Cobranza, requisiciones de pago y conciliación bancaria.",
    accent: "amber",
    imageWebp: cobranzaPagosWebp,
    imagePng: cobranzaPagosPng,
    route: null,
    enabled: false,
  },
  {
    key: "f4",
    code: "F4",
    name: "Reportes",
    description: "Reportería ejecutiva, KPIs y cierre mensual de resultados.",
    accent: "gray",
    imageWebp: reportesWebp,
    imagePng: reportesPng,
    route: null,
    enabled: false,
  },
  {
    key: "f5",
    code: "F5",
    name: "Seguridad",
    description:
      "Permisos por área y por campo, bitácora y auditoría de parámetros sensibles.",
    accent: "red",
    imageWebp: seguridadWebp,
    imagePng: seguridadPng,
    route: null,
    enabled: false,
  },
];
