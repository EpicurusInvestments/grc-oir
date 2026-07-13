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
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SensitiveField } from "@/shared/ui";

import type { AgenciaCreate } from "../types";

export type AgenciaFormOutput = AgenciaCreate & { motivo_cambio?: string | null };

function buildSchema(isEdit: boolean, comisionOriginal?: string) {
  return z
    .object({
      nombre_agencia: z.string().trim().min(1, "El nombre de la agencia es obligatorio.").max(200),
      rfc_agencia: z
        .string()
        .trim()
        .min(12, "El RFC debe tener 12 o 13 caracteres.")
        .max(13, "El RFC debe tener 12 o 13 caracteres."),
      contacto_nombre: z.string().trim().max(160).optional(),
      contacto_email: z.string().trim().max(160).optional(),
      contacto_telefono: z.string().trim().max(40).optional(),
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
  defaultValues?: Partial<AgenciaFormValues>;
  /** % original (en edición) para decidir si el motivo es obligatorio. */
  comisionOriginal?: string;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: AgenciaFormOutput) => void;
  onCancel: () => void;
}

export function AgenciaForm({
  title,
  defaultValues,
  comisionOriginal,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: AgenciaFormProps) {
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
      contacto_nombre: "",
      contacto_email: "",
      contacto_telefono: "",
      porcentaje_comision_agencia_default: "0",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  // El "Motivo del cambio" solo aparece (y es obligatorio) al MODIFICAR el % en edición.
  const comisionCambiada =
    isEdit &&
    comisionOriginal !== undefined &&
    watch("porcentaje_comision_agencia_default") !== comisionOriginal;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    onSubmit({
      nombre_agencia: data.nombre_agencia.trim(),
      rfc_agencia: data.rfc_agencia.trim(),
      contacto_nombre: data.contacto_nombre?.trim() || null,
      contacto_email: data.contacto_email?.trim() || null,
      contacto_telefono: data.contacto_telefono?.trim() || null,
      porcentaje_comision_agencia_default: data.porcentaje_comision_agencia_default.trim(),
      ...(isEdit && motivo ? { motivo_cambio: motivo } : {}),
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
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
          style={{ fontFamily: "var(--mono)" }}
          {...register("rfc_agencia")}
        />
        <div className="fe">{errors.rfc_agencia?.message}</div>

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

        <div className="sec">Contacto</div>
        <div className="fl">Nombre</div>
        <input className="fi" {...register("contacto_nombre")} />
        <div className="fe">{errors.contacto_nombre?.message}</div>

        <div className="fl">Correo</div>
        <input className="fi" type="email" {...register("contacto_email")} />
        <div className="fe">{errors.contacto_email?.message}</div>

        <div className="fl">Teléfono</div>
        <input className="fi" {...register("contacto_telefono")} />
        <div className="fe">{errors.contacto_telefono?.message}</div>
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
          <button type="submit" className="btn btn-sm btn-phase" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
