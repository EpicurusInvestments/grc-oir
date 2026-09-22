/** Formulario de alta/edición de TarifaPlaza (React Hook Form + Zod).
 *
 * ADR-097 (petición del usuario): reemplaza el campo Plaza por "Nombre de la emisora"
 * (select de Estación) y agrega, justo debajo, el selector "Producto" (Spot/Mención/
 * Control remoto/Patrocinio). Ya NO captura vigencia (`vigencia_desde`/`vigencia_hasta`
 * se eliminaron por completo).
 *
 * ADR-099 (petición del usuario): `tarifa_bruta`/`descuento_pct` son PARÁMETROS
 * SENSIBLES — el backend audita cada cambio (`LogCambioParametro`) y exige
 * `motivo_cambio` si alguno de los dos efectivamente cambió. Mismo patrón que los 3 %
 * de comisión de `OrdenClienteForm.tsx`: un solo campo "Motivo del cambio" compartido
 * (no uno por campo), validado a mano en el submit porque el schema de Zod no conoce
 * `defaultValues` al definirse.
 *
 * Refleja las validaciones del backend: estación obligatoria, tipo de señal/duración/
 * producto (enums), tarifa bruta ≥ 0, descuento 0–100. La `tarifa_neta` es CALCULADA: se
 * muestra solo lectura con tag «Calculado» y NO se envía (la calcula y persiste el
 * servidor). Los errores de negocio del backend (p.ej. tarifa activa duplicada, 409) se
 * muestran vía `submitError`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import type { Estacion } from "@/modules/catalogos/estacion/types";
import { FieldTag, MoneyInput, SavingOverlay } from "@/shared/ui";

import { calcularNetaPreview, fmtMoneda } from "../format";
import {
  DURACION_SPOT_OPCIONES,
  PRODUCTO_OPCIONES,
  TIPO_SENAL_OPCIONES,
  type TarifaPlazaCreate,
} from "../types";

const schema = z.object({
  estacion_id: z.string().min(1, "Selecciona una emisora."),
  tipo_senal: z.enum(["fm", "am", "tv"]),
  duracion_spot: z.enum(["20s", "30s", "60s"]),
  producto: z.enum(["spot", "mencion", "control_remoto", "patrocinio"]),
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
  notas: z.string().trim().max(500).optional(),
  motivo_cambio: z.string().trim().max(500).optional(),
});

type TarifaFormValues = z.infer<typeof schema>;

/** Salida del formulario: el alta/edición de TarifaPlaza + el motivo (transitorio, solo
 *  viaja en edición y solo si algún campo sensible cambió). */
export type TarifaFormOutput = TarifaPlazaCreate & { motivo_cambio?: string | null };

interface TarifaFormProps {
  title: string;
  estaciones: Estacion[];
  defaultValues?: Partial<TarifaFormValues>;
  isEdit?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: TarifaFormOutput) => void;
  onCancel: () => void;
}

export function TarifaForm({
  title,
  estaciones,
  defaultValues,
  isEdit = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: TarifaFormProps) {
  const {
    register,
    control,
    handleSubmit,
    watch,
    setError,
    formState: { errors },
  } = useForm<TarifaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      estacion_id: "",
      tipo_senal: "fm",
      duracion_spot: "30s",
      producto: "spot",
      tarifa_bruta: "",
      descuento_pct: "0",
      notas: "",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  const netaPreview = calcularNetaPreview(watch("tarifa_bruta"), watch("descuento_pct"));
  const netaTexto = Number.isFinite(netaPreview) ? fmtMoneda(netaPreview) : "—";

  const brutaCambiada =
    isEdit &&
    defaultValues?.tarifa_bruta !== undefined &&
    Number(watch("tarifa_bruta")) !== Number(defaultValues.tarifa_bruta);
  const descuentoCambiado =
    isEdit &&
    defaultValues?.descuento_pct !== undefined &&
    Number(watch("descuento_pct")) !== Number(defaultValues.descuento_pct);
  const algunSensibleCambio = brutaCambiada || descuentoCambiado;

  const submit = handleSubmit((data) => {
    const motivo = data.motivo_cambio?.trim();
    if (algunSensibleCambio && !motivo) {
      setError("motivo_cambio", {
        type: "manual",
        message: "El motivo es obligatorio al cambiar la tarifa bruta o el descuento.",
      });
      return;
    }
    onSubmit({
      estacion_id: data.estacion_id,
      tipo_senal: data.tipo_senal,
      duracion_spot: data.duracion_spot,
      producto: data.producto,
      tarifa_bruta: data.tarifa_bruta.trim(),
      descuento_pct: data.descuento_pct.trim(),
      notas: data.notas?.trim() || null,
      ...(isEdit && motivo ? { motivo_cambio: motivo } : {}),
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

        <div className="fl fl-required">Nombre de la emisora</div>
        <select className="fsel" autoFocus {...register("estacion_id")}>
          <option value="">Selecciona…</option>
          {estaciones.map((e) => (
            <option key={e.estacion_id} value={e.estacion_id}>
              {e.nombre_estacion}
              {e.siglas ? ` (${e.siglas})` : ""}
            </option>
          ))}
        </select>
        <div className="fe">{errors.estacion_id?.message}</div>

        <div className="fl fl-required">Producto</div>
        <select className="fsel" {...register("producto")}>
          {PRODUCTO_OPCIONES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="fe">{errors.producto?.message}</div>

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
            <div className="fl fl-required">
              Tarifa bruta (MXN) <FieldTag origin="audit" />
            </div>
            <Controller
              control={control}
              name="tarifa_bruta"
              render={({ field }) => (
                <MoneyInput value={field.value} onChange={field.onChange} onBlur={field.onBlur} placeholder="0.00" />
              )}
            />
            <div className="fe">{errors.tarifa_bruta?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">
              Descuento (%) <FieldTag origin="audit" />
            </div>
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

        {/* Compartido entre tarifa bruta y descuento (ADR-099): un solo motivo para
            los dos, mismo criterio que los 3 % de comisión de OrdenClienteForm. */}
        {isEdit && (
          <>
            <div className="fl fl-required">
              Motivo del cambio{" "}
              <span style={{ color: "var(--text3)", fontWeight: 400 }}>
                (si modificas la tarifa bruta o el descuento)
              </span>
            </div>
            <input
              className="fi"
              placeholder="Requerido al modificar el valor…"
              {...register("motivo_cambio")}
            />
            <div className="fe">{errors.motivo_cambio?.message}</div>
          </>
        )}

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

        <div className="fl">Notas</div>
        <textarea className="ftxt" rows={2} {...register("notas")} />
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
          <button type="submit" className="btn btn-sm btn-teal" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
