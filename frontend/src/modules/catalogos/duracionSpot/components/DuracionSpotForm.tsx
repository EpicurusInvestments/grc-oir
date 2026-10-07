/** Formulario de alta/edición de DuracionSpotCatalogo (React Hook Form + Zod). Refleja
 * el backend: producto texto libre requerido (≤60) — sin duplicado por
 * producto+descripción, lo valida el backend. ADR-159 (petición del usuario): catálogo
 * nuevo, aún sin usar en ninguna otra pantalla. ADR-164 (petición del usuario):
 * "producto" deja de ser un selector (ya no reusa `ProductoTarifa` de Tarifa) y pasa a
 * ser un input de texto libre, para poder dar de alta productos nuevos.
 *
 * ADR-165 (petición del usuario): "descripción de la duración" pasa a ser OPCIONAL — si
 * se deja vacía, el backend la guarda como "sin resultado" (equivale a nulo), para
 * productos (p.ej. Mención) donde no siempre se quiere capturar una duración real.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

import type { DuracionSpotCatalogoCreate } from "../types";

const schema = z.object({
  producto: z.string().trim().min(1, "El producto es obligatorio.").max(60),
  descripcion_duracion: z.string().trim().max(60),
});

type DuracionSpotFormValues = z.infer<typeof schema>;

interface DuracionSpotFormProps {
  title: string;
  defaultValues?: Partial<DuracionSpotFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: DuracionSpotCatalogoCreate) => void;
  onCancel: () => void;
}

export function DuracionSpotForm({
  title,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: DuracionSpotFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<DuracionSpotFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { producto: "", descripcion_duracion: "", ...defaultValues },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      producto: data.producto.trim(),
      descripcion_duracion: data.descripcion_duracion.trim(),
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Clasificación</div>

        <div className="fl fl-required">Producto</div>
        <input
          className="fi"
          autoFocus
          placeholder="p. ej. Spot, Mención, Jingle promocional…"
          {...register("producto")}
        />
        <div className="fe">{errors.producto?.message}</div>

        <div className="fl">Descripción de la duración</div>
        <input
          className="fi"
          placeholder="p. ej. 20, 1, sin duración… (vacío = «sin resultado»)"
          {...register("descripcion_duracion")}
        />
        <div className="fv muted" style={{ fontSize: 11, marginTop: 2 }}>
          Si se deja vacía, se guarda como «sin resultado» (equivale a no capturar
          ninguna duración para este producto).
        </div>
        <div className="fe">{errors.descripcion_duracion?.message}</div>
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
          <button type="submit" className="btn btn-sm btn-teal" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
