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
 * Refleja las validaciones del backend: estación obligatoria, duración/producto (enums),
 * tarifa bruta ≥ 0, descuento 0–100. La `tarifa_neta` es CALCULADA: se muestra solo
 * lectura con tag «Calculado» y NO se envía (la calcula y persiste el servidor). Los
 * errores de negocio del backend (p.ej. tarifa activa duplicada, 409) se muestran vía
 * `submitError`.
 *
 * ADR-158 (petición del usuario): se quita el campo "Tipo de señal" — es propiedad de
 * la estación seleccionada (`Estacion.tipo_senal`), capturarla aquí también permitía
 * una inconsistencia sin ningún beneficio. "Duración del spot" se renombra a solo
 * "Duración".
 *
 * ADR-166 (petición del usuario): "Producto" y "Duración" dejan de ser selectores fijos
 * y se llenan desde el catálogo `DuracionSpotCatalogo` ("Producto Duración"): el select
 * de Producto lista los valores distintos y activos del catálogo; al elegir uno, el
 * select de Duración lista las `descripcion_duracion` de ESE producto — EXCLUYENDO el
 * literal "sin resultado" (ADR-165), que aquí NUNCA es una duración seleccionable. Si
 * para el producto elegido no queda ninguna duración real, se bloquea Guardar con un
 * mensaje para ir a dar de alta una en ese catálogo. Al editar una tarifa ya existente
 * cuya combinación no esté (todavía) en el catálogo, se conserva como opción de
 * respaldo para no romper la edición de datos previos a esta conexión.
 */

import { useMemo } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { useDuracionesSpot } from "@/modules/catalogos/duracionSpot/hooks";
import { SIN_RESULTADO } from "@/modules/catalogos/duracionSpot/types";
import type { Estacion } from "@/modules/catalogos/estacion/types";
import { FieldTag, MoneyInput, SavingOverlay } from "@/shared/ui";

import { calcularNetaPreview, fmtMoneda } from "../format";
import type { TarifaPlazaCreate } from "../types";

const esSinResultado = (v: string) => v.trim().toLowerCase() === SIN_RESULTADO;

const schema = z.object({
  estacion_id: z.string().min(1, "Selecciona una emisora."),
  duracion_spot: z
    .string()
    .min(1, "Selecciona una duración.")
    .refine((v) => !esSinResultado(v), 'No se puede usar "sin resultado" como duración.'),
  producto: z.string().min(1, "Selecciona un producto."),
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
    setValue,
    setError,
    formState: { errors },
  } = useForm<TarifaFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      estacion_id: "",
      duracion_spot: "",
      producto: "",
      tarifa_bruta: "",
      descuento_pct: "0",
      notas: "",
      motivo_cambio: "",
      ...defaultValues,
    },
  });

  // ADR-166: Producto/Duración salen del catálogo "Producto Duración", no de un enum fijo.
  const catalogo = useDuracionesSpot().useList({ activo: true, size: 100 });
  const entradas = useMemo(() => catalogo.data?.items ?? [], [catalogo.data]);

  const productoActual = watch("producto");

  const productos = useMemo(() => {
    const vistos = new Map<string, string>(); // key lower -> forma original
    for (const e of entradas) vistos.set(e.producto.trim().toLowerCase(), e.producto);
    // Respaldo: una tarifa ya existente cuyo producto no esté (todavía) en el catálogo
    // no debe perder su valor al editar.
    if (defaultValues?.producto && !vistos.has(defaultValues.producto.trim().toLowerCase())) {
      vistos.set(defaultValues.producto.trim().toLowerCase(), defaultValues.producto);
    }
    return [...vistos.values()].sort((a, b) => a.localeCompare(b, "es"));
  }, [entradas, defaultValues?.producto]);

  const duraciones = useMemo(() => {
    const delProducto = entradas.filter(
      (e) => e.producto.trim().toLowerCase() === productoActual.trim().toLowerCase(),
    );
    const vistos = new Map<string, string>();
    for (const e of delProducto) {
      if (esSinResultado(e.descripcion_duracion)) continue;
      vistos.set(e.descripcion_duracion.trim().toLowerCase(), e.descripcion_duracion);
    }
    // Mismo respaldo que arriba, pero solo mientras el producto elegido siga siendo el
    // original de esta tarifa (si el usuario lo cambia, el respaldo ya no aplica).
    if (
      defaultValues?.duracion_spot &&
      productoActual.trim().toLowerCase() === (defaultValues.producto ?? "").trim().toLowerCase() &&
      !vistos.has(defaultValues.duracion_spot.trim().toLowerCase())
    ) {
      vistos.set(defaultValues.duracion_spot.trim().toLowerCase(), defaultValues.duracion_spot);
    }
    return [...vistos.values()];
  }, [entradas, productoActual, defaultValues?.producto, defaultValues?.duracion_spot]);

  const sinDuracionDisponible = productoActual.trim() !== "" && duraciones.length === 0;

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
    if (sinDuracionDisponible) return; // bloqueado: el banner ya explica por qué.
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

        <div className="fl fl-required">
          Producto{" "}
          <span style={{ color: "var(--text3)", fontWeight: 400 }}>
            (catálogo Producto Duración)
          </span>
        </div>
        <select
          className="fsel"
          {...register("producto", { onChange: () => setValue("duracion_spot", "") })}
          disabled={catalogo.isLoading}
        >
          <option value="">{catalogo.isLoading ? "Cargando…" : "Selecciona…"}</option>
          {productos.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <div className="fe">{errors.producto?.message}</div>

        <div className="fl fl-required">Duración</div>
        {sinDuracionDisponible ? (
          <div className="state-msg error" style={{ textAlign: "left", margin: 0 }}>
            El producto «{productoActual}» no tiene ninguna duración capturada en el
            catálogo Producto Duración. Ve a Catálogos → Producto Duración y da de alta
            una duración real para este producto antes de continuar.
          </div>
        ) : (
          <select className="fsel" {...register("duracion_spot")} disabled={!productoActual}>
            <option value="">{productoActual ? "Selecciona…" : "Elige un producto primero"}</option>
            {duraciones.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        )}
        <div className="fe">{errors.duracion_spot?.message}</div>

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
