/** Formulario de alta/edición de Plaza (React Hook Form + Zod). Refleja las validaciones
 * del backend (nombre_plaza requerido ≤120; estado opcional ≤120).
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { PlazaCreate } from "../types";

const schema = z.object({
  nombre_plaza: z.string().trim().min(1, "El nombre de la plaza es obligatorio.").max(120),
  estado: z.string().trim().max(120).optional(),
});

type PlazaFormValues = z.infer<typeof schema>;

interface PlazaFormProps {
  title: string;
  defaultValues?: Partial<PlazaFormValues>;
  submitting?: boolean;
  onSubmit: (data: PlazaCreate) => void;
  onCancel: () => void;
}

export function PlazaForm({ title, defaultValues, submitting, onSubmit, onCancel }: PlazaFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PlazaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { nombre_plaza: "", estado: "", ...defaultValues },
  });

  const submit = handleSubmit((data) => {
    onSubmit({ nombre_plaza: data.nombre_plaza, estado: data.estado?.trim() || null });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos de la plaza</div>

        <div className="fl fl-required">Nombre de la plaza</div>
        <input className="fi" autoFocus {...register("nombre_plaza")} />
        <div className="fe">{errors.nombre_plaza?.message}</div>

        <div className="fl">Estado</div>
        <input className="fi" placeholder="Ej. Nuevo León" {...register("estado")} />
        <div className="fe">{errors.estado?.message}</div>
      </div>
      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-phase" disabled={submitting}>
          {submitting ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
  );
}
