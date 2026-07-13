/** Formulario INLINE de marca (dentro del detalle del anunciante), análogo al de estación
 * dentro del afiliado. Solo captura el nombre de la marca; el anunciante_id lo fija la
 * pantalla.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

const schema = z.object({
  nombre_marca: z.string().trim().min(1, "El nombre de la marca es obligatorio.").max(160),
});

type MarcaFormValues = z.infer<typeof schema>;

export interface MarcaFormData {
  nombre_marca: string;
}

interface MarcaInlineFormProps {
  title: string;
  defaultValues?: Partial<MarcaFormValues>;
  submitting?: boolean;
  onSubmit: (data: MarcaFormData) => void;
  onCancel: () => void;
}

export function MarcaInlineForm({
  title,
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
}: MarcaInlineFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<MarcaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { nombre_marca: "", ...defaultValues },
  });

  const submit = handleSubmit((data) => onSubmit({ nombre_marca: data.nombre_marca.trim() }));

  return (
    <form className="inline-form" onSubmit={submit}>
      <div className="if-title">{title}</div>

      <div className="fl fl-required">Nombre de la marca</div>
      <input className="fi" autoFocus placeholder="Ej. Pan Bimbo" {...register("nombre_marca")} />
      <div className="fe">{errors.nombre_marca?.message}</div>

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
