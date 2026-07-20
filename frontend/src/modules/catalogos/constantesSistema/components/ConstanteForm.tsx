/** Formulario de alta/edición de una constante (React Hook Form + Zod).
 *
 * En ALTA se capturan grupo (select), clave, descripción y valor. En EDICIÓN, grupo y clave
 * son la identidad natural del registro (el backend no los deja cambiar): se muestran de solo
 * lectura y solo se editan descripción y valor. Errores de negocio llegan por `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { ConstanteSistemaCreate, GrupoConstante } from "../types";
import { GRUPO_LABEL, GRUPOS } from "../types";

const schema = z.object({
  grupo: z.enum(GRUPOS),
  clave: z.string().trim().min(1, "La clave es obligatoria.").max(100),
  descripcion: z.string().trim().min(1, "La descripción es obligatoria.").max(400),
  valor: z.string().trim().max(200).optional(),
});

type ConstanteFormValues = z.infer<typeof schema>;

interface ConstanteFormProps {
  title: string;
  isEdit?: boolean;
  defaultValues?: Partial<ConstanteFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: ConstanteSistemaCreate) => void;
  onCancel: () => void;
}

export function ConstanteForm({
  title,
  isEdit = false,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: ConstanteFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ConstanteFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      grupo: "UsoCFDI" as GrupoConstante,
      clave: "",
      descripcion: "",
      valor: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      grupo: data.grupo,
      clave: data.clave.trim(),
      descripcion: data.descripcion.trim(),
      valor: data.valor?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos de la constante</div>

        <div className="fl fl-required">Grupo</div>
        {isEdit ? (
          // Identidad natural: no se edita en edición (se muestra de solo lectura).
          <input className="fi" readOnly {...register("grupo")} />
        ) : (
          <select className="fsel" autoFocus {...register("grupo")}>
            {GRUPOS.map((g) => (
              <option key={g} value={g}>
                {g} — {GRUPO_LABEL[g]}
              </option>
            ))}
          </select>
        )}
        <div className="fe">{errors.grupo?.message}</div>

        <div className="fl fl-required">Clave</div>
        <input className="fi mono" readOnly={isEdit} {...register("clave")} />
        <div className="fe">{errors.clave?.message}</div>

        <div className="fl fl-required">Descripción</div>
        <input className="fi" autoFocus={isEdit} {...register("descripcion")} />
        <div className="fe">{errors.descripcion?.message}</div>

        <div className="fl">Valor configurable</div>
        <input className="fi mono" placeholder="Opcional (p.ej. 33, D)" {...register("valor")} />
        <div className="fe">{errors.valor?.message}</div>
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
