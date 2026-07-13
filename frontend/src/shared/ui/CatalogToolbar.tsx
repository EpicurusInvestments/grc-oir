/** Toolbar reutilizable: búsqueda + filtros rápidos en pills + contador de resultados.
 * Estado controlado por el padre (el filtrado/paginación se resuelven en el backend).
 */

import type { ReactNode } from "react";

export interface FilterPill {
  key: string;
  label: string;
}

interface CatalogToolbarProps {
  search: string;
  onSearch: (value: string) => void;
  searchPlaceholder?: string;
  filterLabel?: string;
  filters?: FilterPill[];
  activeFilter?: string;
  onFilter?: (key: string) => void;
  /** Segundo grupo de filtros opcional, mostrado a la IZQUIERDA junto al primero
   *  (p.ej. "Relación" en Anunciantes, además de "Estatus"). */
  filterLabel2?: string;
  filters2?: FilterPill[];
  activeFilter2?: string;
  onFilter2?: (key: string) => void;
  /** Texto del contador, p.ej. "12 de 42". */
  count?: string;
  /** Acciones a la derecha (antes del contador), p.ej. botón "+ Nuevo". */
  actions?: ReactNode;
}

export function CatalogToolbar({
  search,
  onSearch,
  searchPlaceholder = "Buscar…",
  filterLabel = "Estatus",
  filters = [],
  activeFilter,
  onFilter,
  filterLabel2,
  filters2 = [],
  activeFilter2,
  onFilter2,
  count,
  actions,
}: CatalogToolbarProps) {
  return (
    <div className="toolbar">
      <input
        className="search"
        placeholder={searchPlaceholder}
        value={search}
        onChange={(e) => onSearch(e.target.value)}
      />
      {filters.length > 0 && <span className="tb-label">{filterLabel}</span>}
      {filters.map((f) => (
        <button
          type="button"
          key={f.key}
          className={`fp ${f.key === activeFilter ? "active" : ""}`}
          onClick={() => onFilter?.(f.key)}
        >
          {f.label}
        </button>
      ))}
      {filters2.length > 0 && <span className="tb-label">{filterLabel2}</span>}
      {filters2.map((f) => (
        <button
          type="button"
          key={f.key}
          className={`fp ${f.key === activeFilter2 ? "active" : ""}`}
          onClick={() => onFilter2?.(f.key)}
        >
          {f.label}
        </button>
      ))}
      <div className="tb-spacer" />
      {actions}
      {count !== undefined && <span className="tb-count">{count}</span>}
    </div>
  );
}
