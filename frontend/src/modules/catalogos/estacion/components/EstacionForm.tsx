/** Formulario de alta/edición de Estación/Emisora (React Hook Form + Zod).
 *
 * ADR-094: Plaza y Afiliado son dos selects INDEPENDIENTES — la plaza de la estación ya
 * no se hereda del afiliado (reemplaza a ADR-005); pueden ser distintas.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

import type { EstacionCreate, TipoSenal } from "../types";

/** Opción mínima de afiliado/plaza para los selects. */
export interface AfiliadoOpcion {
  afiliado_id: string;
  nombre_afiliado: string;
}
export interface PlazaOpcion {
  plaza_id: string;
  nombre_plaza: string;
  estado?: string | null;
}

const TIPOS_SENAL: { value: TipoSenal; label: string }[] = [
  { value: "fm", label: "FM" },
  { value: "am", label: "AM" },
  { value: "tv", label: "TV" },
];

const schema = z.object({
  nombre_estacion: z.string().trim().min(1, "El nombre es obligatorio.").max(120),
  siglas: z.string().trim().max(20).optional(),
  frecuencia: z.string().trim().max(40).optional(),
  tipo_senal: z.enum(["fm", "am", "tv"], { errorMap: () => ({ message: "Selecciona el tipo de señal." }) }),
  plaza_id: z.string().min(1, "Selecciona una plaza."),
  afiliado_id: z.string().min(1, "Selecciona un afiliado."),
});

type EstacionFormValues = z.infer<typeof schema>;

interface EstacionFormProps {
  title: string;
  plazas: PlazaOpcion[];
  afiliados: AfiliadoOpcion[];
  defaultValues?: Partial<EstacionFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: EstacionCreate) => void;
  onCancel: () => void;
}

export function EstacionForm({
  title,
  plazas,
  afiliados,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: EstacionFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EstacionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_estacion: "",
      siglas: "",
      frecuencia: "",
      tipo_senal: "fm",
      plaza_id: "",
      afiliado_id: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_estacion: data.nombre_estacion.trim(),
      siglas: data.siglas?.trim() || null,
      frecuencia: data.frecuencia?.trim() || null,
      tipo_senal: data.tipo_senal,
      plaza_id: data.plaza_id,
      afiliado_id: data.afiliado_id,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Identificación</div>

        <div className="r2">
          <div>
            <div className="fl fl-required">Nombre de la emisora</div>
            <input className="fi" autoFocus placeholder="Ej. La Que Buena" {...register("nombre_estacion")} />
            <div className="fe">{errors.nombre_estacion?.message}</div>
          </div>
          <div>
            <div className="fl">Siglas</div>
            <input
              className="fi"
              style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
              placeholder="Ej. XEW"
              {...register("siglas")}
            />
            <div className="fe">{errors.siglas?.message}</div>
          </div>
        </div>

        <div className="r2">
          <div>
            <div className="fl">Frecuencia</div>
            <input className="fi" placeholder="Ej. 97.7" {...register("frecuencia")} />
            <div className="fe">{errors.frecuencia?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Tipo de señal</div>
            <select className="fsel" {...register("tipo_senal")}>
              {TIPOS_SENAL.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <div className="fe">{errors.tipo_senal?.message}</div>
          </div>
        </div>

        <div className="sec">Operación</div>

        <div className="fl fl-required">Plaza</div>
        <select className="fsel" {...register("plaza_id")}>
          <option value="">Selecciona…</option>
          {plazas.map((p) => (
            <option key={p.plaza_id} value={p.plaza_id}>
              {p.nombre_plaza}
              {p.estado ? ` · ${p.estado}` : ""}
            </option>
          ))}
        </select>
        <div className="fe">{errors.plaza_id?.message}</div>

        <div className="fl fl-required">Afiliado</div>
        <select className="fsel" {...register("afiliado_id")}>
          <option value="">Selecciona…</option>
          {afiliados.map((a) => (
            <option key={a.afiliado_id} value={a.afiliado_id}>
              {a.nombre_afiliado}
            </option>
          ))}
        </select>
        <div className="fe">{errors.afiliado_id?.message}</div>
        <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
          Solo se listan afiliados activos.
        </div>
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
