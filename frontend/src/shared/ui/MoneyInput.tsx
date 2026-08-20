/** Input de captura de dinero (MXN): mientras se edita muestra el número plano (fácil de
 * escribir); al perder el foco lo formatea con separador de miles y 2 decimales. El
 * símbolo "$" queda fijo a la izquierda en todo momento. El valor que entra/sale por
 * `value`/`onChange` es SIEMPRE el string numérico plano (compatible con los esquemas Zod
 * existentes `z.string().refine(Number.isFinite...)` y con `Number(valor)` al enviar).
 */

import { useState } from "react";
import type { InputHTMLAttributes } from "react";

function formatearMonto(v: string): string {
  const n = Number(v);
  if (v.trim() === "" || !Number.isFinite(n)) return v;
  return n.toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Deja pasar solo dígitos y un único punto decimal (evita basura mientras se escribe). */
function sanear(v: string): string {
  const limpio = v.replace(/[^\d.]/g, "");
  const primerPunto = limpio.indexOf(".");
  if (primerPunto === -1) return limpio;
  return limpio.slice(0, primerPunto + 1) + limpio.slice(primerPunto + 1).replace(/\./g, "");
}

interface MoneyInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> {
  value: string;
  onChange: (v: string) => void;
}

export function MoneyInput({ value, onChange, className, onFocus, onBlur, ...rest }: MoneyInputProps) {
  const [editando, setEditando] = useState(false);

  return (
    <div className="money-wrap">
      <span className="money-prefix">$</span>
      <input
        type="text"
        inputMode="decimal"
        className={`fi money-fi ${className ?? ""}`}
        value={editando ? value : formatearMonto(value)}
        onFocus={(e) => {
          setEditando(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setEditando(false);
          onBlur?.(e);
        }}
        onChange={(e) => onChange(sanear(e.target.value))}
        {...rest}
      />
    </div>
  );
}
