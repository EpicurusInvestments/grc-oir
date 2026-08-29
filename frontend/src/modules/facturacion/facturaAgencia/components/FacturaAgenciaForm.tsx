/** Alta de FacturaAgencia (React Hook Form + Zod).
 *
 * El `%` de comisión es opcional: si se deja vacío, el backend toma el default del
 * catálogo Agencia. Se persiste en la factura, así que un cambio posterior del catálogo
 * no altera lo ya pactado.
 *
 * `comision_agencia = OrdenCliente.total * % / 100` la calcula el SERVICIO (sobre el total
 * de la orden, con IVA — la fórmula literal de la spec). Aquí no se previsualiza porque
 * requeriría el total de la orden, que este formulario no tiene: mostrar un número
 * aproximado sería peor que no mostrarlo.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { useAgencias, useOrdenesFacturables } from "../../hooks";
import type { FacturaAgenciaCreate } from "../../types";

const monto = z
  .string()
  .min(1, "Obligatorio.")
  .refine((v) => !Number.isNaN(Number(v)) && Number(v) >= 0, "Debe ser un monto válido.");

const schema = z.object({
  agencia_id: z.string().min(1, "Selecciona la agencia."),
  orden_id: z.string().min(1, "Selecciona la orden."),
  folio_factura_agencia: z.string().trim().max(50).optional(),
  fecha_factura_agencia: z.string().min(1, "La fecha es obligatoria."),
  monto_factura_agencia: monto,
  iva_factura_agencia: monto,
  porcentaje_comision_agencia: z
    .string()
    .optional()
    .refine(
      (v) => !v || (!Number.isNaN(Number(v)) && Number(v) >= 0 && Number(v) <= 100),
      "El porcentaje debe estar entre 0 y 100.",
    ),
});

type Valores = z.infer<typeof schema>;

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaAgenciaCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaAgenciaForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const agencias = useAgencias();
  const ordenes = useOrdenesFacturables();
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { fecha_factura_agencia: hoy(), iva_factura_agencia: "0" },
  });

  const ordenId = watch("orden_id");

  return (
    <form
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...v,
          // Vacío → null: así el backend aplica el default del catálogo en vez de recibir "".
          porcentaje_comision_agencia: v.porcentaje_comision_agencia || null,
        } as FacturaAgenciaCreate),
      )}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nueva factura de agencia</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">
            Agencia <FieldTag origin="catalogo" />
          </div>
          <select className="fsel" {...register("agencia_id")}>
            <option value="">— Selecciona —</option>
            {(agencias.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.etiqueta}
              </option>
            ))}
          </select>
          {errors.agencia_id && <div className="fe">{errors.agencia_id.message}</div>}

          <div className="fl fl-required">Orden relacionada</div>
          <SearchableSelect
            value={ordenId ?? ""}
            onChange={(v) => setValue("orden_id", v, { shouldValidate: true })}
            placeholder={ordenes.isLoading ? "Cargando órdenes…" : "Busca por folio o número…"}
            options={(ordenes.data ?? []).map((o) => ({
              value: o.orden_id,
              label: `${o.folio_orden} · ${o.numero_orden_cliente}`,
            }))}
          />
          {errors.orden_id && <div className="fe">{errors.orden_id.message}</div>}

          <div className="r2">
            <div>
              <div className="fl">Folio externo</div>
              <input className="fi" style={{ fontFamily: "var(--mono)" }} {...register("folio_factura_agencia")} />
            </div>
            <div>
              <div className="fl fl-required">Fecha de la factura</div>
              <input type="date" className="fi" {...register("fecha_factura_agencia")} />
              {errors.fecha_factura_agencia && (
                <div className="fe">{errors.fecha_factura_agencia.message}</div>
              )}
            </div>
          </div>

          <div className="r2">
            <div>
              <div className="fl fl-required">Subtotal</div>
              <input className="fi" inputMode="decimal" {...register("monto_factura_agencia")} />
              {errors.monto_factura_agencia && (
                <div className="fe">{errors.monto_factura_agencia.message}</div>
              )}
            </div>
            <div>
              <div className="fl fl-required">IVA</div>
              <input className="fi" inputMode="decimal" {...register("iva_factura_agencia")} />
              {errors.iva_factura_agencia && (
                <div className="fe">{errors.iva_factura_agencia.message}</div>
              )}
            </div>
          </div>

          <div className="fl">
            % de comisión <FieldTag origin="catalogo" />
          </div>
          <input
            className="fi"
            inputMode="decimal"
            placeholder="Vacío = default del catálogo"
            {...register("porcentaje_comision_agencia")}
          />
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Se guarda en la factura: si el catálogo cambia después, esta conserva el pactado.
          </div>
          {errors.porcentaje_comision_agencia && (
            <div className="fe">{errors.porcentaje_comision_agencia.message}</div>
          )}
        </div>

        {submitError && <div className="state-msg error">{submitError}</div>}
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-primary" disabled={submitting}>
          Guardar
        </button>
      </div>
    </form>
  );
}
