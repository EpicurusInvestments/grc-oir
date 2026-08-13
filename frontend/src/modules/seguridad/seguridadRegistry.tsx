/** Registro de secciones de la fase Seguridad (F5) — gemelo del `catalogRegistry` de F0.
 *
 * Hoy tiene UNA entrada (Usuarios), la que adelantó F5-00. Cuando llegue F5 pleno, sus
 * pantallas (PermisoCampo, bitácora de auditoría) se agregan aquí y aparecen solas en el
 * sidebar: no hay que tocar la ruta ni el explorador.
 */

/* eslint-disable react-refresh/only-export-components --
 * Igual que `catalogRegistry`: mezcla datos de configuración con referencias a pantallas
 * vía `render`. No es un módulo de componentes; la regla de fast-refresh no aplica. */

import type { ReactNode } from "react";

import type { SidebarGroup } from "@/shared/ui";

import { UsuariosPage } from "./usuarios/pages/UsuariosPage";

export interface SeguridadEntry {
  key: string;
  label: string;
  group: string;
  /** Pantalla de la sección. Si falta, el explorador muestra "no implementado". */
  render?: () => ReactNode;
}

export const SEGURIDAD_GROUPS = ["Acceso", "Auditoría"] as const;

export const seguridadRegistry: SeguridadEntry[] = [
  {
    key: "usuarios",
    label: "Usuarios",
    group: "Acceso",
    render: () => <UsuariosPage />,
  },
  // Pendientes de F5 pleno; se muestran para que el alcance de la fase sea visible.
  { key: "permisos_campo", label: "Permisos por campo", group: "Acceso" },
  { key: "bitacora", label: "Bitácora de cambios", group: "Auditoría" },
];

/** Agrupa las entradas para el `Sidebar`, respetando el orden de `SEGURIDAD_GROUPS`. */
export function buildSeguridadGroups(entries: SeguridadEntry[]): SidebarGroup[] {
  return SEGURIDAD_GROUPS.map((titulo) => ({
    title: titulo,
    items: entries
      .filter((e) => e.group === titulo)
      .map((e) => ({ key: e.key, label: e.label })),
  })).filter((g) => g.items.length > 0);
}
