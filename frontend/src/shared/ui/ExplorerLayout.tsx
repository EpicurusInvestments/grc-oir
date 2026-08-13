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
  /** Clase de color por fase (`phase-f5`, …). Sin ella se usa el color por defecto de
   *  `:root`, que es F0 morado — así las pantallas de catálogos no cambian. */
  phaseClass?: string;
  children: ReactNode;
}

export function ExplorerLayout({
  faseLabel,
  user,
  groups,
  activeKey,
  onSelect,
  phaseClass,
  children,
}: ExplorerLayoutProps) {
  return (
    <div className={`app-shell ${phaseClass ?? ""}`}>
      <AppHeader faseLabel={faseLabel} user={user} />
      <div className="app-body">
        <Sidebar groups={groups} activeKey={activeKey} onSelect={onSelect} />
        <main className="main">{children}</main>
      </div>
    </div>
  );
}
