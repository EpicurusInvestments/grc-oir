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
}

export function ExplorerLayout({
  faseLabel,
  user,
  groups,
  activeKey,
  onSelect,
  children,
}: ExplorerLayoutProps) {
  return (
    <div className="app-shell">
      <AppHeader faseLabel={faseLabel} user={user} />
      <div className="app-body">
        <Sidebar groups={groups} activeKey={activeKey} onSelect={onSelect} />
        <main className="main">{children}</main>
      </div>
    </div>
  );
}
