/** Formulario de alta/edición de TarifaPlaza (React Hook Form + Zod).
 *
 * Refleja las validaciones del backend: plaza obligatoria, tipo de señal y duración
 * (enums), tarifa bruta ≥ 0, descuento 0–100, `vigencia_hasta >= vigencia_desde`. La
 * `tarifa_neta` es CALCULADA: se muestra solo lectura con tag «Calculado» y NO se envía
 * (la calcula y persiste el servidor). Los errores de negocio del backend (p.ej.
 * solapamiento de vigencias, 409) se muestran vía `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { Plaza } from "@/modules/catalogos/plaza/types";
import { FieldTag } from "@/shared/ui";

import { calcularNetaPreview, fmtMoneda } from "../format";
import {
  DURACION_SPOT_OPCIONES,
  TIPO_SENAL_OPCIONES,
  type TarifaPlazaCreate,
} from "../types";

const schema = z
  .object({
    plaza_id: z.string().min(1, "Selecciona una plaza."),
    tipo_senal: z.enum(["fm", "am", "tv"]),
    duracion_spot: z.enum(["20s", "30s", "60s", "mencion"]),
    tarifa_bruta: z
      .string()
      .trim()
      .min(1, "La tarifa bruta es obligatoria.")
      .refine((v) => Number.isFinite(Number(v)) && Number(v) >= 0, "Monto inválido (número ≥ 0)."),
    descuento_pct: z
      .string()
      .trim()
      .min(1, "El descuento es obligatorio.")
      .refine((v) => {
        const n = Number(v);
        return Number.isFinite(n) && n >= 0 && n <= 100;
      }, "El descuento debe estar entre 0 y 100."),
    vigencia_desde: z.string().min(1, "La fecha de inicio es obligatoria."),
    vigencia_hasta: z.string().min(1, "La fecha de fin es obligatoria."),
    notas: z.string().trim().max(500).optional(),
  })
  .refine((d) => d.vigencia_hasta >= d.vigencia_desde, {
    path: ["vigencia_hasta"],
    message: "La fecha de fin debe ser mayor o igual que la de inicio.",
  });

type TarifaFormValues = z.infer<typeof schema>;

interface TarifaFormProps {
  title: string;
  plazas: Plaza[];
  defaultValues?: Partial<TarifaFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: TarifaPlazaCreate) => void;
  onCancel: () => void;
}

export function TarifaForm({
  title,
  plazas,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: TarifaFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<TarifaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      plaza_id: "",
      tipo_senal: "fm",
      duracion_spot: "30s",
      tarifa_bruta: "",
      descuento_pct: "0",
      vigencia_desde: "",
      vigencia_hasta: "",
      notas: "",
      ...defaultValues,
    },
  });

  const netaPreview = calcularNetaPreview(watch("tarifa_bruta"), watch("descuento_pct"));
  const netaTexto = Number.isFinite(netaPreview) ? fmtMoneda(netaPreview) : "—";

  const submit = handleSubmit((data) => {
    onSubmit({
      plaza_id: data.plaza_id,
      tipo_senal: data.tipo_senal,
      duracion_spot: data.duracion_spot,
      tarifa_bruta: data.tarifa_bruta.trim(),
      descuento_pct: data.descuento_pct.trim(),
      vigencia_desde: data.vigencia_desde,
      vigencia_hasta: data.vigencia_hasta,
      notas: data.notas?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Clasificación</div>

        <div className="fl fl-required">Plaza</div>
        <select className="fsel" autoFocus {...register("plaza_id")}>
          <option value="">Selecciona…</option>
          {plazas.map((p) => (
            <option key={p.plaza_id} value={p.plaza_id}>
              {p.nombre_plaza}
              {p.estado ? ` · ${p.estado}` : ""}
            </option>
          ))}
        </select>
        <div className="fe">{errors.plaza_id?.message}</div>

        <div className="r2">
          <div>
            <div className="fl fl-required">Tipo de señal</div>
            <select className="fsel" {...register("tipo_senal")}>
              {TIPO_SENAL_OPCIONES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <div className="fe">{errors.tipo_senal?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Duración del spot</div>
            <select className="fsel" {...register("duracion_spot")}>
              {DURACION_SPOT_OPCIONES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <div className="fe">{errors.duracion_spot?.message}</div>
          </div>
        </div>

        <div className="sec">Tarifa</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Tarifa bruta (MXN)</div>
            <input
              className="fi"
              inputMode="decimal"
              placeholder="0.00"
              style={{ fontFamily: "var(--mono)" }}
              {...register("tarifa_bruta")}
            />
            <div className="fe">{errors.tarifa_bruta?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Descuento (%)</div>
            <input
              className="fi"
              inputMode="decimal"
              placeholder="0"
              style={{ fontFamily: "var(--mono)" }}
              {...register("descuento_pct")}
            />
            <div className="fe">{errors.descuento_pct?.message}</div>
          </div>
        </div>

        <div className="fl">
          Tarifa neta <FieldTag origin="calculado" />
        </div>
        <input
          className="fi"
          readOnly
          value={netaTexto}
          style={{ fontFamily: "var(--mono)", fontWeight: 600 }}
        />
        <div className="fe" />

        <div className="sec">Vigencia</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Desde</div>
            <input className="fi" type="date" {...register("vigencia_desde")} />
            <div className="fe">{errors.vigencia_desde?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Hasta</div>
            <input className="fi" type="date" {...register("vigencia_hasta")} />
            <div className="fe">{errors.vigencia_hasta?.message}</div>
          </div>
        </div>

        <div className="fl">Notas</div>
        <textarea
          className="fi"
          rows={3}
          style={{ height: "auto", minHeight: 62, paddingTop: 8, resize: "vertical" }}
          {...register("notas")}
        />
        <div className="fe">{errors.notas?.message}</div>
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
