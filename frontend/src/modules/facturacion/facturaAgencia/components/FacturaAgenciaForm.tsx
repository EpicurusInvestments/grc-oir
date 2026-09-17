/** Alta/edición de FacturaAgencia (React Hook Form + Zod) — mismo patrón que
 * `FacturaAfiliadoForm`, adaptado a que aquí la relación con la orden es 1:1 por
 * factura (no N:M): el combo "Orden relacionada" es de selección simple, filtrado por
 * la agencia ya elegida.
 *
 * El `%` de comisión se sugiere del catálogo de la agencia al elegir la orden (si el
 * usuario todavía no capturó uno a mano) y siempre queda editable — se persiste en la
 * factura (spec: "Cat/Manual"). La tarjeta "Comisión calculada" se recalcula en vivo
 * (`orden.total * % / 100`) para que quien captura vea el monto antes de guardar, sin
 * esperar la respuesta del backend.
 *
 * La edición hace todo lo que hace el alta (mismo criterio que ADR-087 en
 * FacturaAfiliado): agencia y orden se pueden reasignar.
 *
 * PDF/XML por separado (ADR-079, mismo mecanismo que ADR-070 en FacturaAfiliado):
 * `AdjuntoFacturaInput` con `tipo="factura_agencia_pdf"`/`"factura_agencia_xml"`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { AdjuntoFacturaInput } from "../../facturaCliente/components/AdjuntoFacturaInput";
import { fmtMoneda } from "../../format";
import { useAgencias, useOrdenesFacturablesAgencia } from "../../hooks";
import type { FacturaAgenciaCreate, FacturaAgenciaUpdate } from "../../types";

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
  isEdit?: boolean;
  defaultValues?: Valores;
  /** Adjuntos ya guardados, al editar (el `useState` de abajo solo toma un valor
   *  inicial — no se resincroniza si `defaultValues` cambia después del primer render,
   *  mismo criterio que `FacturaAfiliadoForm`). */
  archivoPdfPathInicial?: string | null;
  archivoXmlPathInicial?: string | null;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaAgenciaCreate | FacturaAgenciaUpdate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaAgenciaForm({
  isEdit,
  defaultValues,
  archivoPdfPathInicial = null,
  archivoXmlPathInicial = null,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: Props) {
  const agencias = useAgencias();
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { fecha_factura_agencia: hoy(), iva_factura_agencia: "0" },
  });
  const [archivoPdfPath, setArchivoPdfPath] = useState<string | null>(archivoPdfPathInicial);
  const [archivoXmlPath, setArchivoXmlPath] = useState<string | null>(archivoXmlPathInicial);

  const agenciaId = watch("agencia_id");
  const ordenId = watch("orden_id");
  const ordenes = useOrdenesFacturablesAgencia(agenciaId || null);

  // Fix (mismo criterio que el combo de OI en FacturaAfiliado): cambiar de agencia
  // limpia la orden ya elegida — era de la agencia ANTERIOR. Se compara contra la
  // agencia CON LA QUE SE MONTÓ el formulario (no "¿ya corrió el efecto?"): React
  // StrictMode monta cada componente dos veces en desarrollo, y un `useRef` de "ya
  // corrió una vez" se deja engañar por ese doble montaje (ver ADR-088).
  const agenciaIdDeMontaje = useRef(defaultValues?.agencia_id ?? "");
  useEffect(() => {
    if (agenciaId === agenciaIdDeMontaje.current) return;
    setValue("orden_id", "");
  }, [agenciaId, setValue]);

  // El % solo se auto-sugiere si el usuario todavía no capturó uno a mano — elegir
  // otra orden no debe pisar un valor ya escrito.
  const porcentajeTocado = useRef(false);
  const ordenSeleccionada = (ordenes.data ?? []).find((o) => o.orden_id === ordenId);

  const onElegirOrden = (id: string) => {
    setValue("orden_id", id, { shouldValidate: true });
    const oc = (ordenes.data ?? []).find((o) => o.orden_id === id);
    if (oc && !porcentajeTocado.current && oc.porcentaje_comision_agencia_default != null) {
      setValue("porcentaje_comision_agencia", oc.porcentaje_comision_agencia_default);
    }
  };

  const porcentajeCapturado = watch("porcentaje_comision_agencia");
  const porcentajeEfectivo =
    porcentajeCapturado || ordenSeleccionada?.porcentaje_comision_agencia_default || null;
  const comisionPreview =
    ordenSeleccionada && porcentajeEfectivo
      ? ((Number(ordenSeleccionada.total) * Number(porcentajeEfectivo)) / 100).toFixed(2)
      : null;

  const m = Number(watch("monto_factura_agencia") ?? 0);
  const i = Number(watch("iva_factura_agencia") ?? 0);
  const totalPreview = Number.isNaN(m) || Number.isNaN(i) ? null : (m + i).toFixed(2);

  const onValid = (v: Valores) => {
    const payload = {
      ...v,
      // Vacío → null: así el backend aplica el default del catálogo en vez de recibir "".
      porcentaje_comision_agencia: v.porcentaje_comision_agencia || null,
      archivo_pdf_path: archivoPdfPath,
      archivo_xml_path: archivoXmlPath,
    };
    onSubmit(isEdit ? (payload as FacturaAgenciaUpdate) : (payload as FacturaAgenciaCreate));
  };

  return (
    <form
      onSubmit={handleSubmit(onValid)}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">{isEdit ? "Editar factura de agencia" : "Nueva factura de agencia"}</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">
            Agencia <FieldTag origin="catalogo" />
          </div>
          <select className="fsel" value={agenciaId ?? ""} {...register("agencia_id")}>
            <option value="">— Selecciona —</option>
            {(agencias.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.etiqueta}
              </option>
            ))}
          </select>
          {errors.agencia_id && <div className="fe">{errors.agencia_id.message}</div>}

          <div className="fl fl-required">
            Orden relacionada <FieldTag origin="derivado" />
          </div>
          <SearchableSelect
            value={ordenId ?? ""}
            onChange={onElegirOrden}
            disabled={!agenciaId}
            placeholder={ordenes.isLoading ? "Cargando órdenes…" : "Busca por folio o número…"}
            emptyResultsLabel={
              !agenciaId
                ? "Selecciona primero una agencia."
                : "Esta agencia no tiene órdenes internas cerradas."
            }
            options={(ordenes.data ?? []).map((o) => ({
              value: o.orden_id,
              label: o.anunciante ? `${o.folio_orden} — ${o.anunciante}` : o.folio_orden,
            }))}
          />
          {errors.orden_id && <div className="fe">{errors.orden_id.message}</div>}
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Solo lista las órdenes <strong>cerradas</strong> de esa agencia.
          </div>

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
            {...register("porcentaje_comision_agencia", {
              onChange: () => {
                porcentajeTocado.current = true;
              },
            })}
          />
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Se sugiere de la agencia al elegir la orden; se guarda en la factura — si el catálogo
            cambia después, esta conserva el pactado.
          </div>
          {errors.porcentaje_comision_agencia && (
            <div className="fe">{errors.porcentaje_comision_agencia.message}</div>
          )}

          <div className="r2">
            <div>
              <div className="fl">
                Comisión calculada <FieldTag origin="calculado" />
              </div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtMoneda(comisionPreview)}
              </div>
            </div>
            <div>
              <div className="fl">
                Total <FieldTag origin="calculado" />
              </div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtMoneda(totalPreview)}
              </div>
            </div>
          </div>
          {ordenSeleccionada && (
            <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
              Sobre el total c/IVA de la orden ({fmtMoneda(ordenSeleccionada.total)})
            </div>
          )}

          <div className="r2">
            <div>
              <div className="fl">Archivo PDF</div>
              <AdjuntoFacturaInput
                tipo="factura_agencia_pdf"
                placeholder="Cargar PDF de la factura"
                value={archivoPdfPath}
                onChange={setArchivoPdfPath}
              />
            </div>
            <div>
              <div className="fl">Archivo XML</div>
              <AdjuntoFacturaInput
                tipo="factura_agencia_xml"
                placeholder="Cargar XML de la factura"
                value={archivoXmlPath}
                onChange={setArchivoXmlPath}
              />
            </div>
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
