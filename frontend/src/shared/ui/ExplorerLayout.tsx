/** Layout del explorador: header arriba; sidebar + área principal abajo.
 * Es el contenedor común de TODAS las pantallas de catálogos.
 */

import type { ReactNode } from "react";

import { AppHeader } from "./AppHeader";
import { Sidebar, type SidebarGroup } from "./Sidebar";

interface ExplorerLayoutProps {
  faseLabel: string;
  user: { username: string; area: string };
  groups: SidebarGroup[];
  activeKey: string | null;
  onSelect: (key: string) => void;
  children: ReactNode;
  /** Slot opcional en el header, antes del chip de usuario (ver `AppHeader.beforeUser`). */
  headerExtra?: ReactNode;
  /** Clase extra en la raíz para repintar los tokens `--phase*` de ESTA pantalla:
   *  `phase-f1` (teal, Órdenes), `phase-f5` (rojo de marca, Seguridad)… Sin ella se usa el
   *  color por defecto de `:root`, que es F0 morado — así los catálogos no cambian. */
  rootClassName?: string;
}

export function ExplorerLayout({
  faseLabel,
  user,
  groups,
  activeKey,
  onSelect,
  children,
  headerExtra,
  rootClassName,
}: ExplorerLayoutProps) {
  return (
    <div className={`app-shell ${rootClassName ?? ""}`}>
      <AppHeader faseLabel={faseLabel} user={user} beforeUser={headerExtra} />
      <div className="app-body">
        <Sidebar groups={groups} activeKey={activeKey} onSelect={onSelect} />
        <main className="main">{children}</main>
      </div>
    </div>
  );
}
