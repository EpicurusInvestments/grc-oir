/** Selector con filtro de búsqueda — para listas largas donde un `<select>` nativo se
 * vuelve incómodo (buscar por folio, número de orden, etc.). Al enfocarse muestra un
 * campo de texto para filtrar por substring (sin distinguir mayúsculas/minúsculas) sobre
 * la etiqueta de cada opción; al elegir una, vuelve a mostrar la etiqueta seleccionada.
 */

import { useEffect, useRef, useState } from "react";

export interface OpcionBuscable {
  value: string;
  label: string;
}

interface SearchableSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: OpcionBuscable[];
  placeholder?: string;
  emptyOptionLabel?: string;
  emptyResultsLabel?: string;
  disabled?: boolean;
}

export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Selecciona…",
  emptyOptionLabel,
  emptyResultsLabel = "Sin resultados.",
  disabled,
}: SearchableSelectProps) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const contenedorRef = useRef<HTMLDivElement>(null);

  const seleccionada = options.find((o) => o.value === value);

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

  const filtradas = query.trim()
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  const elegir = (v: string) => {
    onChange(v);
    setAbierto(false);
    setQuery("");
  };

  return (
    <div ref={contenedorRef} style={{ position: "relative" }}>
      <input
        className="fi"
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        value={abierto ? query : seleccionada?.label ?? ""}
        onFocus={() => setAbierto(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setAbierto(true);
        }}
      />
      {abierto && (
        <div className="ssel-list">
          <div className="ssel-item ssel-item-muted" onMouseDown={() => elegir("")}>
            {emptyOptionLabel ?? placeholder}
          </div>
          {filtradas.map((o) => (
            <div key={o.value} className="ssel-item" onMouseDown={() => elegir(o.value)}>
              {o.label}
            </div>
          ))}
          {filtradas.length === 0 && <div className="ssel-empty">{emptyResultsLabel}</div>}
        </div>
      )}
    </div>
  );
}
