/** Selector MÚLTIPLE con filtro de búsqueda — mismo espíritu que `SearchableSelect`, pero
 * para campos donde se puede marcar más de una opción a la vez (p.ej. "Factura
 * relacionada" en la captura de F2, ADR-062). Las opciones elegidas se muestran como
 * chips removibles arriba del campo de búsqueda; el desplegable solo ofrece lo que
 * todavía NO está seleccionado, así que no hay forma de duplicar una elección.
 */

import { useEffect, useRef, useState } from "react";

import type { OpcionBuscable } from "./SearchableSelect";

interface MultiSearchableSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  options: OpcionBuscable[];
  placeholder?: string;
  emptyResultsLabel?: string;
  disabled?: boolean;
}

export function MultiSearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Busca y selecciona…",
  emptyResultsLabel = "Sin resultados.",
  disabled,
}: MultiSearchableSelectProps) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const contenedorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    function alHacerClicFuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", alHacerClicFuera);
    return () => document.removeEventListener("mousedown", alHacerClicFuera);
  }, [abierto]);

  const seleccionadas = value
    .map((v) => options.find((o) => o.value === v))
    .filter((o): o is OpcionBuscable => o != null);

  const disponibles = options.filter((o) => !value.includes(o.value));
  const filtradas = query.trim()
    ? disponibles.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : disponibles;

  const agregar = (v: string) => {
    onChange([...value, v]);
    setQuery("");
  };

  const quitar = (v: string) => onChange(value.filter((x) => x !== v));

  return (
    <div ref={contenedorRef} style={{ position: "relative" }}>
      {seleccionadas.length > 0 && (
        <div className="msel-chips">
          {seleccionadas.map((o) => (
            <span key={o.value} className="msel-chip">
              {o.label}
              {!disabled && (
                <button
                  type="button"
                  className="msel-chip-remove"
                  aria-label={`Quitar ${o.label}`}
                  onClick={() => quitar(o.value)}
                >
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      <input
        className="fi"
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        value={query}
        onFocus={() => setAbierto(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setAbierto(true);
        }}
      />
      {abierto && (
        <div className="ssel-list">
          {filtradas.map((o) => (
            <div key={o.value} className="ssel-item" onMouseDown={() => agregar(o.value)}>
              {o.label}
            </div>
          ))}
          {filtradas.length === 0 && <div className="ssel-empty">{emptyResultsLabel}</div>}
        </div>
      )}
    </div>
  );
}
