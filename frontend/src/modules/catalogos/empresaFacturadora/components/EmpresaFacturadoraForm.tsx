/** Formulario de alta/edición de EmpresaFacturadora (React Hook Form + Zod). Refleja el
 * backend: nombre requerido (≤200), RFC MX 12-13 (único — lo valida el backend) y dirección
 * opcional (texto largo). */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { EmpresaFacturadoraCreate } from "../types";

const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;

const schema = z.object({
  nombre_empresa: z.string().trim().min(1, "El nombre es obligatorio.").max(200),
  rfc_empresa: z
    .string()
    .trim()
    .regex(RFC_REGEX, "RFC inválido (formato mexicano de 12-13 caracteres)."),
  direccion_empresa: z.string().trim().optional(),
});

type EmpresaFacturadoraFormValues = z.infer<typeof schema>;

interface EmpresaFacturadoraFormProps {
  title: string;
  defaultValues?: Partial<EmpresaFacturadoraFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: EmpresaFacturadoraCreate) => void;
  onCancel: () => void;
}

export function EmpresaFacturadoraForm({
  title,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: EmpresaFacturadoraFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EmpresaFacturadoraFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_empresa: "",
      rfc_empresa: "",
      direccion_empresa: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_empresa: data.nombre_empresa.trim(),
      rfc_empresa: data.rfc_empresa.toUpperCase(),
      direccion_empresa: data.direccion_empresa?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos fiscales</div>

        <div className="fl fl-required">Nombre / Razón social</div>
        <input className="fi" autoFocus {...register("nombre_empresa")} />
        <div className="fe">{errors.nombre_empresa?.message}</div>

        <div className="fl fl-required">RFC</div>
        <input
          className="fi"
          maxLength={13}
          style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
          {...register("rfc_empresa")}
        />
        <div className="fe">{errors.rfc_empresa?.message}</div>

        <div className="fl">Dirección</div>
        <textarea
          className="fi"
          rows={3}
          style={{ height: "auto", minHeight: 62, paddingTop: 8, resize: "vertical" }}
          {...register("direccion_empresa")}
        />
        <div className="fe">{errors.direccion_empresa?.message}</div>
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
