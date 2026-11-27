/** Alta de una Nota de Crédito (petición del usuario, con captura) — `FacturaCliente`
 * con `tipo_comprobante: "E"`, SIEMPRE lanzada desde la factura que se va a acreditar
 * ("+ Nota de crédito" en su detalle, `FacturasClientePage.tsx`): a diferencia de
 * `FacturaClienteForm.tsx` (que deriva TODO de una o varias `OrdenCliente`), esta no
 * tiene orden de origen — el receptor/empresa se HEREDAN de `origen` sin mostrarse
 * editables aquí (ya los fijó el servicio al crear).
 *
 * Método de pago SIEMPRE `PUE` (fijo, no se captura, se muestra solo informativo —
 * petición del usuario: "que no se pueda modificar... para que el usuario no se
 * confunda"). Forma de pago SÍ se captura: precargada con la de `origen` pero
 * editable. Monto e IVA se precargan con los de `origen` (`subtotal_factura`/
 * `iva_factura`) y son editables (petición del usuario 2026-11-27) — el backend los
 * niega antes de persistir (quedan negativos, "para efecto de reportes").
 *
 * Número de factura: PROPUESTO (ADR-295, petición del usuario) con el siguiente
 * consecutivo `NC-AAAA-MM-...` disponible, pero sigue siendo editable — solo se
 * precarga si el usuario no había escrito nada todavía.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { useConstantes } from "@/modules/catalogos/constantesSistema/hooks";
import { DateInput, FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { fmtFolio } from "../../format";
import { useCuentasContables, useFormasDePago, useSiguienteNumeroFactura } from "../../hooks";
import {
  MOTIVOS_NOTA_CREDITO,
  type FacturaCliente,
  type FacturaClienteCreate,
  type MotivoNotaCredito,
} from "../../types";

// Mismo formato que valida el backend (`NUMERO_FACTURA_REGEX`, factura_cliente.py):
// "NC-AAAA-MM-folio" — el usuario lo captura a mano, sin consecutivo automático.
const NUMERO_FACTURA_REGEX = /^NC-[0-9]{4}-[0-9]{2}-[0-9]+$/;

const schema = z.object({
  numero_factura: z
    .string()
    .trim()
    .min(1, "El folio es obligatorio.")
    .max(30)
    .regex(
      NUMERO_FACTURA_REGEX,
      "Formato inválido: debe ser 'NC-AAAA-MM-folio' (ej. NC-2026-11-0071).",
    ),
  numero_pedido: z.string().trim().max(50).optional(),
  referencia_adicional: z.string().trim().max(150).optional(),
  motivo_nota_credito: z.string().min(1, "Selecciona el motivo."),
  forma_pago_clave: z.string().min(1, "Selecciona la forma de pago."),
  monto_nota_credito: z
    .string()
    .min(1, "Captura el monto a acreditar.")
    .refine((v) => Number(v) > 0, "El monto debe ser mayor a 0."),
  iva_nota_credito: z
    .string()
    .min(1, "Captura el IVA a acreditar.")
    .refine((v) => Number(v) >= 0, "El IVA no puede ser negativo."),
  descripcion_factura: z.string().trim().min(1, "La descripción es obligatoria."),
  observaciones_factura: z.string().trim().optional(),
  fecha_factura: z.string().min(1, "La fecha es obligatoria."),
  cuenta_contable_id: z.string().min(1, "Selecciona la cuenta contable."),
  clave_prod_serv: z.string().min(1, "Selecciona la clave de producto o servicio."),
  clave_unidad: z.string().min(1, "Selecciona la clave de unidad."),
  moneda_sat: z.string().min(1, "Selecciona la moneda."),
  tipo_relacion_sat: z.string().trim().max(2).optional(),
  uso_cfdi: z.string().trim().max(5).optional(),
});

type Valores = z.infer<typeof schema>;

interface Props {
  /** La factura que se va a acreditar — fija, no editable aquí. */
  origen: FacturaCliente;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: FacturaClienteCreate) => void;
  onCancel: () => void;
}

const hoy = () => new Date().toISOString().slice(0, 10);

export function NotaCreditoForm({ origen, submitting, submitError, onSubmit, onCancel }: Props) {
  const cuentas = useCuentasContables();
  const formas = useFormasDePago();
  const siguienteNumero = useSiguienteNumeroFactura("E");
  const { useList } = useConstantes();
  const clavesProdServ = useList({ grupo: "ClaveProdServ", activo: true, size: 100 });
  const clavesUnidad = useList({ grupo: "ClaveUnidad", activo: true, size: 100 });
  const monedas = useList({ grupo: "MonedaSAT", activo: true, size: 100 });
  const tiposRelacion = useList({ grupo: "TipoRelacion", activo: true, size: 100 });
  const usosCfdi = useList({ grupo: "UsoCFDI", activo: true, size: 100 });

  const {
    register,
    control,
    handleSubmit,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: {
      descripcion_factura: `Nota de crédito de la factura ${origen.numero_factura}`,
      fecha_factura: hoy(),
      clave_prod_serv: origen.clave_prod_serv ?? "",
      clave_unidad: origen.clave_unidad ?? "",
      moneda_sat: origen.moneda_sat ?? "",
      uso_cfdi: "G02",
      cuenta_contable_id: origen.cuenta_contable_id ?? "",
      forma_pago_clave: origen.forma_pago_clave ?? "",
      monto_nota_credito: origen.subtotal_factura,
      iva_nota_credito: origen.iva_factura,
    },
  });

  // Precarga "Número de factura" con la sugerencia (ADR-295) SOLO si el usuario no
  // había escrito nada todavía — nunca pisa lo que ya esté tecleando.
  useEffect(() => {
    if (siguienteNumero.data && !getValues("numero_factura")) {
      setValue("numero_factura", siguienteNumero.data);
    }
  }, [siguienteNumero.data, getValues, setValue]);

  return (
    <form
      onSubmit={handleSubmit((valores) =>
        onSubmit({
          ...valores,
          numero_factura: valores.numero_factura.toUpperCase(),
          ordenes_ids: [],
          facturas_relacionadas_ids: [origen.factura_id],
          tipo_comprobante: "E",
          motivo_nota_credito: valores.motivo_nota_credito as MotivoNotaCredito,
          // Método de pago SIEMPRE PUE (petición del usuario, no se captura). Forma de
          // pago SÍ viene del formulario (precargada con la de origen, editable).
          metodo_pago_clave: "PUE",
        } as FacturaClienteCreate),
      )}
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <SavingOverlay visible={!!submitting} />

      <div className="db" style={{ maxWidth: 900 }}>
      <div className="heredado-block">
        <div className="heredado-title">Factura de origen</div>
        <div className="heredado-grid">
          <div className="heredado-row">
            <span className="heredado-lbl">Factura</span>
            <span className="heredado-val mono">{fmtFolio(origen.numero_factura)}</span>
          </div>
          <div className="heredado-row">
            <span className="heredado-lbl">Receptor</span>
            <span className="heredado-val">{origen.razon_social_facturacion}</span>
          </div>
          <div className="heredado-row">
            <span className="heredado-lbl">Método de pago</span>
            <span className="heredado-val mono">PUE</span>
          </div>
        </div>
      </div>

      <div className="form-card">
        <div className="form-card-title">Identificación de la Nota de Crédito</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Número de factura</div>
            <input
              className="fi mono"
              placeholder="Ej. NC-2026-11-0071"
              {...register("numero_factura")}
            />
            {errors.numero_factura && <div className="fe">{errors.numero_factura.message}</div>}
          </div>
          <div>
            <div className="fl">Número de pedido</div>
            <input className="fi mono" {...register("numero_pedido")} />
          </div>
        </div>
        <div className="fl">Referencia adicional</div>
        <input className="fi" {...register("referencia_adicional")} />

        <div className="fl fl-required">Motivo</div>
        <select className="fsel" {...register("motivo_nota_credito")}>
          <option value="">— Selecciona —</option>
          {MOTIVOS_NOTA_CREDITO.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        {errors.motivo_nota_credito && (
          <div className="fe">{errors.motivo_nota_credito.message}</div>
        )}
      </div>

      <div className="form-card">
        <div className="form-card-title">Concepto y observaciones</div>
        <div className="fl fl-required">Descripción (aparece en el cuerpo de la factura)</div>
        <textarea
          className="ftxt"
          style={{ minHeight: 80 }}
          {...register("descripcion_factura")}
        />
        {errors.descripcion_factura && (
          <div className="fe">{errors.descripcion_factura.message}</div>
        )}
        <div className="fl">Observaciones adicionales</div>
        <textarea className="ftxt" {...register("observaciones_factura")} />
      </div>

      <div className="form-card">
        <div className="form-card-title">Monto a acreditar</div>
        <div className="r2">
          <div>
            <div className="fl fl-required">Monto (sin IVA)</div>
            <input
              className="fi mono"
              type="number"
              step="0.01"
              min="0.01"
              placeholder="0.00"
              {...register("monto_nota_credito")}
            />
            {errors.monto_nota_credito && (
              <div className="fe">{errors.monto_nota_credito.message}</div>
            )}
          </div>
          <div>
            <div className="fl fl-required">IVA</div>
            <input
              className="fi mono"
              type="number"
              step="0.01"
              min="0"
              placeholder="0.00"
              {...register("iva_nota_credito")}
            />
            {errors.iva_nota_credito && (
              <div className="fe">{errors.iva_nota_credito.message}</div>
            )}
          </div>
        </div>
        <div className="fv muted" style={{ fontSize: 11 }}>
          Ambos se precargan con el Monto e IVA de la factura de origen — se guardan con
          signo negativo (para efecto de reportes), captúralos en positivo. Ajusta el IVA
          si la acreditación es parcial o proporcional.
        </div>
      </div>

      <div className="form-card">
        <div className="form-card-title">Configuración contable y fiscal</div>
        <div className="fl fl-required">
          Cuenta contable <FieldTag origin="catalogo" />
        </div>
        <Controller
          control={control}
          name="cuenta_contable_id"
          render={({ field }) => (
            <SearchableSelect
              value={field.value}
              onChange={field.onChange}
              options={(cuentas.data ?? []).map((c) => ({ value: c.id, label: c.etiqueta }))}
            />
          )}
        />
        {errors.cuenta_contable_id && (
          <div className="fe">{errors.cuenta_contable_id.message}</div>
        )}

        <div className="fl fl-required">
          Forma de pago <FieldTag origin="catalogo" />
        </div>
        {/* Se guarda la CLAVE, no un FK: FormaPago vive en ConstantesSistema. Precargada
            con la de la factura de origen (defaultValues), pero editable. */}
        <select className="fsel" {...register("forma_pago_clave")}>
          <option value="">— Selecciona —</option>
          {(formas.data ?? []).map((f) => (
            <option key={f.id} value={f.id}>
              {f.etiqueta}
            </option>
          ))}
        </select>
        {errors.forma_pago_clave && <div className="fe">{errors.forma_pago_clave.message}</div>}

        <div className="fl fl-required">
          Clave del producto o servicio <FieldTag origin="catalogo" />
        </div>
        <Controller
          control={control}
          name="clave_prod_serv"
          render={({ field }) => (
            <SearchableSelect
              value={field.value}
              onChange={field.onChange}
              options={(clavesProdServ.data?.items ?? []).map((c) => ({
                value: c.clave,
                label: `${c.clave} · ${c.descripcion}`,
              }))}
            />
          )}
        />
        {errors.clave_prod_serv && <div className="fe">{errors.clave_prod_serv.message}</div>}

        <div className="fl fl-required">
          Clave de unidad <FieldTag origin="catalogo" />
        </div>
        <Controller
          control={control}
          name="clave_unidad"
          render={({ field }) => (
            <SearchableSelect
              value={field.value}
              onChange={field.onChange}
              options={(clavesUnidad.data?.items ?? []).map((c) => ({
                value: c.clave,
                label: `${c.clave} · ${c.descripcion}`,
              }))}
            />
          )}
        />
        {errors.clave_unidad && <div className="fe">{errors.clave_unidad.message}</div>}

        <div className="fl fl-required">
          Moneda <FieldTag origin="catalogo" />
        </div>
        <select className="fsel" {...register("moneda_sat")}>
          <option value="">— Selecciona —</option>
          {(monedas.data?.items ?? []).map((c) => (
            <option key={c.clave} value={c.clave}>
              {c.clave} · {c.descripcion}
            </option>
          ))}
        </select>
        {errors.moneda_sat && <div className="fe">{errors.moneda_sat.message}</div>}

        <div className="fl">
          Tipo de relación SAT <FieldTag origin="catalogo" />
        </div>
        <select className="fsel" {...register("tipo_relacion_sat")}>
          <option value="">— Sin capturar —</option>
          {(tiposRelacion.data?.items ?? []).map((c) => (
            <option key={c.clave} value={c.clave}>
              {c.clave} · {c.descripcion}
            </option>
          ))}
        </select>

        <div className="fl">
          Uso de CFDI <FieldTag origin="catalogo" />
        </div>
        <Controller
          control={control}
          name="uso_cfdi"
          render={({ field }) => (
            <SearchableSelect
              value={field.value ?? ""}
              onChange={field.onChange}
              emptyOptionLabel="— Sin capturar —"
              options={(usosCfdi.data?.items ?? []).map((c) => ({
                value: c.clave,
                label: `${c.clave} · ${c.descripcion}`,
              }))}
            />
          )}
        />
      </div>

      <div className="form-card">
        <div className="form-card-title">Fecha</div>
        <div className="fl fl-required">Fecha de la Nota de Crédito</div>
        <Controller
          control={control}
          name="fecha_factura"
          render={({ field }) => <DateInput value={field.value} onChange={field.onChange} />}
        />
        {errors.fecha_factura && <div className="fe">{errors.fecha_factura.message}</div>}
      </div>

      {submitError && <div className="state-msg error">{submitError}</div>}
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-primary" disabled={submitting}>
          Crear Nota de Crédito (preparada)
        </button>
      </div>
    </form>
  );
}
