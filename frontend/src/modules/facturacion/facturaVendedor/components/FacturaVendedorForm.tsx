/** Alta/edición de FacturaVendedor — paridad exacta de `FacturaAgenciaForm`, pero la
 * comisión es del VENDEDOR PRINCIPAL de la orden (no de la agencia ni del secundario).
 * El combo "Orden relacionada" es de selección simple, filtrado por el vendedor ya
 * elegido; solo lista OC `orden_cerrada` cuyo `vendedor_principal_id` es ese vendedor.
 *
 * El `%` de comisión se sugiere del catálogo del vendedor al elegir la orden (si el
 * usuario todavía no capturó uno a mano) y siempre queda editable — se persiste en la
 * factura (spec: "Cat/Manual"). La tarjeta "Comisión calculada" se recalcula en vivo
 * (`orden.total * % / 100`).
 *
 * La edición hace todo lo que hace el alta (mismo criterio que ADR-087/ADR-079):
 * vendedor y orden se pueden reasignar.
 *
 * PDF/XML por separado (mismo mecanismo que ADR-070/ADR-079): `AdjuntoFacturaInput`
 * con `tipo="factura_vendedor_pdf"`/`"factura_vendedor_xml"`.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { AdjuntoFacturaInput } from "../../facturaCliente/components/AdjuntoFacturaInput";
import { fmtMoneda } from "../../format";
import { useOrdenesFacturablesVendedor, useVendedores } from "../../hooks";
import type { FacturaVendedorCreate, FacturaVendedorUpdate } from "../../types";

const monto = z
  .string()
  .min(1, "Obligatorio.")
  .refine((v) => !Number.isNaN(Number(v)) && Number(v) >= 0, "Debe ser un monto válido.");

const schema = z.object({
  vendedor_id: z.string().min(1, "Selecciona el vendedor."),
  orden_id: z.string().min(1, "Selecciona la orden."),
  folio_factura_vendedor: z.string().trim().max(50).optional(),
  fecha_factura_vendedor: z.string().min(1, "La fecha es obligatoria."),
  monto_factura_vendedor: monto,
  iva_factura_vendedor: monto,
  porcentaje_comision_vendedor: z
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
   *  mismo criterio que `FacturaAgenciaForm`). */
  archivoPdfPathInicial?: string | null;
  archivoXmlPathInicial?: string | null;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaVendedorCreate | FacturaVendedorUpdate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaVendedorForm({
  isEdit,
  defaultValues,
  archivoPdfPathInicial = null,
  archivoXmlPathInicial = null,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: Props) {
  const vendedores = useVendedores();
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { fecha_factura_vendedor: hoy(), iva_factura_vendedor: "0" },
  });
  const [archivoPdfPath, setArchivoPdfPath] = useState<string | null>(archivoPdfPathInicial);
  const [archivoXmlPath, setArchivoXmlPath] = useState<string | null>(archivoXmlPathInicial);

  const vendedorId = watch("vendedor_id");
  const ordenId = watch("orden_id");
  const ordenes = useOrdenesFacturablesVendedor(vendedorId || null);

  // Fix (mismo criterio que el combo de agencia en FacturaAgenciaForm): cambiar de
  // vendedor limpia la orden ya elegida — era del vendedor ANTERIOR. Se compara contra
  // el vendedor CON EL QUE SE MONTÓ el formulario (no "¿ya corrió el efecto?"): React
  // StrictMode monta cada componente dos veces en desarrollo, y un `useRef` de "ya
  // corrió una vez" se deja engañar por ese doble montaje (ver ADR-088).
  const vendedorIdDeMontaje = useRef(defaultValues?.vendedor_id ?? "");
  useEffect(() => {
    if (vendedorId === vendedorIdDeMontaje.current) return;
    setValue("orden_id", "");
  }, [vendedorId, setValue]);

  // El % solo se auto-sugiere si el usuario todavía no capturó uno a mano — elegir
  // otra orden no debe pisar un valor ya escrito.
  const porcentajeTocado = useRef(false);
  const ordenSeleccionada = (ordenes.data ?? []).find((o) => o.orden_id === ordenId);

  const onElegirOrden = (id: string) => {
    setValue("orden_id", id, { shouldValidate: true });
    const oc = (ordenes.data ?? []).find((o) => o.orden_id === id);
    if (oc && !porcentajeTocado.current && oc.porcentaje_comision_vendedor_default != null) {
      setValue("porcentaje_comision_vendedor", oc.porcentaje_comision_vendedor_default);
    }
  };

  const porcentajeCapturado = watch("porcentaje_comision_vendedor");
  const porcentajeEfectivo =
    porcentajeCapturado || ordenSeleccionada?.porcentaje_comision_vendedor_default || null;
  // Se manda como string SIN redondear (ni aquí ni en `fmtMoneda`, que trunca en el
  // string): `.toFixed(2)` redondearía el preview a un valor que podría no coincidir
  // con lo que en verdad se va a guardar.
  const comisionPreview =
    ordenSeleccionada && porcentajeEfectivo
      ? String((Number(ordenSeleccionada.total) * Number(porcentajeEfectivo)) / 100)
      : null;

  const m = Number(watch("monto_factura_vendedor") ?? 0);
  const i = Number(watch("iva_factura_vendedor") ?? 0);
  const totalPreview = Number.isNaN(m) || Number.isNaN(i) ? null : String(m + i);

  const onValid = (v: Valores) => {
    const payload = {
      ...v,
      // Vacío → null: así el backend aplica el default del catálogo en vez de recibir "".
      porcentaje_comision_vendedor: v.porcentaje_comision_vendedor || null,
      archivo_pdf_path: archivoPdfPath,
      archivo_xml_path: archivoXmlPath,
    };
    onSubmit(isEdit ? (payload as FacturaVendedorUpdate) : (payload as FacturaVendedorCreate));
  };

  return (
    <form
      onSubmit={handleSubmit(onValid)}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">{isEdit ? "Editar factura de vendedor" : "Nueva factura de vendedor"}</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">
            Vendedor <FieldTag origin="catalogo" />
          </div>
          <select className="fsel" value={vendedorId ?? ""} {...register("vendedor_id")}>
            <option value="">— Selecciona —</option>
            {(vendedores.data ?? []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.etiqueta}
              </option>
            ))}
          </select>
          {errors.vendedor_id && <div className="fe">{errors.vendedor_id.message}</div>}

          <div className="fl fl-required">
            Orden relacionada <FieldTag origin="derivado" />
          </div>
          <SearchableSelect
            value={ordenId ?? ""}
            onChange={onElegirOrden}
            disabled={!vendedorId}
            placeholder={ordenes.isLoading ? "Cargando órdenes…" : "Busca por folio o número…"}
            emptyResultsLabel={
              !vendedorId
                ? "Selecciona primero un vendedor."
                : "Este vendedor no tiene órdenes internas cerradas."
            }
            options={(ordenes.data ?? []).map((o) => ({
              value: o.orden_id,
              label: o.anunciante ? `${o.folio_orden} — ${o.anunciante}` : o.folio_orden,
            }))}
          />
          {errors.orden_id && <div className="fe">{errors.orden_id.message}</div>}
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Solo lista las órdenes <strong>cerradas</strong> donde este vendedor es el principal.
          </div>

          <div className="r2">
            <div>
              <div className="fl">Folio externo</div>
              <input className="fi" style={{ fontFamily: "var(--mono)" }} {...register("folio_factura_vendedor")} />
            </div>
            <div>
              <div className="fl fl-required">Fecha de la factura</div>
              <input type="date" className="fi" {...register("fecha_factura_vendedor")} />
              {errors.fecha_factura_vendedor && (
                <div className="fe">{errors.fecha_factura_vendedor.message}</div>
              )}
            </div>
          </div>

          <div className="r2">
            <div>
              <div className="fl fl-required">Subtotal</div>
              <input className="fi" inputMode="decimal" {...register("monto_factura_vendedor")} />
              {errors.monto_factura_vendedor && (
                <div className="fe">{errors.monto_factura_vendedor.message}</div>
              )}
            </div>
            <div>
              <div className="fl fl-required">IVA</div>
              <input className="fi" inputMode="decimal" {...register("iva_factura_vendedor")} />
              {errors.iva_factura_vendedor && (
                <div className="fe">{errors.iva_factura_vendedor.message}</div>
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
            {...register("porcentaje_comision_vendedor", {
              onChange: () => {
                porcentajeTocado.current = true;
              },
            })}
          />
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 10, display: "block" }}>
            Se sugiere del vendedor al elegir la orden; se guarda en la factura — si el catálogo
            cambia después, esta conserva el pactado.
          </div>
          {errors.porcentaje_comision_vendedor && (
            <div className="fe">{errors.porcentaje_comision_vendedor.message}</div>
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
                tipo="factura_vendedor_pdf"
                placeholder="Cargar PDF de la factura"
                value={archivoPdfPath}
                onChange={setArchivoPdfPath}
              />
            </div>
            <div>
              <div className="fl">Archivo XML</div>
              <AdjuntoFacturaInput
                tipo="factura_vendedor_xml"
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
