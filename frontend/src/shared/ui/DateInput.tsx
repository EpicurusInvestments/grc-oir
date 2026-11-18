/** Input de captura de fecha (ADR-271c, petición del usuario; formato actualizado a
 * dd/mm/aa en ADR-272 — mismo barrido global que llevó las pantallas de solo lectura a
 * "DD-MMM-AA"): reemplaza `<input type="date">` nativo porque su formato visible lo
 * decide el navegador/SO y no hay forma confiable de forzarlo distinto entre
 * navegadores. Aquí el campo SIEMPRE se ve día/mes/año (2 dígitos de año) para el
 * usuario — el valor que entra/sale por `value`/`onChange` sigue siendo el ISO plano
 * "aaaa-mm-dd" (compatible con los esquemas Zod y los `Date` que ya arma todo el
 * sistema), igual que `MoneyInput` mantiene el string numérico plano aunque muestre
 * "$1,234.56".
 *
 * ADR-272: el formato de SOLO LECTURA se fue a "DD-MMM-AA" (p.ej. "13-feb-26"), pero
 * aquí, en captura, se queda en dd/mm/aa NUMÉRICO — decisión explícita del usuario
 * ("si consideras que el cambio es muy grande y mientras no afecte funcionalidad hazlo,
 * en caso contrario que sea el formato mexicano dd/MM/aa"): enmascarar un nombre de mes
 * en texto mientras se teclea (parsear "feb", autocompletar) habría sido un cambio de
 * riesgo alto a la lógica de captura actual, que solo enmascara dígitos.
 *
 * Se puede escribir el valor a mano (con máscara automática de "/") o elegirlo del
 * calendario (ícono a la derecha) — mismo patrón de popover en portal que
 * `SearchableSelect.tsx` (ADR-267): así nunca se recorta dentro de un panel con scroll
 * acotado (`.db` dentro de `.detail-pane`).
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { DayPicker } from "react-day-picker";
import { es } from "react-day-picker/locale";
import "react-day-picker/style.css";

function formatearParaInput(iso: string): string {
  if (!iso) return "";
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  if (!anio || !mes || !dia) return "";
  return `${dia}/${mes}/${anio.slice(-2)}`;
}

/** Deja solo dígitos (hasta 6: dd+mm+aa) y reinserta las "/" en su posición — mismo
 *  criterio de "sanear mientras se escribe" que `MoneyInput.sanear`. */
function aplicarMascara(crudo: string): string {
  const digitos = crudo.replace(/\D/g, "").slice(0, 6);
  const dia = digitos.slice(0, 2);
  const mes = digitos.slice(2, 4);
  const anio = digitos.slice(4, 6);
  let resultado = dia;
  if (mes) resultado += `/${mes}`;
  if (anio) resultado += `/${anio}`;
  return resultado;
}

/** "dd/mm/aa" completo y real (rechaza "30/02/26") → ISO, o `null` si no está listo. El
 *  año de 2 dígitos siempre se interpreta como 20XX — el sistema no maneja fechas antes
 *  del año 2000. */
function parsearDdMmAa(texto: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{2})$/.exec(texto);
  if (!m) return null;
  const dia = Number(m[1]);
  const mes = Number(m[2]);
  const anio = 2000 + Number(m[3]);
  const d = new Date(anio, mes - 1, dia);
  if (d.getFullYear() !== anio || d.getMonth() !== mes - 1 || d.getDate() !== dia) return null;
  return `${anio}-${m[2]}-${m[1]}`;
}

function parseIsoADate(iso: string): Date | undefined {
  if (!iso) return undefined;
  const [anio, mes, dia] = iso.slice(0, 10).split("-").map(Number);
  if (!anio || !mes || !dia) return undefined;
  return new Date(anio, mes - 1, dia);
}

function formatoIsoLocal(fecha: Date): string {
  const y = fecha.getFullYear();
  const m = String(fecha.getMonth() + 1).padStart(2, "0");
  const d = String(fecha.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

interface DateInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "min" | "max"> {
  value: string;
  onChange: (v: string) => void;
  /** ISO "aaaa-mm-dd": días antes de este quedan deshabilitados en el calendario. */
  min?: string;
  /** ISO "aaaa-mm-dd": días después de este quedan deshabilitados en el calendario. */
  max?: string;
}

export function DateInput({ value, onChange, min, max, className, disabled, onFocus, onBlur, ...rest }: DateInputProps) {
  const [texto, setTexto] = useState(() => formatearParaInput(value));
  const [enfocado, setEnfocado] = useState(false);
  const [abierto, setAbierto] = useState(false);
  const contenedorRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  // El texto solo se resincroniza desde `value` cuando el campo NO se está editando a
  // mano — si no, cada tecleo rebotaría el cursor a la posición 0.
  useEffect(() => {
    if (!enfocado) setTexto(formatearParaInput(value));
  }, [value, enfocado]);

  useEffect(() => {
    if (!abierto) return;
    function alHacerClicFuera(e: MouseEvent) {
      const target = e.target as Node;
      if (contenedorRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setAbierto(false);
    }
    document.addEventListener("mousedown", alHacerClicFuera);
    return () => document.removeEventListener("mousedown", alHacerClicFuera);
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;
    const actualizarCoords = () => {
      const rect = contenedorRef.current?.getBoundingClientRect();
      if (!rect) return;
      // Primera pasada: se asume "abajo"; el `useLayoutEffect` de abajo corrige a
      // "arriba" en cuanto el panel ya está montado y se puede medir su alto real.
      setCoords({ top: rect.bottom + 2, left: rect.left });
    };
    actualizarCoords();
    window.addEventListener("scroll", actualizarCoords, true);
    window.addEventListener("resize", actualizarCoords);
    return () => {
      window.removeEventListener("scroll", actualizarCoords, true);
      window.removeEventListener("resize", actualizarCoords);
    };
  }, [abierto]);

  // Bug real (reportado por el usuario, con captura): el panel siempre se abría hacia
  // abajo sin revisar si había espacio — con el campo cerca del final del formulario
  // (p.ej. "Fecha de la factura" en "Nueva factura"), el mes y los días de la semana
  // cabían pero la cuadrícula de números quedaba fuera de la ventana (recortada por el
  // borde de la pantalla, no por CSS). Aquí, ya con el panel montado y medible, se
  // voltea hacia ARRIBA si no cabe abajo pero sí arriba.
  useLayoutEffect(() => {
    if (!abierto || !coords || !panelRef.current) return;
    const rectCampo = contenedorRef.current?.getBoundingClientRect();
    if (!rectCampo) return;
    const altoPanel = panelRef.current.getBoundingClientRect().height;
    const cabeAbajo = rectCampo.bottom + 2 + altoPanel <= window.innerHeight;
    const nuevoTop = cabeAbajo ? rectCampo.bottom + 2 : Math.max(2, rectCampo.top - altoPanel - 2);
    if (nuevoTop !== coords.top) setCoords((c) => (c ? { ...c, top: nuevoTop } : c));
    // Solo depende de que el panel exista/abra — recalcular en cada cambio de `coords`
    // (incluido el que esta misma corrida produce) es intencional: converge en 1-2
    // pasadas y detecta cuando el usuario navega de mes (el panel no cambia de alto).
  }, [abierto, coords]);

  const manejarCambio = (crudo: string) => {
    // Compatibilidad: un valor ISO "aaaa-mm-dd" puesto de golpe (pruebas automatizadas,
    // o un `paste` de ese formato) se acepta directo, sin pasar por la máscara mm/dd.
    if (/^\d{4}-\d{2}-\d{2}$/.test(crudo)) {
      setTexto(formatearParaInput(crudo));
      onChange(crudo);
      return;
    }
    if (crudo === "") {
      setTexto("");
      onChange("");
      return;
    }
    const enmascarado = aplicarMascara(crudo);
    setTexto(enmascarado);
    const iso = parsearDdMmAa(enmascarado);
    if (iso) onChange(iso);
  };

  const elegirDelCalendario = (fecha: Date | undefined) => {
    if (!fecha) return;
    const iso = formatoIsoLocal(fecha);
    setTexto(formatearParaInput(iso));
    onChange(iso);
    setAbierto(false);
  };

  return (
    <div ref={contenedorRef} className="date-wrap">
      <input
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder="dd/mm/aa"
        className={`fi date-fi ${className ?? ""}`}
        value={texto}
        disabled={disabled}
        onFocus={(e) => {
          setEnfocado(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setEnfocado(false);
          // Si quedó a medias (ni vacío ni una fecha real), se regresa al último valor
          // válido en vez de dejar basura a medio escribir.
          if (texto !== "" && !parsearDdMmAa(texto)) setTexto(formatearParaInput(value));
          onBlur?.(e);
        }}
        onChange={(e) => manejarCambio(e.target.value)}
        {...rest}
      />
      <button
        type="button"
        className="date-icon-btn"
        disabled={disabled}
        tabIndex={-1}
        aria-label="Abrir calendario"
        onClick={() => setAbierto((v) => !v)}
      >
        📅
      </button>
      {abierto &&
        coords &&
        createPortal(
          <div ref={panelRef} className="date-panel rdp-wrapper" style={{ position: "fixed", top: coords.top, left: coords.left }}>
            <DayPicker
              mode="single"
              locale={es}
              selected={parseIsoADate(value)}
              onSelect={elegirDelCalendario}
              defaultMonth={parseIsoADate(value) ?? parseIsoADate(min ?? "") ?? new Date()}
              disabled={
                min || max
                  ? [
                      ...(min ? [{ before: parseIsoADate(min)! }] : []),
                      ...(max ? [{ after: parseIsoADate(max)! }] : []),
                    ]
                  : undefined
              }
            />
          </div>,
          document.body,
        )}
    </div>
  );
}
