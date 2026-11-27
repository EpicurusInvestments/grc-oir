/** Sidebar del explorador: catálogos agrupados, con contador por catálogo (side-count). */

import type { ReactNode } from "react";

export interface SidebarItem {
  key: string;
  label: string;
  count?: number;
  icon?: ReactNode;
  /** Resalta el contador en rojo (p.ej. "Pendientes de asignar"). */
  urgent?: boolean;
}

export interface SidebarGroup {
  title: string;
  items: SidebarItem[];
}

interface SidebarProps {
  groups: SidebarGroup[];
  activeKey: string | null;
  onSelect: (key: string) => void;
}

export function Sidebar({ groups, activeKey, onSelect }: SidebarProps) {
  return (
    <aside className="sidebar">
      {groups.map((group) => (
        <div className="side-section" key={group.title}>
          <div className="side-title">{group.title}</div>
          {group.items.map((item) => (
            <button
              type="button"
              key={item.key}
              className={`side-item ${item.key === activeKey ? "active" : ""}`}
              onClick={() => onSelect(item.key)}
            >
              {item.icon}
              {item.label}
              {/* Sin contador real que mostrar (F4: "Estado de resultados" no es una
               *  bandeja con items que contar), se omite el badge por completo — un "0"
               *  ahí no informa nada, solo distrae. El resto de los módulos SIEMPRE pasan
               *  un `count` real (aunque sea 0 "pendientes"), así que no cambian. */}
              {item.count !== undefined && (
                <span className={`side-count ${item.urgent ? "urgent" : ""}`}>{item.count}</span>
              )}
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}
