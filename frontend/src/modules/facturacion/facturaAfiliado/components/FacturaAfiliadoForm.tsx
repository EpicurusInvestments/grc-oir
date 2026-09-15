/** Alta/edición de FacturaAfiliado (React Hook Form + Zod).
 *
 * El IVA se CAPTURA, no se calcula: la factura de la emisora puede traer retenciones o
 * conceptos exentos, así que imponerle el 16% rechazaría facturas legítimas (la spec lo
 * marca "Manual"). El TOTAL sí lo calcula el backend — aquí solo se previsualiza.
 *
 * "Asignación a órdenes estación": permite elegir VARIAS OI del afiliado ya elegido (una
 * por una, con búsqueda) — cada una aporta su propio `importe_emisora` a la tarjeta
 * "Asignado". El Subtotal/IVA de la factura se siguen capturando a mano (no se
 * auto-llenan desde las OI elegidas: con varias seleccionadas no habría un solo monto
 * que copiar) — "Sin asignar" es solo la resta contra lo capturado, para que quien
 * factura verifique que cuadra, sin bloquear el guardado si no.
 *
 * La edición hace todo lo que hace el alta (petición del usuario): el afiliado se puede
 * reasignar y esta misma sección edita qué OI tiene asignadas — las que ya estaban
 * (`asignacionesIniciales`) se precargan en la lista y se pueden quitar igual que las
 * nuevas; al guardar se manda la lista completa (`ordenes_estacion_ids`) y el backend
 * reconcilia: agrega lo nuevo, quita lo que ya no está, deja intacto lo que sigue.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { AdjuntoFacturaInput } from "../../facturaCliente/components/AdjuntoFacturaInput";
import { fmtMoneda } from "../../format";
import { useAfiliados, useOrdenesFacturablesAfiliado } from "../../hooks";
import type {
  FacturaAfiliadoCreate,
  FacturaAfiliadoOrden,
  FacturaAfiliadoUpdate,
} from "../../types";

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

/** Fila de la sección "Asignación a órdenes estación" — sea una OI recién agregada del
 *  combo (`importe_emisora` en vivo) o una ya asignada de antes (`monto_asignado`
 *  comprometido, no se recalcula solo porque el importe de la OE haya cambiado). */
interface OrdenSeleccionada {
  orden_estacion_id: string;
  folio_orden_estacion: string;
  nombre_estacion: string | null;
  importe_emisora: string;
}

interface Props {
  isEdit?: boolean;
  defaultValues?: Valores;
  /** Asignaciones ya guardadas, al editar — precargan la sección "Asignación a órdenes
   *  estación" (el `useState` de abajo solo las toma como valor inicial, no se
   *  resincroniza si la prop cambia después del primer render). */
  asignacionesIniciales?: FacturaAfiliadoOrden[];
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
  asignacionesIniciales,
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
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { fecha_factura_afiliado: hoy(), iva_factura_afiliado: "0" },
  });

  // "Asignación a órdenes estación": lista de OI elegidas, fuera del schema de Zod a
  // propósito — es auxiliar, no un dato que RHF valide. Al editar arranca con lo ya
  // asignado (`asignacionesIniciales`); el `monto_asignado` comprometido se muestra
  // como si fuera el "importe_emisora" de esa fila (mismo campo que usan las nuevas).
  const [ordenesSeleccionadas, setOrdenesSeleccionadas] = useState<OrdenSeleccionada[]>(() =>
    (asignacionesIniciales ?? []).map((a) => ({
      orden_estacion_id: a.orden_estacion_id,
      folio_orden_estacion: a.folio_orden_estacion,
      nombre_estacion: a.nombre_estacion,
      importe_emisora: a.monto_asignado,
    })),
  );
  const [archivoPdfPath, setArchivoPdfPath] = useState<string | null>(archivoPdfPathInicial);
  const [archivoXmlPath, setArchivoXmlPath] = useState<string | null>(archivoXmlPathInicial);

  const afiliadoId = watch("afiliado_id");
  const ordenesFacturables = useOrdenesFacturablesAfiliado(afiliadoId || null);

  // Fix: cambiar de afiliado limpia las OI ya elegidas — eran del afiliado ANTERIOR y
  // ya no tiene sentido dejarlas (además de que ninguna pertenecería al nuevo). Se
  // compara contra el afiliado CON EL QUE SE MONTÓ el formulario (capturado una sola
  // vez), no contra "la primera vez que corrió el efecto": `watch()` de RHF puede
  // tardar un tick en reflejar `defaultValues`, así que un `useRef` de "¿ya corrió?"
  // alcanzaba a disparar el primer `setOrdenesSeleccionadas([])` de verdad y borraba
  // las `asignacionesIniciales` recién precargadas al editar.
  const afiliadoIdDeMontaje = useRef(defaultValues?.afiliado_id ?? "");
  useEffect(() => {
    if (afiliadoId === afiliadoIdDeMontaje.current) return;
    setOrdenesSeleccionadas([]);
  }, [afiliadoId]);

  const agregarOrdenEstacion = (id: string) => {
    if (!id) return;
    const oe = (ordenesFacturables.data ?? []).find((o) => o.orden_estacion_id === id);
    if (oe) {
      setOrdenesSeleccionadas((prev) => [
        ...prev,
        {
          orden_estacion_id: oe.orden_estacion_id,
          folio_orden_estacion: oe.folio_orden_estacion,
          nombre_estacion: oe.nombre_estacion,
          importe_emisora: oe.importe_emisora,
        },
      ]);
    }
  };

  const quitarOrdenEstacion = (id: string) => {
    setOrdenesSeleccionadas((prev) => prev.filter((o) => o.orden_estacion_id !== id));
  };

  // Solo ofrece las que todavía no se eligieron — una vez agregada, desaparece del buscador.
  const opcionesDisponibles = (ordenesFacturables.data ?? []).filter(
    (oe) => !ordenesSeleccionadas.some((sel) => sel.orden_estacion_id === oe.orden_estacion_id),
  );

  const asignado = ordenesSeleccionadas.reduce((s, oe) => s + Number(oe.importe_emisora), 0);
  const subtotalCapturado = Number(watch("monto_factura_afiliado")) || 0;
  const sinAsignar = subtotalCapturado - asignado;

  const m = Number(watch("monto_factura_afiliado") ?? 0);
  const i = Number(watch("iva_factura_afiliado") ?? 0);
  const totalPreview = Number.isNaN(m) || Number.isNaN(i) ? null : (m + i).toFixed(2);

  const onValid = (v: Valores) => {
    const ordenesEstacionIds = ordenesSeleccionadas.map((oe) => oe.orden_estacion_id);
    if (isEdit) {
      onSubmit({
        afiliado_id: v.afiliado_id,
        factura_emisora: v.factura_emisora,
        fecha_factura_afiliado: v.fecha_factura_afiliado,
        monto_factura_afiliado: v.monto_factura_afiliado,
        iva_factura_afiliado: v.iva_factura_afiliado,
        archivo_pdf_path: archivoPdfPath,
        archivo_xml_path: archivoXmlPath,
        ordenes_estacion_ids: ordenesEstacionIds,
      } satisfies FacturaAfiliadoUpdate);
    } else {
      onSubmit({
        ...v,
        archivo_pdf_path: archivoPdfPath,
        archivo_xml_path: archivoXmlPath,
        ordenes_estacion_ids: ordenesEstacionIds,
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
          {/* `value` explícito (además de `register`): las opciones llegan de una
              consulta async (`useAfiliados`), y el `ref` de `register` solo fija el
              valor inicial UNA vez, al montar — si en ese momento el catálogo todavía
              no cargó, el afiliado ya elegido (al editar) se quedaría sin seleccionar
              en el DOM aunque RHF internamente lo tenga bien. Con `value` controlado,
              React lo vuelve a aplicar en cuanto las opciones existen. */}
          <select className="fsel" value={watch("afiliado_id") ?? ""} {...register("afiliado_id")}>
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

        <div className="form-card">
          <div className="form-card-title">Asignación a órdenes estación</div>
          <div className="fl">
            Folio de la Orden Interna <FieldTag origin="derivado" />
          </div>
          <SearchableSelect
            value=""
            onChange={agregarOrdenEstacion}
            disabled={!afiliadoId}
            placeholder="Buscar por folio y agregar…"
            emptyOptionLabel="— Ninguna —"
            emptyResultsLabel={
              !afiliadoId
                ? "Selecciona primero un afiliado."
                : opcionesDisponibles.length === 0 && ordenesSeleccionadas.length > 0
                  ? "Ya agregaste todas las órdenes internas cerradas de este afiliado."
                  : "Este afiliado no tiene órdenes internas cerradas."
            }
            options={opcionesDisponibles.map((oe) => ({
              value: oe.orden_estacion_id,
              label: oe.nombre_estacion
                ? `${oe.folio_orden_estacion} — ${oe.nombre_estacion}`
                : oe.folio_orden_estacion,
            }))}
          />
          <div className="derivado-hint" style={{ marginTop: -6, marginBottom: 11, display: "block" }}>
            Opcional: solo lista las órdenes internas <strong>cerradas</strong> de ese afiliado. Puedes
            elegir varias — la factura queda asignada a cada una al guardar.
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 11 }}>
            <div style={{ flex: 1, background: "var(--surface2)", borderRadius: "var(--r)", padding: "8px 11px" }}>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Asignado
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600 }}>
                {fmtMoneda(String(asignado))}
              </div>
            </div>
            <div
              style={{
                flex: 1,
                background: sinAsignar === 0 ? "var(--green-bg)" : "var(--red-bg)",
                borderRadius: "var(--r)",
                padding: "8px 11px",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: sinAsignar === 0 ? "var(--green-text)" : "var(--red-text)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Sin asignar
              </div>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 14,
                  fontWeight: 600,
                  color: sinAsignar === 0 ? "var(--green-text)" : "var(--red-text)",
                }}
              >
                {fmtMoneda(String(sinAsignar))}
              </div>
            </div>
          </div>

          {ordenesSeleccionadas.length === 0 ? (
            <div className="fv muted" style={{ fontSize: 12 }}>
              Sin órdenes internas agregadas todavía.
            </div>
          ) : (
            ordenesSeleccionadas.map((oe) => (
              <div
                key={oe.orden_estacion_id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r)",
                  padding: "9px 11px",
                  marginBottom: 5,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
                    {oe.folio_orden_estacion}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>
                      {fmtMoneda(oe.importe_emisora)}
                    </span>
                    <button
                      type="button"
                      className="btn btn-xs"
                      onClick={() => quitarOrdenEstacion(oe.orden_estacion_id)}
                      title="Quitar de esta factura"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                {oe.nombre_estacion && (
                  <div style={{ fontSize: 11, color: "var(--text3)" }}>{oe.nombre_estacion}</div>
                )}
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
