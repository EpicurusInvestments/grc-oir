/** Formulario de alta/edición de Agencia (React Hook Form + Zod).
 *
 * Refleja las validaciones del backend: nombre (req., único, ≤200), RFC (12-13),
 * contactos opcionales y `porcentaje_comision_agencia_default` (0–100, string). Ese % es
 * PARÁMETRO SENSIBLE: se muestra con el componente `SensitiveField` (tag «Audit log») y,
 * en EDICIÓN, exige "Motivo del cambio" SOLO si el valor cambia (el backend lo requiere y
 * responde 400 si falta). Los errores de negocio (409 nombre duplicado, 422 RFC) llegan
 * por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay, SensitiveField } from "@/shared/ui";

import { useConstantes } from "../../constantesSistema/hooks";
import type { AgenciaCreate } from "../types";
import type { ContactoFormData } from "./ContactoInlineForm";
import { ContactosSection } from "./ContactosSection";

export type AgenciaFormOutput = AgenciaCreate & { motivo_cambio?: string | null };

// Mismo patrón que `AnuncianteForm`: el backend rechaza (422 genérico, sin campo
// señalado) cualquier RFC que no cumpla el formato oficial MX, no solo la longitud. Sin
// esta regex, un RFC de 12-13 caracteres pero con la forma equivocada (p.ej. 5 letras en
// vez de 3-4 antes de la fecha) pasaba la validación del front y tronaba hasta el back
// con "Datos de entrada inválidos" — sin decir por qué ni en qué campo.
const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;

function buildSchema(isEdit: boolean, comisionOriginal?: string) {
  return z
    .object({
      nombre_agencia: z.string().trim().min(1, "El nombre de la agencia es obligatorio.").max(200),
      rfc_agencia: z
        .string()
        .trim()
        .regex(
          RFC_REGEX,
          "RFC inválido: 3-4 letras + 6 dígitos (fecha AAMMDD) + 3 alfanuméricos (homoclave).",
        ),
      // Clave SAT (c_RegimenFiscal), sugerida desde ConstantesSistema, sin FK formal.
      regimen_fiscal: z.string().trim().max(4).optional(),
      porcentaje_comision_agencia_default: z
        .string()
        .trim()
        .min(1, "El % de comisión es obligatorio.")
        .refine((v) => {
          const n = Number(v);
          return Number.isFinite(n) && n >= 0 && n <= 100;
        }, "El % debe estar entre 0 y 100."),
      motivo_cambio: z.string().trim().max(500).optional(),
    })
    .superRefine((d, ctx) => {
      // En edición, si el % cambia respecto al valor original, el motivo es obligatorio.
      if (
        isEdit &&
        comisionOriginal !== undefined &&
        d.porcentaje_comision_agencia_default !== comisionOriginal &&
        !d.motivo_cambio?.trim()
      ) {
        ctx.addIssue({
          path: ["motivo_cambio"],
          code: z.ZodIssueCode.custom,
          message: "Indica el motivo del cambio de % de comisión.",
        });
      }
    });
}

type AgenciaFormValues = z.infer<ReturnType<typeof buildSchema>>;

interface AgenciaFormProps {
  title: string;
  /** Presente SOLO en edición: habilita la sección "Contactos" en modo servidor. En alta
   *  (`undefined`/`null`) los contactos se capturan en memoria y se crean justo después
   *  de guardar la agencia. */
  agenciaId?: string | null;
  defaultValues?: Partial<AgenciaFormValues>;
  /** % original (en edición) para decidir si el motivo es obligatorio. */
  comisionOriginal?: string;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  /** `contactosNuevos` solo trae algo en ALTA; en edición siempre llega vacío, porque ahí
   *  ya se sincronizan solos contra el backend. */
  onSubmit: (data: AgenciaFormOutput, contactosNuevos: ContactoFormData[]) => void;
  onCancel: () => void;
}

export function AgenciaForm({
  title,
  agenciaId = null,
  defaultValues,
  comisionOriginal,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: AgenciaFormProps) {
  const [contactosNuevos, setContactosNuevos] = useState<ContactoFormData[]>([]);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<AgenciaFormValues>({
    resolver: zodResolver(buildSchema(isEdit, comisionOriginal)),
    defaultValues: {
      nombre_agencia: "",
      rfc_agencia: "",
      regimen_fiscal: "",
      porcentaje_comision_agencia_default: "0",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  const { useList } = useConstantes();
  const regimenes = useList({ grupo: "RegimenFiscal", activo: true, size: 100 });

  // El "Motivo del cambio" solo aparece (y es obligatorio) al MODIFICAR el % en edición.
  const comisionCambiada =
    isEdit &&
    comisionOriginal !== undefined &&
    watch("porcentaje_comision_agencia_default") !== comisionOriginal;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    onSubmit(
      {
        nombre_agencia: data.nombre_agencia.trim(),
        rfc_agencia: data.rfc_agencia.toUpperCase(),
        regimen_fiscal: data.regimen_fiscal?.trim() || null,
        porcentaje_comision_agencia_default: data.porcentaje_comision_agencia_default.trim(),
        ...(isEdit && motivo ? { motivo_cambio: motivo } : {}),
      },
      contactosNuevos,
    );
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos fiscales</div>

        <div className="fl fl-required">Nombre de la agencia</div>
        <input className="fi" autoFocus {...register("nombre_agencia")} />
        <div className="fe">{errors.nombre_agencia?.message}</div>

        <div className="fl fl-required">RFC</div>
        <input
          className="fi"
          placeholder="XXX000000XXX"
          maxLength={13}
          style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
          {...register("rfc_agencia")}
        />
        <div className="fe">{errors.rfc_agencia?.message}</div>

        <div className="fl">Régimen fiscal (como receptora)</div>
        <select className="fsel" {...register("regimen_fiscal")}>
          <option value="">— Sin capturar —</option>
          {(regimenes.data?.items ?? []).map((c) => (
            <option key={c.clave} value={c.clave}>
              {c.clave} · {c.descripcion}
            </option>
          ))}
        </select>
        <div className="fe">{errors.regimen_fiscal?.message}</div>

        <div className="sec">Comisión</div>
        <SensitiveField
          label="% comisión por defecto"
          required
          inputMode="decimal"
          placeholder="0.00"
          register={register("porcentaje_comision_agencia_default")}
          error={errors.porcentaje_comision_agencia_default?.message}
          motivo={
            comisionCambiada
              ? {
                  register: register("motivo_cambio"),
                  error: errors.motivo_cambio?.message,
                }
              : undefined
          }
        />

        <ContactosSection
          agenciaId={isEdit ? agenciaId : null}
          canWrite
          contactosNuevos={contactosNuevos}
          onContactosNuevosChange={setContactosNuevos}
        />
      </div>

      <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {submitError && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {submitError}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-sm btn-teal" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
