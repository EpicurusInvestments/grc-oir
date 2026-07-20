/** Formulario de alta/edición de CuentaContable (React Hook Form + Zod).
 *
 * Catálogo simple: código (único CI — lo valida el backend), nombre y `tipo_cuenta` como
 * SELECT del ENUM de la spec. Errores de negocio (código duplicado) llegan por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { CuentaContableCreate } from "../types";
import { TIPO_CUENTA_OPCIONES } from "../types";

const schema = z.object({
  codigo_cuenta: z.string().trim().min(1, "El código es obligatorio.").max(40),
  nombre_cuenta: z.string().trim().min(1, "El nombre es obligatorio.").max(200),
  tipo_cuenta: z.enum(["ingreso", "costo", "gasto", "activo", "pasivo"]),
});

type CuentaContableFormValues = z.infer<typeof schema>;

interface CuentaContableFormProps {
  title: string;
  defaultValues?: Partial<CuentaContableFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: CuentaContableCreate) => void;
  onCancel: () => void;
}

export function CuentaContableForm({
  title,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: CuentaContableFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CuentaContableFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      codigo_cuenta: "",
      nombre_cuenta: "",
      tipo_cuenta: "ingreso",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      codigo_cuenta: data.codigo_cuenta.trim(),
      nombre_cuenta: data.nombre_cuenta.trim(),
      tipo_cuenta: data.tipo_cuenta,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos de la cuenta</div>

        <div className="fl fl-required">Código de cuenta</div>
        <input className="fi mono" autoFocus {...register("codigo_cuenta")} />
        <div className="fe">{errors.codigo_cuenta?.message}</div>

        <div className="fl fl-required">Nombre de cuenta</div>
        <input className="fi" {...register("nombre_cuenta")} />
        <div className="fe">{errors.nombre_cuenta?.message}</div>

        <div className="fl fl-required">Tipo de cuenta</div>
        <select className="fsel" {...register("tipo_cuenta")}>
          {TIPO_CUENTA_OPCIONES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="fe">{errors.tipo_cuenta?.message}</div>
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
