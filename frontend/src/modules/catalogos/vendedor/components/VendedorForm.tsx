/** Formulario de alta/edición de Vendedor (React Hook Form + Zod).
 *
 * `porcentaje_comision_default` es PARÁMETRO SENSIBLE: se muestra con `SensitiveField`
 * (tag «Audit log») y, en EDICIÓN, exige "Motivo del cambio" SOLO si el valor cambia
 * (mismo comportamiento que Agencia en F0-03). Errores de negocio llegan por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SensitiveField } from "@/shared/ui";

import type { VendedorCreate } from "../types";

export type VendedorFormOutput = VendedorCreate & { motivo_cambio?: string | null };

const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function buildSchema(isEdit: boolean, comisionOriginal?: string) {
  return z
    .object({
      nombre_vendedor: z.string().trim().min(1, "El nombre es obligatorio.").max(160),
      email_vendedor: z
        .string()
        .trim()
        .max(160)
        .refine((v) => v === "" || EMAIL_REGEX.test(v), "Correo inválido.")
        .optional(),
      porcentaje_comision_default: z
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
      if (
        isEdit &&
        comisionOriginal !== undefined &&
        d.porcentaje_comision_default !== comisionOriginal &&
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

type VendedorFormValues = z.infer<ReturnType<typeof buildSchema>>;

interface VendedorFormProps {
  title: string;
  defaultValues?: Partial<VendedorFormValues>;
  comisionOriginal?: string;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: VendedorFormOutput) => void;
  onCancel: () => void;
}

export function VendedorForm({
  title,
  defaultValues,
  comisionOriginal,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: VendedorFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<VendedorFormValues>({
    resolver: zodResolver(buildSchema(isEdit, comisionOriginal)),
    defaultValues: {
      nombre_vendedor: "",
      email_vendedor: "",
      porcentaje_comision_default: "0",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  const comisionCambiada =
    isEdit &&
    comisionOriginal !== undefined &&
    watch("porcentaje_comision_default") !== comisionOriginal;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    onSubmit({
      nombre_vendedor: data.nombre_vendedor.trim(),
      email_vendedor: data.email_vendedor?.trim() || null,
      porcentaje_comision_default: data.porcentaje_comision_default.trim(),
      ...(isEdit && motivo ? { motivo_cambio: motivo } : {}),
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos del vendedor</div>

        <div className="fl fl-required">Nombre</div>
        <input className="fi" autoFocus {...register("nombre_vendedor")} />
        <div className="fe">{errors.nombre_vendedor?.message}</div>

        <div className="fl">Correo</div>
        <input className="fi" type="email" {...register("email_vendedor")} />
        <div className="fe">{errors.email_vendedor?.message}</div>

        <div className="sec">Comisión</div>
        <SensitiveField
          label="% comisión default"
          required
          inputMode="decimal"
          placeholder="0.00"
          register={register("porcentaje_comision_default")}
          error={errors.porcentaje_comision_default?.message}
          motivo={
            comisionCambiada
              ? { register: register("motivo_cambio"), error: errors.motivo_cambio?.message }
              : undefined
          }
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
          <button type="submit" className="btn btn-sm btn-phase" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
