/** Alta de FacturaCliente — formulario largo por secciones.
 *
 * Estructura de la pantalla aprobada `Fase_2_-_Facturacion.html`: bloque ámbar con los
 * datos heredados de la orden y luego tarjetas por sección (Identificación, Receptor,
 * Concepto, Montos, Configuración contable, Fechas). No es el panel de detalle: es el
 * "form full-screen" que el `frontend/CLAUDE.md` reserva justo para la preparación de una
 * factura.
 *
 * Lo que el backend DERIVA de la orden (periodo, subtotal, emisor) se muestra pero no se
 * captura. El receptor sí es editable —la pantalla aprobada lo marca así— y viaja como
 * override opcional. Los IMPORTES calculados (IVA y total) se previsualizan aquí y los
 * recalcula el servicio: el front nunca los manda.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, MultiSearchableSelect, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useCuentasContables,
  useFacturasDelAnunciante,
  useMetodosDePago,
  useOrdenesFacturables,
} from "../../hooks";
import { ESTADO_FACTURACION_LABEL, type FacturaClienteCreate, type OrdenPorFacturar } from "../../types";

const schema = z.object({
  orden_id: z.string().min(1, "Selecciona la orden a facturar."),
  numero_factura: z.string().trim().min(1, "El número de factura es obligatorio.").max(30),
  numero_pedido: z.string().trim().max(50).optional(),
  referencia_adicional: z.string().trim().max(150).optional(),
  facturas_relacionadas_ids: z.array(z.string()).default([]),
  razon_social_facturacion: z.string().trim().min(1, "La razón social es obligatoria.").max(200),
  rfc_facturacion: z.string().trim().min(1, "El RFC es obligatorio.").max(13),
  direccion_facturacion: z.string().trim().optional(),
  descripcion_factura: z.string().trim().min(1, "La descripción es obligatoria."),
  observaciones_factura: z.string().trim().optional(),
  fecha_factura: z.string().min(1, "La fecha de la factura es obligatoria."),
  cuenta_contable_id: z.string().min(1, "Selecciona la cuenta contable."),
  metodo_pago_clave: z.string().min(1, "Selecciona el método de pago."),
  info_cuenta_pago: z.string().trim().optional(),
});

type Valores = z.infer<typeof schema>;

interface Props {
  /** Orden ya elegida (alta desde la bandeja): sus datos pre-cargan el formulario. */
  orden?: OrdenPorFacturar | null;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaClienteCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

/** Descripción sugerida, con el mismo texto que arma la pantalla aprobada. */
function descripcionSugerida(o: OrdenPorFacturar | null | undefined): string {
  if (!o) return "";
  const spots =
    o.total_spots != null && o.duracion_spot
      ? ` ${o.total_spots} spots de ${o.duracion_spot}`
      : "";
  return (
    `Servicios de transmisión publicitaria — ${o.producto ?? "Campaña"} del ` +
    `${o.fecha_inicio_campania} al ${o.fecha_fin_campania}.${spots} según orden ` +
    `${o.numero_orden_cliente}.`
  );
}

export function FacturaClienteForm({
  orden = null,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: Props) {
  const ordenes = useOrdenesFacturables();
  const cuentas = useCuentasContables();
  const metodos = useMetodosDePago();
  const facturasDelAnunciante = useFacturasDelAnunciante(orden?.anunciante_id);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: {
      orden_id: orden?.orden_id ?? "",
      numero_pedido: orden?.numero_orden_cliente ?? "",
      razon_social_facturacion: orden?.receptor_razon_social ?? "",
      rfc_facturacion: orden?.receptor_rfc ?? "",
      direccion_facturacion: orden?.receptor_direccion ?? "",
      descripcion_factura: descripcionSugerida(orden),
      fecha_factura: hoy(),
      facturas_relacionadas_ids: [],
    },
  });

  const ordenId = watch("orden_id");
  const facturasRelacionadasIds = watch("facturas_relacionadas_ids");

  // IVA y total son PREVISUALIZACIÓN: los calcula el servicio sobre el subtotal heredado.
  const subtotal = Number(orden?.subtotal ?? 0);
  const iva = subtotal * 0.16;
  const total = subtotal + iva;

  return (
    <form
      onSubmit={handleSubmit((v) => onSubmit(v as FacturaClienteCreate))}
      style={{ maxWidth: 900 }}
    >
      <SavingOverlay visible={!!submitting} />

      {orden && (
        <div className="heredado-block">
          <div className="heredado-title">Datos heredados de la orden</div>
          <div className="heredado-grid">
            <div className="heredado-row">
              <span className="heredado-lbl">Orden origen</span>
              <span className="heredado-val mono">{orden.folio_orden}</span>
            </div>
            <div className="heredado-row">
              <span className="heredado-lbl">Pedido</span>
              <span className="heredado-val mono">{orden.numero_orden_cliente}</span>
            </div>
            <div className="heredado-row">
              <span className="heredado-lbl">Empresa emisora</span>
              <span className="heredado-val">{oGuion(orden.empresa_emisora)}</span>
            </div>
            <div className="heredado-row">
              <span className="heredado-lbl">Vendedor</span>
              <span className="heredado-val">{oGuion(orden.vendedor)}</span>
            </div>
            <div className="heredado-row">
              <span className="heredado-lbl">Período transmisión</span>
              <span className="heredado-val mono">
                {fmtFecha(orden.fecha_inicio_campania)} → {fmtFecha(orden.fecha_fin_campania)}
              </span>
            </div>
            <div className="heredado-row">
              <span className="heredado-lbl">Subtotal</span>
              <span className="heredado-val mono">{fmtMoneda(orden.subtotal)}</span>
            </div>
          </div>
        </div>
      )}

      {/* ── Identificación ── */}
      <div className="form-card">
        <div className="form-card-title">Identificación de la factura</div>

        {!orden && (
          <>
            <div className="fl fl-required">Orden a facturar</div>
            <SearchableSelect
              value={ordenId ?? ""}
              onChange={(v) => setValue("orden_id", v, { shouldValidate: true })}
              placeholder={ordenes.isLoading ? "Cargando órdenes…" : "Busca por folio o número…"}
              options={(ordenes.data ?? []).map((o) => ({
                value: o.orden_id,
                label: `${o.folio_orden} · ${o.numero_orden_cliente}`,
              }))}
            />
            {!ordenes.isLoading && (ordenes.data?.length ?? 0) === 0 && (
              <div className="fe">No hay órdenes cerradas pendientes de facturar.</div>
            )}
            {errors.orden_id && <div className="fe">{errors.orden_id.message}</div>}
          </>
        )}

        <div className="r2">
          <div>
            <div className="fl fl-required">Número de factura</div>
            <input className="fi mono" placeholder="Ej. A-001246" {...register("numero_factura")} />
            {errors.numero_factura && <div className="fe">{errors.numero_factura.message}</div>}
          </div>
          <div>
            <div className="fl">Número de pedido</div>
            <input className="fi mono" {...register("numero_pedido")} />
          </div>
        </div>
        <div className="fl">Referencia adicional</div>
        <input
          className="fi"
          placeholder="Referencia para reconciliación con cliente"
          {...register("referencia_adicional")}
        />

        <div className="fl">Factura relacionada (si aplica)</div>
        <MultiSearchableSelect
          value={facturasRelacionadasIds ?? []}
          onChange={(v) => setValue("facturas_relacionadas_ids", v)}
          disabled={!orden}
          placeholder={
            !orden
              ? "Elige primero la orden a facturar…"
              : facturasDelAnunciante.isLoading
                ? "Cargando facturas del anunciante…"
                : "Busca por número de factura…"
          }
          emptyResultsLabel="Este anunciante no tiene otras facturas."
          options={(facturasDelAnunciante.data?.items ?? []).map((f) => ({
            value: f.factura_id,
            label: `${f.numero_factura} · ${ESTADO_FACTURACION_LABEL[f.estado_facturacion]}`,
          }))}
        />
      </div>

      {/* ── Receptor ── */}
      <div className="form-card">
        <div className="form-card-title">Receptor de la factura</div>
        {orden && (
          <div className="receptor-nota">
            {orden.facturacion_directa_cliente || !orden.agencia
              ? `Facturación directa al cliente — la factura va a ${orden.anunciante}.`
              : `Vía agencia — la factura va a la agencia ${orden.agencia}.`}
          </div>
        )}
        <div className="fl fl-required">
          Razón social <FieldTag origin="heredado" />
        </div>
        <input className="fi" {...register("razon_social_facturacion")} />
        {errors.razon_social_facturacion && (
          <div className="fe">{errors.razon_social_facturacion.message}</div>
        )}
        <div className="r2">
          <div>
            <div className="fl fl-required">RFC</div>
            <input className="fi mono" maxLength={13} {...register("rfc_facturacion")} />
            {errors.rfc_facturacion && <div className="fe">{errors.rfc_facturacion.message}</div>}
          </div>
          <div />
        </div>
        <div className="fl">Dirección</div>
        <textarea className="ftxt" {...register("direccion_facturacion")} />
      </div>

      {/* ── Concepto ── */}
      <div className="form-card">
        <div className="form-card-title">Concepto y observaciones</div>
        <div className="fl fl-required">
          Descripción del servicio (aparece en el cuerpo de la factura)
        </div>
        <textarea
          className="ftxt"
          style={{ minHeight: 80 }}
          {...register("descripcion_factura")}
        />
        {errors.descripcion_factura && (
          <div className="fe">{errors.descripcion_factura.message}</div>
        )}
        <div className="fl">Observaciones adicionales</div>
        <textarea
          className="ftxt"
          placeholder="Notas que aparecen en la factura…"
          {...register("observaciones_factura")}
        />
      </div>

      {/* ── Montos ── */}
      <div className="form-card">
        <div className="form-card-title">Montos</div>
        <div className="r3">
          <div>
            <div className="fl">
              Subtotal <FieldTag origin="heredado" />
            </div>
            {/* Solo lectura: es la base de los calculados y viene de la orden. Editarlo
                rompería la correspondencia con lo que F1 cerró. */}
            <div className="fv mono big">{fmtMoneda(orden?.subtotal ?? null)}</div>
          </div>
          <div>
            <div className="fl">
              IVA <FieldTag origin="calculado" />
            </div>
            <div className="fv mono big">{fmtMoneda(iva.toFixed(2))}</div>
          </div>
          <div>
            <div className="fl">
              Total <FieldTag origin="calculado" />
            </div>
            <div className="fv mono big" style={{ color: "var(--blue-text)" }}>
              {fmtMoneda(total.toFixed(2))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Configuración contable ── */}
      <div className="form-card">
        <div className="form-card-title">Configuración contable</div>
        <div className="fl fl-required">
          Cuenta contable <FieldTag origin="catalogo" />
        </div>
        <select className="fsel" {...register("cuenta_contable_id")}>
          <option value="">— Selecciona —</option>
          {(cuentas.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.etiqueta}
            </option>
          ))}
        </select>
        {errors.cuenta_contable_id && <div className="fe">{errors.cuenta_contable_id.message}</div>}

        <div className="fl fl-required">
          Método de pago <FieldTag origin="catalogo" />
        </div>
        {/* Se guarda la CLAVE, no un FK: MetodoPago vive en ConstantesSistema. */}
        <select className="fsel" {...register("metodo_pago_clave")}>
          <option value="">— Selecciona —</option>
          {(metodos.data ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.etiqueta}
            </option>
          ))}
        </select>
        {errors.metodo_pago_clave && <div className="fe">{errors.metodo_pago_clave.message}</div>}

        <div className="fl">Información cuenta de pago (aparece en factura)</div>
        <textarea
          className="ftxt"
          placeholder="Ej. BBVA · CLABE 012180001234567890 · Titular…"
          {...register("info_cuenta_pago")}
        />
      </div>

      {/* ── Fechas ── */}
      <div className="form-card">
        <div className="form-card-title">Fechas</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Fecha de la factura</div>
            <input type="date" className="fi" {...register("fecha_factura")} />
            {errors.fecha_factura && <div className="fe">{errors.fecha_factura.message}</div>}
          </div>
          <div>
            <div className="fl">Fecha de entrega</div>
            <div className="fv muted" style={{ fontSize: 12 }}>
              Se registra al marcar la factura como entregada.
            </div>
          </div>
        </div>
      </div>

      {submitError && <div className="state-msg error">{submitError}</div>}

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-primary" disabled={submitting}>
          Crear factura (preparada)
        </button>
      </div>
    </form>
  );
}
