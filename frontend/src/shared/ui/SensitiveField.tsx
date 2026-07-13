/** Campo de PARÁMETRO SENSIBLE (F0-03): entrada + tag «Audit log» + captura de "Motivo del
 * cambio".
 *
 * Los campos sensibles (p.ej. % de comisión, días de crédito) se auditan en el backend:
 * al modificarlos se registra el cambio en `LogCambioParametro` y se exige un motivo. Este
 * componente hace visible ese contrato en la UI:
 *  - marca el campo con el tag «Audit log»;
 *  - en EDICIÓN (`motivo` presente) muestra el campo "Motivo del cambio" (requerido si el
 *    valor cambia — la validación de "requerido" la decide el formulario que lo usa).
 *
 * Es presentacional y compatible con React Hook Form: se le pasan los `register(...)` del
 * valor y (opcionalmente) del motivo. Pensado para reutilizarse en Agencia, Anunciante
 * (días de crédito) y Contrato (% de comisión).
 */

import type { UseFormRegisterReturn } from "react-hook-form";

import { FieldTag } from "./FieldTag";

interface SensitiveFieldProps {
  label: string;
  /** Registro RHF del campo sensible (valor). */
  register: UseFormRegisterReturn;
  error?: string;
  required?: boolean;
  inputMode?: "decimal" | "numeric";
  placeholder?: string;
  /** Texto de ayuda opcional bajo la etiqueta (p.ej. unidad o rango). */
  hint?: string;
  /** Si se pasa, se muestra el campo "Motivo del cambio" (solo en edición). */
  motivo?: { register: UseFormRegisterReturn; error?: string };
}

export function SensitiveField({
  label,
  register,
  error,
  required,
  inputMode = "decimal",
  placeholder,
  hint,
  motivo,
}: SensitiveFieldProps) {
  return (
    <>
      <div className={`fl ${required ? "fl-required" : ""}`}>
        {label} <FieldTag origin="audit" />
      </div>
      {hint && (
        <div className="fv muted" style={{ marginTop: -2, marginBottom: 4, fontSize: 11 }}>
          {hint}
        </div>
      )}
      <input
        className="fi"
        inputMode={inputMode}
        placeholder={placeholder}
        style={{ fontFamily: "var(--mono)" }}
        {...register}
      />
      <div className="fe">{error}</div>

      {motivo && (
        <>
          <div className="fl fl-required">Motivo del cambio</div>
          <input
            className="fi"
            placeholder="Requerido al modificar el valor…"
            {...motivo.register}
          />
          <div className="fe">{motivo.error}</div>
        </>
      )}
    </>
  );
}
