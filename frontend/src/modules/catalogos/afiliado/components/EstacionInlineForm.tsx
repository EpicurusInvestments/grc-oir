/** Formulario INLINE de estación (dentro del detalle del afiliado).
 *
 * Regla ADR-005: la plaza NO se captura — se hereda del afiliado y se muestra de solo
 * lectura con el tag «Heredado». La razón social también se muestra de solo lectura.
 * Emite solo los campos capturables; el afiliado_id lo fija la pantalla.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag } from "@/shared/ui";

import type { TipoSenal } from "../types";

const schema = z.object({
  nombre_estacion: z.string().trim().min(1, "El nombre/clave es obligatorio.").max(120),
  frecuencia: z.string().trim().max(40).optional(),
  tipo_senal: z.enum(["fm", "am", "tv"]),
});

type EstacionFormValues = z.infer<typeof schema>;

export interface EstacionFormData {
  nombre_estacion: string;
  frecuencia: string | null;
  tipo_senal: TipoSenal;
}

interface EstacionInlineFormProps {
  title: string;
  plazaNombre: string;
  razonSocial: string;
  defaultValues?: Partial<EstacionFormValues>;
  submitting?: boolean;
  onSubmit: (data: EstacionFormData) => void;
  onCancel: () => void;
}

export function EstacionInlineForm({
  title,
  plazaNombre,
  razonSocial,
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
}: EstacionInlineFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EstacionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { nombre_estacion: "", frecuencia: "", tipo_senal: "fm", ...defaultValues },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_estacion: data.nombre_estacion,
      frecuencia: data.frecuencia?.trim() || null,
      tipo_senal: data.tipo_senal,
    });
  });

  return (
    <form className="inline-form" onSubmit={submit}>
      <div className="if-title">{title}</div>

      <div className="fl fl-required">Nombre / clave</div>
      <input className="fi" autoFocus placeholder="Ej. XHMT-FM" {...register("nombre_estacion")} />
      <div className="fe">{errors.nombre_estacion?.message}</div>

      <div className="r2">
        <div>
          <div className="fl">Frecuencia</div>
          <input className="fi" placeholder="Ej. 90.1 FM" {...register("frecuencia")} />
          <div className="fe">{errors.frecuencia?.message}</div>
        </div>
        <div>
          <div className="fl fl-required">Tipo de señal</div>
          <select className="fsel" {...register("tipo_senal")}>
            <option value="fm">FM</option>
            <option value="am">AM</option>
            <option value="tv">TV</option>
          </select>
          <div className="fe">{errors.tipo_senal?.message}</div>
        </div>
      </div>

      <div className="fl">
        Plaza <FieldTag origin="heredado" />
      </div>
      <input className="fi" value={plazaNombre} readOnly disabled />

      <div className="fl">Razón social del afiliado</div>
      <input className="fi" value={razonSocial} readOnly disabled />

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 6 }}>
        <button type="button" className="btn btn-xs" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-xs btn-phase" disabled={submitting}>
          {submitting ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
  );
}
