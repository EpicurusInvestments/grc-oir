/** Selector MÚLTIPLE por checkboxes — mismo espíritu que `MultiSearchableSelect`, pero
 * con el patrón de un desplegable de casillas (buscador + "Selecciona todos" + lista con
 * check de cada opción) en vez de chips removibles (ADR-187, petición del usuario:
 * "Material a Transmitir" de `PeriodoTransmisionGrid.tsx`). El campo cerrado muestra un
 * resumen de lo elegido; al abrir, el panel deja marcar/desmarcar cualquier opción.
 */

import { useEffect, useRef, useState } from "react";

import type { OpcionBuscable } from "./SearchableSelect";

/** ADR-187 (petición del usuario, corrige el primer intento — mostraba TODOS los
 * elegidos separados por coma, haciendo la columna demasiado ancha): abrevia a 20
 * caracteres + "…" tanto el resumen del campo cerrado como cada opción de la lista. */
const LARGO_MAXIMO_LABEL = 20;
function abreviar(texto: string): string {
  return texto.length > LARGO_MAXIMO_LABEL ? `${texto.slice(0, LARGO_MAXIMO_LABEL)}…` : texto;
}

interface CheckboxMultiSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  options: OpcionBuscable[];
  placeholder?: string;
  emptyResultsLabel?: string;
  disabled?: boolean;
  /** Tope de opciones seleccionables (p.ej. no más de 1 por spot del día). Al llegar al
   *  tope, las opciones NO elegidas se muestran deshabilitadas (solo se puede desmarcar,
   *  no agregar una más) y "Selecciona todos" deja de poder marcar de más. */
  maxSelected?: number;
}

export function CheckboxMultiSelect({
  value,
  onChange,
  options,
  placeholder = "Busca y selecciona…",
  emptyResultsLabel = "Sin resultados.",
  disabled,
  maxSelected,
}: CheckboxMultiSelectProps) {
  const [abierto, setAbierto] = useState(false);
  const [query, setQuery] = useState("");
  const contenedorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    function alHacerClicFuera(e: MouseEvent) {
      const contenedor = contenedorRef.current;
      if (!contenedor) return;
      const target = e.target as Node | null;
      if (!target || contenedor.contains(target)) return; // clic adentro, normal
      // Corrige un bug real: la grid vive dentro de un contenedor con scroll propio
      // (`overflow: auto`), y la barra de scroll de un ANCESTRO dispara el `mousedown`
      // con `target` = ese mismo ancestro (no un elemento "afuera" de verdad) — tratarlo
      // como clic afuera cerraba el panel apenas el usuario intentaba arrastrar esa
      // barra para bajar y ver más renglones de la tabla. PERO (corrige una regresión
      // real de ese primer fix): un ancestro también recibe el `mousedown` de un clic
      // genuino en su FONDO (p.ej. el espacio vacío del formulario) — ESE sí debe cerrar
      // el panel. Se distinguen comparando la posición del clic contra el `clientWidth`/
      // `clientHeight` del ancestro (excluye su barra de scroll, a diferencia de
      // `offsetWidth`/`offsetHeight`): si cae DENTRO de esa área, es un clic de verdad
      // sobre el ancestro (cierra); si cae fuera, es la barra de scroll (no cierra).
      if (target instanceof Element && target.contains(contenedor)) {
        const rect = target.getBoundingClientRect();
        const dentroDelContenido =
          e.clientX >= rect.left &&
          e.clientX <= rect.left + target.clientWidth &&
          e.clientY >= rect.top &&
          e.clientY <= rect.top + target.clientHeight;
        if (!dentroDelContenido) return;
      }
      setAbierto(false);
      setQuery("");
    }
    document.addEventListener("mousedown", alHacerClicFuera);
    return () => document.removeEventListener("mousedown", alHacerClicFuera);
  }, [abierto]);

  const alTope = maxSelected != null && value.length >= maxSelected;
  const filtradas = query.trim()
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;
  const todasFiltradasElegidas = filtradas.length > 0 && filtradas.every((o) => value.includes(o.value));

  const alternar = (v: string) => {
    if (value.includes(v)) {
      onChange(value.filter((x) => x !== v));
    } else if (!alTope) {
      onChange([...value, v]);
    }
  };

  const alternarTodas = () => {
    if (todasFiltradasElegidas) {
      const fuera = new Set(filtradas.map((o) => o.value));
      onChange(value.filter((v) => !fuera.has(v)));
      return;
    }
    const yaElegidas = new Set(value);
    const porAgregar = filtradas.filter((o) => !yaElegidas.has(o.value)).map((o) => o.value);
    const cupo = maxSelected != null ? Math.max(0, maxSelected - value.length) : porAgregar.length;
    onChange([...value, ...porAgregar.slice(0, cupo)]);
  };

  // ADR-187: el campo cerrado NUNCA junta todos los elegidos (eso hacía la columna
  // demasiado ancha con 2+ materiales) — muestra solo el PRIMERO, abreviado.
  const primerLabel = options.find((o) => o.value === value[0])?.label;
  const resumen = primerLabel ? abreviar(primerLabel) : "";

  return (
    <div ref={contenedorRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="fi cmsel-campo"
        disabled={disabled}
        title={value.length > 0 ? value.map((v) => options.find((o) => o.value === v)?.label).join(", ") : undefined}
        onClick={() => setAbierto((a) => !a)}
      >
        <span className={resumen ? undefined : "cmsel-placeholder"}>{resumen || placeholder}</span>
      </button>
      {abierto && (
        <div className="cmsel-panel">
          <input
            className="fi"
            style={{ marginBottom: 0 }}
            placeholder="Buscar…"
            autoComplete="off"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="cmsel-item cmsel-todas">
            <input type="checkbox" checked={todasFiltradasElegidas} onChange={alternarTodas} />
            [Selecciona todos]
          </label>
          <div className="cmsel-lista">
            {filtradas.map((o) => {
              const elegida = value.includes(o.value);
              return (
                <label key={o.value} className="cmsel-item" title={o.label}>
                  <input
                    type="checkbox"
                    checked={elegida}
                    disabled={!elegida && alTope}
                    onChange={() => alternar(o.value)}
                  />
                  {abreviar(o.label)}
                </label>
              );
            })}
            {filtradas.length === 0 && <div className="ssel-empty">{emptyResultsLabel}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
