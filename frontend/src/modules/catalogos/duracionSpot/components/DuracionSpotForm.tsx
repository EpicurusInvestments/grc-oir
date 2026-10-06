/** Formulario de alta/edición de DuracionSpotCatalogo (React Hook Form + Zod). Refleja
 * el backend: producto requerido (reusa `ProductoTarifa`) y descripción de duración
 * requerida (≤60, texto libre — sin duplicado por producto+descripción, lo valida el
 * backend). ADR-159 (petición del usuario): catálogo nuevo, aún sin usar en ninguna
 * otra pantalla.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PRODUCTO_OPCIONES } from "@/modules/catalogos/tarifa/types";
import { SavingOverlay } from "@/shared/ui";

import type { DuracionSpotCatalogoCreate } from "../types";

const schema = z.object({
  producto: z.enum(["spot", "mencion", "control_remoto", "patrocinio"]),
  descripcion_duracion: z.string().trim().min(1, "La descripción es obligatoria.").max(60),
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
    defaultValues: { producto: "spot", descripcion_duracion: "", ...defaultValues },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      producto: data.producto,
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
        <select className="fsel" autoFocus {...register("producto")}>
          {PRODUCTO_OPCIONES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="fe">{errors.producto?.message}</div>

        <div className="fl fl-required">Descripción de la duración</div>
        <input
          className="fi"
          placeholder="p. ej. 20, 1, sin duración…"
          {...register("descripcion_duracion")}
        />
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
