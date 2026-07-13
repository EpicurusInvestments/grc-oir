/** Formulario de alta/edición de Anunciante (React Hook Form + Zod).
 *
 * Refleja el backend: nombre comercial y fiscal (req.), RFC (12-13), agencia opcional
 * (— Sin agencia — = directo), contactos y `dias_credito_default`. Ese último es PARÁMETRO
 * SENSIBLE: se muestra con `SensitiveField` (tag «Audit log») y, en EDICIÓN, exige "Motivo
 * del cambio" SOLO si el valor cambia. Errores de negocio llegan por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SensitiveField } from "@/shared/ui";

import type { AnuncianteCreate } from "../types";

export type AnuncianteFormOutput = AnuncianteCreate & { motivo_cambio?: string | null };

/** Opción mínima de agencia para el select. */
export interface AgenciaOpcion {
  agencia_id: string;
  nombre_agencia: string;
}

const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;
const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function buildSchema(isEdit: boolean, diasOriginal?: string) {
  return z
    .object({
      nombre_comercial: z.string().trim().min(1, "El nombre comercial es obligatorio.").max(200),
      nombre_fiscal: z
        .string()
        .trim()
        .min(1, "El nombre fiscal / razón social es obligatorio.")
        .max(250),
      rfc_anunciante: z
        .string()
        .trim()
        .regex(RFC_REGEX, "RFC inválido (formato mexicano de 12-13 caracteres)."),
      agencia_id: z.string().optional(), // "" = directo
      localizacion: z.string().trim().max(250).optional(),
      referencia_anunciante: z.string().trim().max(250).optional(),
      contacto_nombre: z.string().trim().max(160).optional(),
      contacto_email: z
        .string()
        .trim()
        .max(160)
        .refine((v) => v === "" || EMAIL_REGEX.test(v), "Correo inválido.")
        .optional(),
      contacto_telefono: z.string().trim().max(40).optional(),
      dias_credito_default: z
        .string()
        .trim()
        .min(1, "Los días de crédito son obligatorios.")
        .refine((v) => {
          const n = Number(v);
          return Number.isInteger(n) && n >= 0 && n <= 3650;
        }, "Debe ser un entero ≥ 0."),
      motivo_cambio: z.string().trim().max(500).optional(),
    })
    .superRefine((d, ctx) => {
      if (
        isEdit &&
        diasOriginal !== undefined &&
        d.dias_credito_default !== diasOriginal &&
        !d.motivo_cambio?.trim()
      ) {
        ctx.addIssue({
          path: ["motivo_cambio"],
          code: z.ZodIssueCode.custom,
          message: "Indica el motivo del cambio de días de crédito.",
        });
      }
    });
}

type AnuncianteFormValues = z.infer<ReturnType<typeof buildSchema>>;

interface AnuncianteFormProps {
  title: string;
  agencias: AgenciaOpcion[];
  defaultValues?: Partial<AnuncianteFormValues>;
  diasOriginal?: string;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: AnuncianteFormOutput) => void;
  onCancel: () => void;
}

export function AnuncianteForm({
  title,
  agencias,
  defaultValues,
  diasOriginal,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: AnuncianteFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<AnuncianteFormValues>({
    resolver: zodResolver(buildSchema(isEdit, diasOriginal)),
    defaultValues: {
      nombre_comercial: "",
      nombre_fiscal: "",
      rfc_anunciante: "",
      agencia_id: "",
      localizacion: "",
      referencia_anunciante: "",
      contacto_nombre: "",
      contacto_email: "",
      contacto_telefono: "",
      dias_credito_default: "0",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  const diasCambiados =
    isEdit && diasOriginal !== undefined && watch("dias_credito_default") !== diasOriginal;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    onSubmit({
      nombre_comercial: data.nombre_comercial.trim(),
      nombre_fiscal: data.nombre_fiscal.trim(),
      rfc_anunciante: data.rfc_anunciante.toUpperCase(),
      agencia_id: data.agencia_id?.trim() ? data.agencia_id : null,
      localizacion: data.localizacion?.trim() || null,
      referencia_anunciante: data.referencia_anunciante?.trim() || null,
      contacto_nombre: data.contacto_nombre?.trim() || null,
      contacto_email: data.contacto_email?.trim() || null,
      contacto_telefono: data.contacto_telefono?.trim() || null,
      dias_credito_default: Number(data.dias_credito_default),
      ...(isEdit && motivo ? { motivo_cambio: motivo } : {}),
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Identificación</div>

        <div className="fl fl-required">Nombre comercial</div>
        <input className="fi" autoFocus {...register("nombre_comercial")} />
        <div className="fe">{errors.nombre_comercial?.message}</div>

        <div className="fl fl-required">Nombre fiscal / Razón social</div>
        <input className="fi" {...register("nombre_fiscal")} />
        <div className="fe">{errors.nombre_fiscal?.message}</div>

        <div className="r2">
          <div>
            <div className="fl fl-required">RFC</div>
            <input
              className="fi"
              maxLength={13}
              style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
              {...register("rfc_anunciante")}
            />
            <div className="fe">{errors.rfc_anunciante?.message}</div>
          </div>
          <div>
            <div className="fl">Referencia interna</div>
            <input className="fi" {...register("referencia_anunciante")} />
            <div className="fe">{errors.referencia_anunciante?.message}</div>
          </div>
        </div>

        <div className="fl">Localización</div>
        <input
          className="fi"
          placeholder="Ciudad, estado o dirección"
          {...register("localizacion")}
        />
        <div className="fe">{errors.localizacion?.message}</div>

        <div className="sec">Relación comercial</div>
        <div className="fl">Agencia que lo representa</div>
        <select className="fsel" {...register("agencia_id")}>
          <option value="">— Sin agencia (directo) —</option>
          {agencias.map((g) => (
            <option key={g.agencia_id} value={g.agencia_id}>
              {g.nombre_agencia}
            </option>
          ))}
        </select>
        <div className="fe" />

        <div className="sec">Contacto</div>
        <div className="fl">Nombre</div>
        <input className="fi" {...register("contacto_nombre")} />
        <div className="fe">{errors.contacto_nombre?.message}</div>

        <div className="fl">Correo</div>
        <input className="fi" {...register("contacto_email")} />
        <div className="fe">{errors.contacto_email?.message}</div>

        <div className="fl">Teléfono</div>
        <input className="fi" {...register("contacto_telefono")} />
        <div className="fe">{errors.contacto_telefono?.message}</div>

        <div className="sec">Condiciones default</div>
        <SensitiveField
          label="Días de crédito (default)"
          required
          inputMode="numeric"
          placeholder="0"
          hint="Valor sugerido al crear cobranzas. Puede sobreescribirse por factura."
          register={register("dias_credito_default")}
          error={errors.dias_credito_default?.message}
          motivo={
            diasCambiados
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
