/** Alta de FacturaAfiliado (React Hook Form + Zod).
 *
 * El IVA se CAPTURA, no se calcula: la factura de la emisora puede traer retenciones o
 * conceptos exentos, así que imponerle el 16% rechazaría facturas legítimas (la spec lo
 * marca "Manual"). El TOTAL sí lo calcula el backend — aquí solo se previsualiza.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay } from "@/shared/ui";

import { fmtMoneda } from "../../format";
import { useAfiliados } from "../../hooks";
import type { FacturaAfiliadoCreate } from "../../types";

const monto = z
  .string()
  .min(1, "Obligatorio.")
  .refine((v) => !Number.isNaN(Number(v)) && Number(v) >= 0, "Debe ser un monto válido.");

const schema = z.object({
  afiliado_id: z.string().min(1, "Selecciona el afiliado."),
  factura_emisora: z.string().trim().min(1, "El folio de la emisora es obligatorio.").max(50),
  fecha_factura_afiliado: z.string().min(1, "La fecha es obligatoria."),
  monto_factura_afiliado: monto,
  iva_factura_afiliado: monto,
});

type Valores = z.infer<typeof schema>;

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaAfiliadoCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaAfiliadoForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const afiliados = useAfiliados();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { fecha_factura_afiliado: hoy(), iva_factura_afiliado: "0" },
  });

  const m = Number(watch("monto_factura_afiliado") ?? 0);
  const i = Number(watch("iva_factura_afiliado") ?? 0);
  const totalPreview = Number.isNaN(m) || Number.isNaN(i) ? null : (m + i).toFixed(2);

  return (
    <form
      onSubmit={handleSubmit((v) => onSubmit(v as FacturaAfiliadoCreate))}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nueva factura de afiliado</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">
            Afiliado <FieldTag origin="catalogo" />
          </div>
          <select className="fsel" {...register("afiliado_id")}>
            <option value="">— Selecciona —</option>
            {(afiliados.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.etiqueta}
              </option>
            ))}
          </select>
          {errors.afiliado_id && <div className="fe">{errors.afiliado_id.message}</div>}

          <div className="r2">
            <div>
              <div className="fl fl-required">Folio de la emisora</div>
              <input className="fi" style={{ fontFamily: "var(--mono)" }} {...register("factura_emisora")} />
              {errors.factura_emisora && <div className="fe">{errors.factura_emisora.message}</div>}
            </div>
            <div>
              <div className="fl fl-required">Fecha de la factura</div>
              <input type="date" className="fi" {...register("fecha_factura_afiliado")} />
              {errors.fecha_factura_afiliado && (
                <div className="fe">{errors.fecha_factura_afiliado.message}</div>
              )}
            </div>
          </div>

          <div className="r2">
            <div>
              <div className="fl fl-required">Subtotal</div>
              <input className="fi" inputMode="decimal" {...register("monto_factura_afiliado")} />
              {errors.monto_factura_afiliado && (
                <div className="fe">{errors.monto_factura_afiliado.message}</div>
              )}
            </div>
            <div>
              <div className="fl fl-required">IVA</div>
              <input className="fi" inputMode="decimal" {...register("iva_factura_afiliado")} />
              {errors.iva_factura_afiliado && (
                <div className="fe">{errors.iva_factura_afiliado.message}</div>
              )}
            </div>
          </div>
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Se captura tal como viene en la factura: puede no ser el 16% (retenciones, exentos).
          </div>

          <div className="fl">
            Total <FieldTag origin="calculado" />
          </div>
          <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
            {fmtMoneda(totalPreview)}
          </div>
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
