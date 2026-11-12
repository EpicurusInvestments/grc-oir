/** Selector con filtro de búsqueda — para listas largas donde un `<select>` nativo se
 * vuelve incómodo (buscar por folio, número de orden, etc.). Al enfocarse muestra un
 * campo de texto para filtrar por substring (sin distinguir mayúsculas/minúsculas) sobre
 * la etiqueta de cada opción; al elegir una, vuelve a mostrar la etiqueta seleccionada.
 *
 * ADR-267 (bug real, petición del usuario, con captura): la lista se renderizaba
 * `position: absolute` dentro del propio formulario — si ese formulario vive en un
 * panel con scroll propio y altura acotada (`.db` dentro de `.detail-pane`, el patrón de
 * TODAS las pantallas de alta/edición), la lista se recortaba en el borde del panel en
 * vez de desplegarse completa, aunque ella misma ya traía su propio scroll interno
 * (`.ssel-list` con `max-height`). Fix: la lista se renderiza en un PORTAL a
 * `document.body`, con `position: fixed` y coordenadas calculadas desde el campo de
 * búsqueda (`getBoundingClientRect`) — así nunca queda recortada por ningún ancestro con
 * `overflow` acotado, sin importar en qué pantalla se use.
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

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
  /** ADR-246 (petición del usuario): "creatable" — si lo que se escribió no coincide con
   *  ninguna opción, se ofrece un renglón "+ Crear "...""  al final de la lista. El
   *  componente NO sabe cómo se crea (eso lo resuelve quien lo use, p.ej. con una mutación
   *  que da de alta la opción en su catálogo); aquí solo se dispara `onCreate` con el
   *  texto tecleado y se cierra la lista — quien llama decide cuándo/cómo actualizar
   *  `value`/`options` (normalmente al resolver la mutación). */
  onCreate?: (texto: string) => void;
  /** Deshabilita el renglón "+ Crear" mientras la alta está en curso (evita doble-click). */
  creando?: boolean;
}

export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Selecciona…",
  emptyOptionLabel,
  emptyResultsLabel = "Sin resultados.",
  disabled,
  onCreate,
  creando,
}: SearchableSelectProps) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const contenedorRef = useRef<HTMLDivElement>(null);
  // ADR-267: la lista vive en un portal (fuera del DOM de `contenedorRef`) — un `ref`
  // propio para que "clic afuera" no la confunda con "afuera" (ni al elegir un
  // renglón, ni al arrastrar su propia barra de scroll interna).
  const listaRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number; width: number } | null>(null);

  const seleccionada = options.find((o) => o.value === value);

  useEffect(() => {
    if (!abierto) return;
    function alHacerClicFuera(e: MouseEvent) {
      const target = e.target as Node;
      if (contenedorRef.current?.contains(target)) return;
      if (listaRef.current?.contains(target)) return;
      setAbierto(false);
      setQuery("");
    }
    document.addEventListener("mousedown", alHacerClicFuera);
    return () => document.removeEventListener("mousedown", alHacerClicFuera);
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;
    const actualizarCoords = () => {
      const rect = contenedorRef.current?.getBoundingClientRect();
      if (rect) setCoords({ top: rect.bottom + 2, left: rect.left, width: rect.width });
    };
    actualizarCoords();
    // `true` = fase de captura: un scroll en CUALQUIER ancestro (no solo `window`)
    // dispara este listener — si no, el panel (en un portal, fuera del flujo normal del
    // formulario) se quedaría flotando en la posición vieja al desplazarse el panel que
    // lo contiene.
    window.addEventListener("scroll", actualizarCoords, true);
    window.addEventListener("resize", actualizarCoords);
    return () => {
      window.removeEventListener("scroll", actualizarCoords, true);
      window.removeEventListener("resize", actualizarCoords);
    };
  }, [abierto]);

  const filtradas = query.trim()
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  const textoQuery = query.trim();
  const yaExiste = options.some((o) => o.label.toLowerCase() === textoQuery.toLowerCase());
  const ofrecerCrear = Boolean(onCreate) && textoQuery.length > 0 && !yaExiste;

  const elegir = (v: string) => {
    onChange(v);
    setAbierto(false);
    setQuery("");
  };

  const crear = () => {
    if (creando) return;
    onCreate?.(textoQuery);
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
        value={abierto ? query : seleccionada?.label ?? value}
        onFocus={() => setAbierto(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setAbierto(true);
        }}
      />
      {abierto &&
        coords &&
        createPortal(
          <div
            ref={listaRef}
            className="ssel-list"
            style={{ position: "fixed", top: coords.top, left: coords.left, right: "auto", width: coords.width }}
          >
            <div className="ssel-item ssel-item-muted" onMouseDown={() => elegir("")}>
              {emptyOptionLabel ?? placeholder}
            </div>
            {filtradas.map((o) => (
              <div key={o.value} className="ssel-item" onMouseDown={() => elegir(o.value)}>
                {o.label}
              </div>
            ))}
            {filtradas.length === 0 && !ofrecerCrear && (
              <div className="ssel-empty">{emptyResultsLabel}</div>
            )}
            {ofrecerCrear && (
              <div className="ssel-item ssel-item-crear" onMouseDown={crear}>
                {creando ? "Creando…" : `+ Crear "${textoQuery}"`}
              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
