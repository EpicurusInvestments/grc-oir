/** Formulario de alta/edición de Contrato (React Hook Form + Zod).
 *
 * Refleja el backend: anunciante (req.), número y nombre (req.), fechas con
 * `fecha_fin >= fecha_inicio`, monto y condiciones/observaciones opcionales, y
 * `porcentaje_comision_contrato` (PARÁMETRO SENSIBLE, opcional) con `SensitiveField` — el
 * "Motivo del cambio" aparece solo al modificar el %. `estado_contrato` NO se edita aquí
 * (se transiciona desde el panel). Errores de negocio llegan por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SensitiveField } from "@/shared/ui";

import type { ContratoCreate } from "../types";

export type ContratoFormOutput = ContratoCreate & { motivo_cambio?: string | null };

export interface AnuncianteOpcion {
  anunciante_id: string;
  nombre_comercial: string;
}

const numeroOpcional = (msg: string, max = 100) =>
  z
    .string()
    .trim()
    .optional()
    .refine((v) => v == null || v === "" || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= max), msg);

function buildSchema(isEdit: boolean, comisionOriginal?: string) {
  return z
    .object({
      anunciante_id: z.string().min(1, "Selecciona un anunciante."),
      numero_contrato: z.string().trim().min(1, "El número es obligatorio.").max(60),
      nombre_contrato: z.string().trim().min(1, "El nombre es obligatorio.").max(200),
      fecha_inicio_contrato: z.string().min(1, "La fecha de inicio es obligatoria."),
      fecha_fin_contrato: z.string().min(1, "La fecha de fin es obligatoria."),
      monto_contrato: numeroOpcional("Monto inválido (número ≥ 0).", 9_999_999_999),
      porcentaje_comision_contrato: numeroOpcional("El % debe estar entre 0 y 100.", 100),
      condiciones_comerciales: z.string().trim().max(4000).optional(),
      observaciones_contrato: z.string().trim().max(1000).optional(),
      motivo_cambio: z.string().trim().max(500).optional(),
    })
    .refine((d) => d.fecha_fin_contrato >= d.fecha_inicio_contrato, {
      path: ["fecha_fin_contrato"],
      message: "La fecha de fin debe ser mayor o igual que la de inicio.",
    })
    .superRefine((d, ctx) => {
      const actual = d.porcentaje_comision_contrato?.trim() ?? "";
      if (isEdit && comisionOriginal !== undefined && actual !== comisionOriginal && !d.motivo_cambio?.trim()) {
        ctx.addIssue({
          path: ["motivo_cambio"],
          code: z.ZodIssueCode.custom,
          message: "Indica el motivo del cambio de % de comisión.",
        });
      }
    });
}

type ContratoFormValues = z.infer<ReturnType<typeof buildSchema>>;

interface ContratoFormProps {
  title: string;
  anunciantes: AnuncianteOpcion[];
  defaultValues?: Partial<ContratoFormValues>;
  comisionOriginal?: string;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: ContratoFormOutput) => void;
  onCancel: () => void;
}

export function ContratoForm({
  title,
  anunciantes,
  defaultValues,
  comisionOriginal,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: ContratoFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ContratoFormValues>({
    resolver: zodResolver(buildSchema(isEdit, comisionOriginal)),
    defaultValues: {
      anunciante_id: "",
      numero_contrato: "",
      nombre_contrato: "",
      fecha_inicio_contrato: "",
      fecha_fin_contrato: "",
      monto_contrato: "",
      porcentaje_comision_contrato: "",
      condiciones_comerciales: "",
      observaciones_contrato: "",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  const comisionCambiada =
    isEdit &&
    comisionOriginal !== undefined &&
    (watch("porcentaje_comision_contrato")?.trim() ?? "") !== comisionOriginal;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    onSubmit({
      anunciante_id: data.anunciante_id,
      numero_contrato: data.numero_contrato.trim(),
      nombre_contrato: data.nombre_contrato.trim(),
      fecha_inicio_contrato: data.fecha_inicio_contrato,
      fecha_fin_contrato: data.fecha_fin_contrato,
      monto_contrato: data.monto_contrato?.trim() || null,
      porcentaje_comision_contrato: data.porcentaje_comision_contrato?.trim() || null,
      condiciones_comerciales: data.condiciones_comerciales?.trim() || null,
      observaciones_contrato: data.observaciones_contrato?.trim() || null,
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

        <div className="fl fl-required">Anunciante</div>
        <select className="fsel" autoFocus {...register("anunciante_id")}>
          <option value="">Selecciona…</option>
          {anunciantes.map((a) => (
            <option key={a.anunciante_id} value={a.anunciante_id}>
              {a.nombre_comercial}
            </option>
          ))}
        </select>
        <div className="fe">{errors.anunciante_id?.message}</div>

        <div className="r2">
          <div>
            <div className="fl fl-required">Número de contrato</div>
            <input
              className="fi"
              style={{ fontFamily: "var(--mono)" }}
              placeholder="CT-2026-001"
              {...register("numero_contrato")}
            />
            <div className="fe">{errors.numero_contrato?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Nombre del contrato</div>
            <input className="fi" {...register("nombre_contrato")} />
            <div className="fe">{errors.nombre_contrato?.message}</div>
          </div>
        </div>

        <div className="sec">Vigencia y monto</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Inicio</div>
            <input className="fi" type="date" {...register("fecha_inicio_contrato")} />
            <div className="fe">{errors.fecha_inicio_contrato?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Fin</div>
            <input className="fi" type="date" {...register("fecha_fin_contrato")} />
            <div className="fe">{errors.fecha_fin_contrato?.message}</div>
          </div>
        </div>

        <div className="fl">Monto del contrato (MXN)</div>
        <input
          className="fi"
          inputMode="decimal"
          placeholder="0.00"
          style={{ fontFamily: "var(--mono)" }}
          {...register("monto_contrato")}
        />
        <div className="fe">{errors.monto_contrato?.message}</div>

        <SensitiveField
          label="% comisión específica del contrato"
          inputMode="decimal"
          placeholder="(opcional) sobreescribe el default de la agencia"
          hint="Si se captura, sobreescribe el % por defecto de la agencia."
          register={register("porcentaje_comision_contrato")}
          error={errors.porcentaje_comision_contrato?.message}
          motivo={
            comisionCambiada
              ? { register: register("motivo_cambio"), error: errors.motivo_cambio?.message }
              : undefined
          }
        />

        <div className="sec">Condiciones y observaciones</div>
        <div className="fl">Condiciones comerciales</div>
        <textarea
          className="fi"
          rows={3}
          style={{ height: "auto", minHeight: 62, paddingTop: 8, resize: "vertical" }}
          {...register("condiciones_comerciales")}
        />
        <div className="fe">{errors.condiciones_comerciales?.message}</div>

        <div className="fl">Observaciones</div>
        <textarea
          className="fi"
          rows={2}
          style={{ height: "auto", minHeight: 48, paddingTop: 8, resize: "vertical" }}
          {...register("observaciones_contrato")}
        />
        <div className="fe">{errors.observaciones_contrato?.message}</div>
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
