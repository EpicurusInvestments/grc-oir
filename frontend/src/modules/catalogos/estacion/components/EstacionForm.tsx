/** Formulario de alta/edición de Estación/Emisora (React Hook Form + Zod).
 *
 * ADR-094: Plaza y Afiliado son dos selects INDEPENDIENTES — la plaza de la estación ya
 * no se hereda del afiliado (reemplaza a ADR-005); pueden ser distintas.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import type { ChangeEvent } from "react";
import { z } from "zod";

import { SavingOverlay, SearchableSelect } from "@/shared/ui";

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

// Petición del usuario, con captura: "siglas" solo admite letras y guiones (sin
// espacios ni otros caracteres, ej. "XHLAYA-FM") — se filtra mientras se escribe, no
// solo al guardar, igual criterio que el validador del backend (`_normaliza_siglas`).
function soloSiglas(e: ChangeEvent<HTMLInputElement>) {
  e.target.value = e.target.value.toUpperCase().replace(/[^A-Z-]/g, "");
}

// Petición del usuario ("IMPORTANTE"): todos los campos de captura de texto van en
// mayúsculas, en todos los catálogos — se transforma mientras se escribe, no solo al
// guardar (antes "Nombre de la emisora" se guardaba tal cual se tecleaba).
function aMayusculas(e: ChangeEvent<HTMLInputElement>) {
  e.target.value = e.target.value.toUpperCase();
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
    control,
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
            <input
              className="fi"
              autoFocus
              placeholder="Ej. La Que Buena"
              {...register("nombre_estacion", { onChange: aMayusculas })}
            />
            <div className="fe">{errors.nombre_estacion?.message}</div>
          </div>
          <div>
            <div className="fl">Siglas</div>
            <input
              className="fi"
              style={{ fontFamily: "var(--mono)" }}
              placeholder="Ej. XEW"
              {...register("siglas", { onChange: soloSiglas })}
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
        <Controller
          control={control}
          name="plaza_id"
          render={({ field }) => (
            <SearchableSelect
              value={field.value}
              onChange={field.onChange}
              options={plazas.map((p) => ({
                value: p.plaza_id,
                label: p.estado ? `${p.nombre_plaza} · ${p.estado}` : p.nombre_plaza,
              }))}
            />
          )}
        />
        <div className="fe">{errors.plaza_id?.message}</div>

        <div className="fl fl-required">Afiliado</div>
        <Controller
          control={control}
          name="afiliado_id"
          render={({ field }) => (
            <SearchableSelect
              value={field.value}
              onChange={field.onChange}
              options={afiliados.map((a) => ({ value: a.afiliado_id, label: a.nombre_afiliado }))}
            />
          )}
        />
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
