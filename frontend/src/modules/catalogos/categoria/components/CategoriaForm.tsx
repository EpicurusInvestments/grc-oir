/** Formulario de alta/edición de Categoria (React Hook Form + Zod). Refleja el backend:
 * nombre requerido (≤160, único CI — lo valida el backend) y descripción opcional. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { CategoriaCreate } from "../types";

const schema = z.object({
  nombre_categoria: z.string().trim().min(1, "El nombre es obligatorio.").max(160),
  descripcion_categoria: z.string().trim().optional(),
});

type CategoriaFormValues = z.infer<typeof schema>;

interface CategoriaFormProps {
  title: string;
  defaultValues?: Partial<CategoriaFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: CategoriaCreate) => void;
  onCancel: () => void;
}

export function CategoriaForm({
  title,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: CategoriaFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CategoriaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { nombre_categoria: "", descripcion_categoria: "", ...defaultValues },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_categoria: data.nombre_categoria.trim(),
      descripcion_categoria: data.descripcion_categoria?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos de la categoría</div>

        <div className="fl fl-required">Nombre</div>
        <input className="fi" autoFocus {...register("nombre_categoria")} />
        <div className="fe">{errors.nombre_categoria?.message}</div>

        <div className="fl">Descripción</div>
        <textarea
          className="fi"
          rows={3}
          style={{ height: "auto", minHeight: 62, paddingTop: 8, resize: "vertical" }}
          {...register("descripcion_categoria")}
        />
        <div className="fe">{errors.descripcion_categoria?.message}</div>
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
