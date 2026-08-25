/** Alta de FacturaCliente (React Hook Form + Zod).
 *
 * Solo pide lo que Facturación CAPTURA. Todo lo demás —receptor, RFC, dirección, periodo
 * de transmisión, subtotal, IVA y total— lo deriva el backend de la OrdenCliente; el
 * schema del servidor rechaza esos campos si se mandan (`extra="forbid"`).
 *
 * El selector de orden ofrece SOLO las que están en `orden_cerrada`: es la precondición
 * del backend, y mostrar aquí una orden que va a dar 400 sería enseñar un callejón.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { useCuentasContables, useMetodosDePago, useOrdenesFacturables } from "../../hooks";
import type { FacturaClienteCreate } from "../../types";

const schema = z.object({
  orden_id: z.string().min(1, "Selecciona la orden a facturar."),
  numero_factura: z.string().trim().min(1, "El folio interno es obligatorio.").max(30),
  numero_pedido: z.string().trim().max(50).optional(),
  referencia_adicional: z.string().trim().max(150).optional(),
  descripcion_factura: z.string().trim().min(1, "La descripción es obligatoria."),
  observaciones_factura: z.string().trim().optional(),
  fecha_factura: z.string().min(1, "La fecha de emisión es obligatoria."),
  cuenta_contable_id: z.string().min(1, "Selecciona la cuenta contable."),
  metodo_pago_clave: z.string().min(1, "Selecciona el método de pago."),
  info_cuenta_pago: z.string().trim().optional(),
  layout_factura: z.string().trim().max(200).optional(),
});

type Valores = z.infer<typeof schema>;

interface Props {
  /** Cuando la orden ya viene decidida (alta desde la bandeja "Listas para facturar"):
   *  se prellena y se muestra fija, sin selector — elegir otra ahí no tendría sentido. */
  ordenFija?: { orden_id: string; folio: string } | null;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaClienteCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function FacturaClienteForm({
  ordenFija = null,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: Props) {
  // Con la orden ya fijada no hace falta traer el catálogo de órdenes facturables.
  const ordenes = useOrdenesFacturables();
  const cuentas = useCuentasContables();
  const metodos = useMetodosDePago();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { fecha_factura: hoy(), orden_id: ordenFija?.orden_id ?? "" },
  });

  const ordenId = watch("orden_id");

  return (
    <form className="form" onSubmit={handleSubmit((v) => onSubmit(v as FacturaClienteCreate))}>
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nueva factura al cliente</div>
        <div className="dh-sub">
          Solo se listan órdenes en «orden cerrada»: son las únicas facturables.
        </div>
      </div>

      <div className="fg">
        <label className="fl">
          Orden a facturar <span className="req">*</span>
          {ordenFija && <FieldTag origin="heredado" />}
        </label>
        {ordenFija ? (
          <div className="fv mono strong">{ordenFija.folio}</div>
        ) : (
          <>
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
          </>
        )}
        {errors.orden_id && <div className="fe">{errors.orden_id.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="numero_factura">
          Folio interno <span className="req">*</span>
        </label>
        <input id="numero_factura" className="in mono" {...register("numero_factura")} />
        {errors.numero_factura && <div className="fe">{errors.numero_factura.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="numero_pedido">
          Número de pedido del cliente
        </label>
        <input id="numero_pedido" className="in" {...register("numero_pedido")} />
      </div>

      <div className="fg">
        <label className="fl" htmlFor="descripcion_factura">
          Descripción de los servicios <span className="req">*</span>
        </label>
        <textarea id="descripcion_factura" className="in ta" {...register("descripcion_factura")} />
        {errors.descripcion_factura && <div className="fe">{errors.descripcion_factura.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="fecha_factura">
          Fecha de emisión <span className="req">*</span>
        </label>
        <input id="fecha_factura" type="date" className="in" {...register("fecha_factura")} />
        {errors.fecha_factura && <div className="fe">{errors.fecha_factura.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="cuenta_contable_id">
          Cuenta contable <span className="req">*</span> <FieldTag origin="catalogo" />
        </label>
        <select id="cuenta_contable_id" className="in" {...register("cuenta_contable_id")}>
          <option value="">— Selecciona —</option>
          {(cuentas.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.etiqueta}
            </option>
          ))}
        </select>
        {errors.cuenta_contable_id && <div className="fe">{errors.cuenta_contable_id.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="metodo_pago_clave">
          Método de pago <span className="req">*</span> <FieldTag origin="catalogo" />
        </label>
        <select id="metodo_pago_clave" className="in" {...register("metodo_pago_clave")}>
          <option value="">— Selecciona —</option>
          {(metodos.data ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.etiqueta}
            </option>
          ))}
        </select>
        {/* Se guarda la CLAVE, no un FK: MetodoPago vive en ConstantesSistema. */}
        {errors.metodo_pago_clave && <div className="fe">{errors.metodo_pago_clave.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="info_cuenta_pago">
          Datos de cuenta para el pago
        </label>
        <textarea id="info_cuenta_pago" className="in ta" {...register("info_cuenta_pago")} />
      </div>

      <div className="fg">
        <label className="fl" htmlFor="layout_factura">
          Layout de impresión
        </label>
        <input id="layout_factura" className="in" {...register("layout_factura")} />
      </div>

      {submitError && <div className="state-msg error">{submitError}</div>}

      <div className="fa">
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
