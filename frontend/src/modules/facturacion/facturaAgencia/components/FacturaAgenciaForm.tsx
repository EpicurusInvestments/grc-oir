/** Alta/edición de FacturaAgencia (React Hook Form + Zod) — ADR nuevo (petición del
 * usuario, con captura, 2026-11-06) que SUSTITUYE el criterio de ADR-079: el combo
 * "Orden relacionada" de selección simple se reemplaza por el mismo patrón de
 * "Buscar y agregar" multi-selección que `FacturaAfiliadoForm`, para acumular VARIAS
 * órdenes en una sola factura.
 *
 * Subtotal/IVA/Total dejan de capturarse a mano (petición del usuario: "no se captura
 * Subtotal manual, se vuelve un campo calculado") — se CALCULAN como la suma de la
 * comisión de cada orden elegida, más IVA a la tasa central. Cada orden usa SU PROPIO %
 * ya pactado (`porcentaje_comision_agencia_snap` de esa orden, o si no el default del
 * catálogo de la agencia) — por eso ya no hay un solo campo "% de comisión" editable
 * para toda la factura: el % se ve, de solo lectura, en cada fila agregada.
 *
 * La edición hace todo lo que hace el alta (mismo criterio que ADR-087 en
 * FacturaAfiliado): la agencia se puede reasignar y esta misma sección edita qué
 * órdenes tiene asignadas.
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
import { fmtMoneda, fmtPorcentaje } from "../../format";
import { useAgencias, useOrdenesFacturablesAgencia } from "../../hooks";
import type { FacturaAgenciaCreate, FacturaAgenciaOrden, FacturaAgenciaUpdate } from "../../types";

const schema = z.object({
  agencia_id: z.string().min(1, "Selecciona la agencia."),
  folio_factura_agencia: z.string().trim().max(50).optional(),
  fecha_factura_agencia: z.string().min(1, "La fecha es obligatoria."),
});

type Valores = z.infer<typeof schema>;

/** Fila de la sección "Órdenes asignadas" — sea una OC recién agregada del combo (% y
 *  comisión calculados en vivo contra su propio dato) o una ya asignada de antes
 *  (`porcentaje_comision_snap`/`comision_calculada` ya congelados por el backend). */
interface OrdenSeleccionada {
  orden_id: string;
  folio_orden: string;
  anunciante: string | null;
  total: string;
  porcentaje: string;
  comision: string;
}

interface Props {
  isEdit?: boolean;
  defaultValues?: Valores;
  /** Órdenes ya guardadas, al editar — precargan la sección (el `useState` de abajo solo
   *  las toma como valor inicial, no se resincroniza si la prop cambia después del
   *  primer render) — mismo criterio que `asignacionesIniciales` en FacturaAfiliadoForm. */
  ordenesIniciales?: FacturaAgenciaOrden[];
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
  ordenesIniciales,
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
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { fecha_factura_agencia: hoy() },
  });

  const [ordenesSeleccionadas, setOrdenesSeleccionadas] = useState<OrdenSeleccionada[]>(() =>
    (ordenesIniciales ?? []).map((o) => ({
      orden_id: o.orden_id,
      folio_orden: o.folio_orden,
      anunciante: o.anunciante,
      total: o.orden_total ?? "0",
      porcentaje: o.porcentaje_comision_snap,
      comision: o.comision_calculada,
    })),
  );
  const [archivoPdfPath, setArchivoPdfPath] = useState<string | null>(archivoPdfPathInicial);
  const [archivoXmlPath, setArchivoXmlPath] = useState<string | null>(archivoXmlPathInicial);

  const agenciaId = watch("agencia_id");
  const ordenesFacturables = useOrdenesFacturablesAgencia(agenciaId || null);

  // Fix (mismo criterio que el combo de OI en FacturaAfiliado): cambiar de agencia
  // limpia las órdenes ya elegidas — eran de la agencia ANTERIOR. Se compara contra la
  // agencia CON LA QUE SE MONTÓ el formulario, no "¿ya corrió el efecto?" (React
  // StrictMode monta cada componente dos veces en desarrollo, ver ADR-088).
  const agenciaIdDeMontaje = useRef(defaultValues?.agencia_id ?? "");
  useEffect(() => {
    if (agenciaId === agenciaIdDeMontaje.current) return;
    setOrdenesSeleccionadas([]);
  }, [agenciaId]);

  const agregarOrden = (id: string) => {
    if (!id) return;
    const oc = (ordenesFacturables.data ?? []).find((o) => o.orden_id === id);
    if (oc) {
      const porcentaje = oc.porcentaje_comision_agencia_snap ?? oc.porcentaje_comision_agencia_default ?? "0";
      const comision = String((Number(oc.total) * Number(porcentaje)) / 100);
      setOrdenesSeleccionadas((prev) => [
        ...prev,
        {
          orden_id: oc.orden_id,
          folio_orden: oc.folio_orden,
          anunciante: oc.anunciante,
          total: oc.total,
          porcentaje,
          comision,
        },
      ]);
    }
  };

  const quitarOrden = (id: string) => {
    setOrdenesSeleccionadas((prev) => prev.filter((o) => o.orden_id !== id));
  };

  // Solo ofrece las que todavía no se eligieron en ESTA factura — una vez agregada,
  // desaparece del buscador (el mismo orden SÍ puede estar en OTRAS facturas de
  // agencia, parcialidades, ADR-079: el backend no las excluye del combo).
  const opcionesDisponibles = (ordenesFacturables.data ?? []).filter(
    (oc) => !ordenesSeleccionadas.some((sel) => sel.orden_id === oc.orden_id),
  );

  const comisionTotal = ordenesSeleccionadas.reduce((s, o) => s + Number(o.comision), 0);
  const ivaPreview = comisionTotal * 0.16;
  const totalPreview = comisionTotal + ivaPreview;

  const onValid = (v: Valores) => {
    const ordenesIds = ordenesSeleccionadas.map((o) => o.orden_id);
    const payload = {
      ...v,
      archivo_pdf_path: archivoPdfPath,
      archivo_xml_path: archivoXmlPath,
      ordenes_ids: ordenesIds,
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
              <div className="fl">
                Subtotal <FieldTag origin="calculado" />
              </div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtMoneda(String(comisionTotal))}
              </div>
            </div>
            <div>
              <div className="fl">
                IVA <FieldTag origin="calculado" />
              </div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtMoneda(String(ivaPreview))}
              </div>
            </div>
          </div>
          <div className="fl">
            Total <FieldTag origin="calculado" />
          </div>
          <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
            {fmtMoneda(String(totalPreview))}
          </div>
          <div className="derivado-hint" style={{ marginTop: 6, marginBottom: 10, display: "block" }}>
            Suma de la comisión de cada orden elegida abajo (cada una con su propio %), más IVA.
          </div>

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

        <div className="form-card">
          <div className="form-card-title">Asignación a órdenes estación</div>
          <div className="fl">
            Folio de la Orden Interna <FieldTag origin="derivado" />
          </div>
          <SearchableSelect
            value=""
            onChange={agregarOrden}
            disabled={!agenciaId}
            placeholder="Buscar por folio y agregar…"
            emptyOptionLabel="— Ninguna —"
            emptyResultsLabel={
              !agenciaId
                ? "Selecciona primero una agencia."
                : opcionesDisponibles.length === 0 && ordenesSeleccionadas.length > 0
                  ? "Ya agregaste todas las órdenes cerradas de esta agencia."
                  : "Esta agencia no tiene órdenes cerradas."
            }
            options={opcionesDisponibles.map((oc) => ({
              value: oc.orden_id,
              label: oc.anunciante ? `${oc.folio_orden} — ${oc.anunciante}` : oc.folio_orden,
            }))}
          />
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 11, display: "block" }}>
            Solo lista las órdenes <strong>cerradas</strong> de esa agencia. Puedes elegir varias —
            cada una aporta su propia comisión, con el % ya pactado en ella.
          </div>

          {ordenesSeleccionadas.length === 0 ? (
            <div className="fv muted" style={{ fontSize: 12 }}>
              Sin órdenes agregadas todavía.
            </div>
          ) : (
            ordenesSeleccionadas.map((o) => (
              <div
                key={o.orden_id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r)",
                  padding: "9px 11px",
                  marginBottom: 5,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
                    {o.folio_orden}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>
                      {fmtMoneda(o.comision)}
                    </span>
                    <button
                      type="button"
                      className="btn btn-xs"
                      onClick={() => quitarOrden(o.orden_id)}
                      title="Quitar de esta factura"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <div style={{ fontSize: 11, color: "var(--text3)" }}>
                  {fmtPorcentaje(o.porcentaje)} sobre {fmtMoneda(o.total)}
                  {o.anunciante ? ` · ${o.anunciante}` : ""}
                </div>
              </div>
            ))
          )}
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
