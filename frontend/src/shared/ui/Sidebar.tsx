/** Sidebar del explorador: catálogos agrupados, con contador por catálogo (side-count). */

import type { ReactNode } from "react";

export interface SidebarItem {
  key: string;
  label: string;
  count?: number;
  icon?: ReactNode;
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
              <span className="side-count">{item.count ?? 0}</span>
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}
