/** Alta de FacturaAfiliado (React Hook Form + Zod).
 *
 * El IVA se CAPTURA, no se calcula: la factura de la emisora puede traer retenciones o
 * conceptos exentos, así que imponerle el 16% rechazaría facturas legítimas (la spec lo
 * marca "Manual"). El TOTAL sí lo calcula el backend — aquí solo se previsualiza.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { AdjuntoFacturaInput } from "../../facturaCliente/components/AdjuntoFacturaInput";
import { fmtMoneda } from "../../format";
import { useAfiliados, useOrdenesFacturablesAfiliado } from "../../hooks";
import type { FacturaAfiliadoCreate, FacturaAfiliadoUpdate } from "../../types";

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
  /** Edición (`PUT`): el afiliado queda fijo (el backend no permite reasignarlo por esta
   *  vía), no se ofrece el combo de OI (solo aplica al alta) y `onSubmit` recibe
   *  `FacturaAfiliadoUpdate`, sin `afiliado_id`. */
  isEdit?: boolean;
  defaultValues?: Valores;
  /** Adjuntos ya guardados, al editar (el `useState` de abajo solo toma un valor
   *  inicial — no se resincroniza si `defaultValues` cambia después del primer render,
   *  mismo criterio que el resto del formulario). */
  archivoPdfPathInicial?: string | null;
  archivoXmlPathInicial?: string | null;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaAfiliadoCreate | FacturaAfiliadoUpdate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaAfiliadoForm({
  isEdit,
  defaultValues,
  archivoPdfPathInicial = null,
  archivoXmlPathInicial = null,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: Props) {
  const afiliados = useAfiliados();
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { fecha_factura_afiliado: hoy(), iva_factura_afiliado: "0" },
  });

  // Folio de la Orden Interna (combo del alta) y adjuntos: fuera del schema de Zod a
  // propósito — son auxiliares/opcionales, no datos que RHF necesite validar.
  const [ordenEstacionId, setOrdenEstacionId] = useState<string>("");
  const [archivoPdfPath, setArchivoPdfPath] = useState<string | null>(archivoPdfPathInicial);
  const [archivoXmlPath, setArchivoXmlPath] = useState<string | null>(archivoXmlPathInicial);

  const afiliadoId = watch("afiliado_id");
  // Solo se pide con un afiliado ya elegido (`enabled` del hook) — no aplica en edición
  // (el backend no acepta `orden_estacion_id` en `FacturaAfiliadoUpdate`).
  const ordenesFacturables = useOrdenesFacturablesAfiliado(!isEdit ? afiliadoId || null : null);

  const onElegirOrdenEstacion = (id: string) => {
    setOrdenEstacionId(id);
    const oe = (ordenesFacturables.data ?? []).find((o) => o.orden_estacion_id === id);
    if (oe) {
      // Precarga Subtotal/IVA con lo que la emisora cobra por esa OI — quedan
      // EDITABLES después (son los mismos inputs registrados de siempre, sin `disabled`).
      setValue("monto_factura_afiliado", oe.importe_emisora);
      setValue("iva_factura_afiliado", oe.iva_emisora);
    }
  };

  const m = Number(watch("monto_factura_afiliado") ?? 0);
  const i = Number(watch("iva_factura_afiliado") ?? 0);
  const totalPreview = Number.isNaN(m) || Number.isNaN(i) ? null : (m + i).toFixed(2);

  const onValid = (v: Valores) => {
    if (isEdit) {
      // Sin `afiliado_id`: el backend (`FacturaAfiliadoUpdate`) no lo acepta — no se puede
      // reasignar la factura a otro afiliado por esta vía.
      onSubmit({
        factura_emisora: v.factura_emisora,
        fecha_factura_afiliado: v.fecha_factura_afiliado,
        monto_factura_afiliado: v.monto_factura_afiliado,
        iva_factura_afiliado: v.iva_factura_afiliado,
        archivo_pdf_path: archivoPdfPath,
        archivo_xml_path: archivoXmlPath,
      } satisfies FacturaAfiliadoUpdate);
    } else {
      onSubmit({
        ...v,
        archivo_pdf_path: archivoPdfPath,
        archivo_xml_path: archivoXmlPath,
        orden_estacion_id: ordenEstacionId || null,
      } satisfies FacturaAfiliadoCreate);
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onValid)}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">{isEdit ? "Editar factura de afiliado" : "Nueva factura de afiliado"}</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">
            Afiliado <FieldTag origin="catalogo" />
          </div>
          <select
            className="fsel"
            disabled={isEdit}
            title={isEdit ? "El afiliado no se puede cambiar al editar." : undefined}
            {...register("afiliado_id")}
          >
            <option value="">— Selecciona —</option>
            {(afiliados.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.etiqueta}
              </option>
            ))}
          </select>
          {errors.afiliado_id && <div className="fe">{errors.afiliado_id.message}</div>}

          {!isEdit && (
            <>
              <div className="fl">
                Folio de la Orden Interna <FieldTag origin="derivado" />
              </div>
              <SearchableSelect
                value={ordenEstacionId}
                onChange={onElegirOrdenEstacion}
                disabled={!afiliadoId}
                placeholder="Buscar por folio…"
                emptyOptionLabel="— Ninguna —"
                emptyResultsLabel={
                  afiliadoId
                    ? "Este afiliado no tiene órdenes internas cerradas."
                    : "Selecciona primero un afiliado."
                }
                options={(ordenesFacturables.data ?? []).map((oe) => ({
                  value: oe.orden_estacion_id,
                  label: oe.nombre_estacion
                    ? `${oe.folio_orden_estacion} — ${oe.nombre_estacion}`
                    : oe.folio_orden_estacion,
                }))}
              />
              <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
                Opcional: solo se listan las órdenes internas <strong>cerradas</strong> de ese
                afiliado. Al elegir una, se precargan Subtotal/IVA (siguen siendo editables) y la
                factura queda asignada a esa orden al guardar.
              </div>
            </>
          )}

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

          <div className="r2">
            <div>
              <div className="fl">Archivo PDF</div>
              <AdjuntoFacturaInput
                tipo="factura_afiliado_pdf"
                placeholder="Cargar PDF de la factura"
                value={archivoPdfPath}
                onChange={setArchivoPdfPath}
              />
            </div>
            <div>
              <div className="fl">Archivo XML</div>
              <AdjuntoFacturaInput
                tipo="factura_afiliado_xml"
                placeholder="Cargar XML de la factura"
                value={archivoXmlPath}
                onChange={setArchivoXmlPath}
              />
            </div>
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
          {isEdit ? "Guardar cambios" : "Guardar"}
        </button>
      </div>
    </form>
  );
}
