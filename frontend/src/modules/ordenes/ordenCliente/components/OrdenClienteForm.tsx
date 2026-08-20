/** Formulario de alta/edición de OrdenCliente — pantalla completa, dos columnas (captura +
 * panel de resumen), como pide el patrón "form full-screen" de la propuesta.
 *
 * Selectores encadenados de verdad (E.2): Contrato y Marca se filtran por el anunciante
 * elegido (son relaciones anidadas de Anunciante en F0), con estado vacío explícito si un
 * anunciante no tuviera ninguno. Agencia y dirección de facturación se SUGIEREN desde el
 * anunciante (se prellenan solo si el campo está vacío) sin forzar la relación, igual que
 * en el prototipo aprobado.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { MoneyInput, SavingOverlay, SensitiveField } from "@/shared/ui";

import { ChecklistVoBo } from "../../components/ChecklistVoBo";
import { FROZEN_STATES, IVA_RATE, isChecklistComplete, OBS_PREDEFINIDAS } from "../../constants";
import { fmtMonto } from "../../format";
import {
  agencias,
  anunciantes,
  categorias,
  contratosVigentesDeAnunciante,
  empresasFacturadoras,
  findAgencia,
  findVendedor,
  marcasDeAnunciante,
  vendedores,
} from "../../state/catalogosCache";
import { esComisionOverride } from "../../state/selectors";
import type { EstadoOC, OrdenClienteInput } from "../../types";

/** El backend real (spec `DuracionSpot`) solo acepta estos 4 valores. */
const OPCIONES_DURACION = ["20s", "30s", "60s", "mencion"] as const;

const numeroOpcionalPct = () =>
  z
    .string()
    .trim()
    .optional()
    .refine((v) => v == null || v === "" || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 100), "El % debe estar entre 0 y 100.");

/** `isEdit` decide si aplica la regla de "fecha de inicio no puede ser pasada": es SOLO de
 * alta (ver `OrdenClienteCreate._valida_fechas` en el backend) — al editar, la campaña de
 * una orden ya en curso por definición ya "empezó" y no debe bloquearse por el simple paso
 * del calendario. */
function buildSchema(isEdit: boolean) {
  return z
    .object({
    numero_orden_cliente: z.string().trim().min(1, "El no. de orden del cliente es obligatorio.").max(60),
    fecha_venta: z.string().min(1, "La fecha de venta es obligatoria."),
    empresa_facturadora_id: z.string().min(1, "Selecciona la empresa facturadora."),
    anunciante_id: z.string().min(1, "Selecciona un anunciante."),
    agencia_id: z.string().optional(),
    contrato_id: z.string().optional(),
    marca_id: z.string().optional(),
    producto: z.string().trim().max(200).optional(),
    categoria_id: z.string().optional(),
    direccion_facturacion: z.string().trim().max(300).optional(),
    facturacion_directa_cliente: z.boolean(),
    afiliado_factura_directo_al_cliente: z.boolean(),
    fecha_inicio_campania: z.string().min(1, "La fecha de inicio es obligatoria."),
    fecha_fin_campania: z.string().min(1, "La fecha de fin es obligatoria."),
    duracion_spot: z.string().min(1),
    total_spots: z
      .string()
      .trim()
      .min(1, "El total de spots es obligatorio.")
      .refine((v) => Number.isInteger(Number(v)) && Number(v) >= 1, "Debe ser un entero ≥ 1."),
    precio_unitario: z
      .string()
      .trim()
      .min(1, "El precio unitario es obligatorio.")
      .refine((v) => Number.isFinite(Number(v)) && Number(v) > 0, "Debe ser un número > 0."),
    vendedor_principal_id: z.string().min(1, "Selecciona el vendedor principal."),
    vendedor_secundario_id: z.string().optional(),
    porcentaje_comision_vendedor_principal_snap: numeroOpcionalPct(),
    porcentaje_comision_vendedor_secundario_snap: numeroOpcionalPct(),
    porcentaje_comision_agencia_snap: numeroOpcionalPct(),
    observaciones_predefinidas: z.string().optional(),
    observaciones_libres: z.string().trim().max(1000).optional(),
    odc_pdf_ref: z.string().optional(),
    motivo_cambio_comision: z.string().trim().max(500).optional(),
    })
    .refine((d) => isEdit || d.fecha_inicio_campania >= new Date().toISOString().slice(0, 10), {
      path: ["fecha_inicio_campania"],
      message: "La fecha de inicio no puede ser una fecha pasada.",
    })
    .refine((d) => d.fecha_fin_campania >= d.fecha_inicio_campania, {
      path: ["fecha_fin_campania"],
      message: "La fecha de fin debe ser mayor o igual que la de inicio.",
    });
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

const CAMPOS_SNAP = [
  "porcentaje_comision_vendedor_principal_snap",
  "porcentaje_comision_vendedor_secundario_snap",
  "porcentaje_comision_agencia_snap",
] as const;

interface OrdenClienteFormProps {
  title: string;
  isEdit?: boolean;
  estatusActual?: EstadoOC;
  defaultValues?: Partial<OrdenClienteInput> & { revision_checklist?: Record<string, boolean> };
  submitting?: boolean;
  submitError?: string | null;
  onGuardar: (input: OrdenClienteInput, opts: { darVobo: boolean; motivoComision?: string }) => void;
  onCancelar: () => void;
}

const vacio = (v: string | number | null | undefined) => (v == null ? "" : String(v));

export function OrdenClienteForm({
  title,
  isEdit = false,
  estatusActual,
  defaultValues,
  submitting,
  submitError,
  onGuardar,
  onCancelar,
}: OrdenClienteFormProps) {
  const [checklist, setChecklist] = useState<Record<string, boolean>>(defaultValues?.revision_checklist ?? {});

  const congelado = isEdit && estatusActual ? FROZEN_STATES.includes(estatusActual) : false;
  // La autorización real la valida el backend (solo Admin/Dirección, canal dedicado de
  // comisiones) — aquí solo se decide si el campo se muestra habilitado o no; siempre
  // habilitado, incluso con la OC congelada, ya no depende de un selector de persona de demo.
  const canEditComisiones = true;
  const puedeMostrarChecklist = !isEdit || estatusActual === "orden_cliente_sin_vobo";

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(isEdit)),
    defaultValues: {
      numero_orden_cliente: defaultValues?.numero_orden_cliente ?? "",
      fecha_venta: defaultValues?.fecha_venta ?? new Date().toISOString().slice(0, 10),
      empresa_facturadora_id: defaultValues?.empresa_facturadora_id ?? "",
      anunciante_id: defaultValues?.anunciante_id ?? "",
      agencia_id: defaultValues?.agencia_id ?? "",
      contrato_id: defaultValues?.contrato_id ?? "",
      marca_id: defaultValues?.marca_id ?? "",
      producto: defaultValues?.producto ?? "",
      categoria_id: defaultValues?.categoria_id ?? "",
      direccion_facturacion: defaultValues?.direccion_facturacion ?? "",
      facturacion_directa_cliente: defaultValues?.facturacion_directa_cliente ?? false,
      afiliado_factura_directo_al_cliente: defaultValues?.afiliado_factura_directo_al_cliente ?? false,
      fecha_inicio_campania: defaultValues?.fecha_inicio_campania ?? "",
      fecha_fin_campania: defaultValues?.fecha_fin_campania ?? "",
      duracion_spot: defaultValues?.duracion_spot ?? "30s",
      total_spots: vacio(defaultValues?.total_spots),
      precio_unitario: vacio(defaultValues?.precio_unitario),
      vendedor_principal_id: defaultValues?.vendedor_principal_id ?? "",
      vendedor_secundario_id: defaultValues?.vendedor_secundario_id ?? "",
      porcentaje_comision_vendedor_principal_snap: vacio(defaultValues?.porcentaje_comision_vendedor_principal_snap),
      porcentaje_comision_vendedor_secundario_snap: vacio(defaultValues?.porcentaje_comision_vendedor_secundario_snap),
      porcentaje_comision_agencia_snap: vacio(defaultValues?.porcentaje_comision_agencia_snap),
      observaciones_predefinidas: defaultValues?.observaciones_predefinidas ?? "",
      observaciones_libres: defaultValues?.observaciones_libres ?? "",
      odc_pdf_ref: defaultValues?.odc_pdf_ref ?? "",
      motivo_cambio_comision: "",
    },
  });

  const anuncianteId = watch("anunciante_id");
  const contratos = anuncianteId ? contratosVigentesDeAnunciante(anuncianteId) : [];
  const marcas = anuncianteId ? marcasDeAnunciante(anuncianteId) : [];

  // Si cambia el anunciante y el contrato/marca ya no le pertenecen, se limpian (evita
  // guardar una referencia cruzada inconsistente).
  useEffect(() => {
    const contratoId = watch("contrato_id");
    if (contratoId && !contratos.some((c) => c.id === contratoId)) setValue("contrato_id", "");
    const marcaId = watch("marca_id");
    if (marcaId && !marcas.some((m) => m.id === marcaId)) setValue("marca_id", "");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo debe correr cuando cambia el anunciante
  }, [anuncianteId]);

  const onAnuncianteChange = (id: string) => {
    setValue("anunciante_id", id);
    const anunciante = anunciantes.find((a) => a.id === id);
    if (!anunciante) return;
    if (anunciante.agencia_id && !watch("agencia_id")) setValue("agencia_id", anunciante.agencia_id);
    if (!watch("direccion_facturacion")) {
      setValue("direccion_facturacion", `${anunciante.nombre_fiscal} · RFC ${anunciante.rfc_anunciante}`);
    }
  };

  const onVendedorChange = (campo: "vendedor_principal_id" | "vendedor_secundario_id", id: string) => {
    setValue(campo, id);
    const pctCampo = campo === "vendedor_principal_id" ? "porcentaje_comision_vendedor_principal_snap" : "porcentaje_comision_vendedor_secundario_snap";
    if (!watch(pctCampo)) {
      const vendedor = findVendedor(id);
      if (vendedor) setValue(pctCampo, String(vendedor.porcentaje_comision_default));
    }
  };

  const onAgenciaChange = (id: string) => {
    setValue("agencia_id", id);
    if (!watch("porcentaje_comision_agencia_snap")) {
      const agencia = findAgencia(id);
      if (agencia) setValue("porcentaje_comision_agencia_snap", String(agencia.porcentaje_comision_agencia_default));
    }
  };

  // ── cálculos en vivo ────────────────────────────────────────────────────────
  const fechaInicio = watch("fecha_inicio_campania");
  const fechaFin = watch("fecha_fin_campania");
  const totalSpots = Number(watch("total_spots")) || 0;
  const precioUnitario = Number(watch("precio_unitario")) || 0;
  const subtotal = totalSpots * precioUnitario;
  const iva = subtotal * IVA_RATE;
  const total = subtotal + iva;
  const dias =
    fechaInicio && fechaFin
      ? Math.floor((new Date(fechaFin).getTime() - new Date(fechaInicio).getTime()) / 86_400_000) + 1
      : null;

  const vpId = watch("vendedor_principal_id");
  const vsId = watch("vendedor_secundario_id");
  const agId = watch("agencia_id");
  const pctVp = watch("porcentaje_comision_vendedor_principal_snap");
  const pctVs = watch("porcentaje_comision_vendedor_secundario_snap");
  const pctAg = watch("porcentaje_comision_agencia_snap");

  const estimaciones = [
    vpId && pctVp ? { label: "Vendedor principal", pct: Number(pctVp), monto: (total * Number(pctVp)) / 100 } : null,
    vsId && pctVs ? { label: "Vendedor secundario", pct: Number(pctVs), monto: (total * Number(pctVs)) / 100 } : null,
    agId && pctAg ? { label: "Agencia", pct: Number(pctAg), monto: (total * Number(pctAg)) / 100 } : null,
  ].filter(Boolean) as { label: string; pct: number; monto: number }[];

  // ── override badges (vs. default del catálogo del vendedor/agencia elegido) ──
  const badgeOverride = (pct: string | undefined, defaultCatalogo?: number) => {
    if (defaultCatalogo == null || !pct) return null;
    const overriden = esComisionOverride(Number(pct), defaultCatalogo);
    return (
      <span style={{ fontSize: 9, fontWeight: 600, color: overriden ? "var(--amber-text)" : "var(--text3)" }}>
        {overriden ? `sobrescrito (cat: ${defaultCatalogo}%)` : "del catálogo"}
      </span>
    );
  };

  // ── adjunto simulado (solo el nombre del archivo, no se lee ni se sube nada) ──
  const odcPdfRef = watch("odc_pdf_ref");

  // handleSubmit necesita un callback (data)=>void; envolvemos para exponer 2 acciones
  // (Guardar / Dar Vo.Bo.) que comparten la misma validación.
  const construir = (data: FormValues) => {
    const input: OrdenClienteInput = {
      numero_orden_cliente: data.numero_orden_cliente.trim(),
      fecha_venta: data.fecha_venta,
      empresa_facturadora_id: data.empresa_facturadora_id,
      anunciante_id: data.anunciante_id,
      agencia_id: data.agencia_id || null,
      contrato_id: data.contrato_id || null,
      marca_id: data.marca_id || null,
      producto: data.producto?.trim() ?? "",
      categoria_id: data.categoria_id || null,
      direccion_facturacion: data.direccion_facturacion?.trim() ?? "",
      facturacion_directa_cliente: data.facturacion_directa_cliente,
      afiliado_factura_directo_al_cliente: data.afiliado_factura_directo_al_cliente,
      fecha_inicio_campania: data.fecha_inicio_campania,
      fecha_fin_campania: data.fecha_fin_campania,
      duracion_spot: data.duracion_spot,
      total_spots: Number(data.total_spots),
      precio_unitario: Number(data.precio_unitario),
      vendedor_principal_id: data.vendedor_principal_id,
      vendedor_secundario_id: data.vendedor_secundario_id || null,
      porcentaje_comision_vendedor_principal_snap: canEditComisiones
        ? data.porcentaje_comision_vendedor_principal_snap
          ? Number(data.porcentaje_comision_vendedor_principal_snap)
          : null
        : (defaultValues?.porcentaje_comision_vendedor_principal_snap ?? null),
      porcentaje_comision_vendedor_secundario_snap: canEditComisiones
        ? data.porcentaje_comision_vendedor_secundario_snap
          ? Number(data.porcentaje_comision_vendedor_secundario_snap)
          : null
        : (defaultValues?.porcentaje_comision_vendedor_secundario_snap ?? null),
      porcentaje_comision_agencia_snap: canEditComisiones
        ? data.porcentaje_comision_agencia_snap
          ? Number(data.porcentaje_comision_agencia_snap)
          : null
        : (defaultValues?.porcentaje_comision_agencia_snap ?? null),
      observaciones_predefinidas: data.observaciones_predefinidas ?? "",
      observaciones_libres: data.observaciones_libres?.trim() ?? "",
      odc_pdf_ref: data.odc_pdf_ref || null,
      revision_checklist: checklist,
    };
    const cambioComision = CAMPOS_SNAP.some((campo) => input[campo] !== (defaultValues?.[campo] ?? null));
    return { input, motivoComision: cambioComision ? data.motivo_cambio_comision?.trim() || undefined : undefined, cambioComision };
  };

  /** Al editar, si de verdad cambió algún % de comisión, el motivo es obligatorio — no lo
   * exige el schema de Zod (que no conoce `defaultValues` al definirse), así que se valida
   * aquí y se marca el error manualmente en el campo compartido de "Motivo del cambio". */
  const construirYValidar = (data: FormValues) => {
    const { input, motivoComision, cambioComision } = construir(data);
    if (isEdit && cambioComision && !motivoComision) {
      setError("motivo_cambio_comision", { type: "manual", message: "El motivo es obligatorio al cambiar un % de comisión." });
      return null;
    }
    return { input, motivoComision };
  };

  const guardar = handleSubmit((data) => {
    const resultado = construirYValidar(data);
    if (!resultado) return;
    onGuardar(resultado.input, { darVobo: false, motivoComision: resultado.motivoComision });
  });

  const darVobo = handleSubmit((data) => {
    const resultado = construirYValidar(data);
    if (!resultado) return;
    onGuardar(resultado.input, { darVobo: true, motivoComision: resultado.motivoComision });
  });

  const checklistCompleto = isChecklistComplete(checklist);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="cat-header">
        <div className="cat-title">{title}</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, alignContent: "start" }}>
        {/* ── Columna de captura ── */}
        <div>
          <div className="sec">Identificación</div>
          <div className="r2">
            <div>
              <div className="fl fl-required">No. de orden del cliente</div>
              <input
                className="fi"
                style={{ fontFamily: "var(--mono)" }}
                placeholder="PO-CLIENTE-001"
                disabled={congelado}
                {...register("numero_orden_cliente")}
              />
              <div className="fe">{errors.numero_orden_cliente?.message}</div>
            </div>
            <div>
              <div className="fl fl-required">Fecha de venta</div>
              <input className="fi" type="date" disabled={congelado} {...register("fecha_venta")} />
              <div className="fe">{errors.fecha_venta?.message}</div>
            </div>
          </div>
          <div className="fl fl-required">Empresa facturadora</div>
          <select className="fsel" disabled={congelado} {...register("empresa_facturadora_id")}>
            <option value="">Selecciona…</option>
            {empresasFacturadoras.map((e) => (
              <option key={e.id} value={e.id}>
                {e.nombre_empresa}
              </option>
            ))}
          </select>
          <div className="fe">{errors.empresa_facturadora_id?.message}</div>

          <div className="sec">Cliente</div>
          <div className="fl fl-required">Anunciante</div>
          <select className="fsel" disabled={congelado} value={anuncianteId} onChange={(e) => onAnuncianteChange(e.target.value)}>
            <option value="">Selecciona…</option>
            {anunciantes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre_comercial}
              </option>
            ))}
          </select>
          <div className="fe">{errors.anunciante_id?.message}</div>

          <div className="r2">
            <div>
              <div className="fl">
                Agencia <span style={{ color: "var(--text3)", fontWeight: 400 }}>(sugerida del anunciante)</span>
              </div>
              <select className="fsel" disabled={congelado} value={watch("agencia_id")} onChange={(e) => onAgenciaChange(e.target.value)}>
                <option value="">Sin agencia (venta directa)</option>
                {agencias.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre_agencia}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="fl">Categoría</div>
              <select className="fsel" disabled={congelado} {...register("categoria_id")}>
                <option value="">Selecciona…</option>
                {categorias.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre_categoria}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="r2">
            <div>
              <div className="fl">
                Contrato <span style={{ color: "var(--text3)", fontWeight: 400 }}>(vigentes del anunciante)</span>
              </div>
              {anuncianteId && contratos.length === 0 ? (
                <div className="fv muted" style={{ fontSize: 12 }}>
                  Este anunciante no tiene contratos vigentes.
                </div>
              ) : (
                <select className="fsel" disabled={!anuncianteId || congelado} {...register("contrato_id")}>
                  <option value="">Sin contrato</option>
                  {contratos.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre_contrato}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div>
              <div className="fl">
                Marca <span style={{ color: "var(--text3)", fontWeight: 400 }}>(del anunciante)</span>
              </div>
              {anuncianteId && marcas.length === 0 ? (
                <div className="fv muted" style={{ fontSize: 12 }}>
                  Este anunciante no tiene marcas registradas.
                </div>
              ) : (
                <select className="fsel" disabled={!anuncianteId || congelado} {...register("marca_id")}>
                  <option value="">Sin marca</option>
                  {marcas.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nombre_marca}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div className="fl">Producto</div>
          <input className="fi" placeholder="Descripción del producto anunciado" disabled={congelado} {...register("producto")} />

          <div className="sec">Campaña y montos</div>
          <div className="r2">
            <div>
              <div className="fl fl-required">Inicio de campaña</div>
              <input
                className="fi"
                type="date"
                disabled={congelado}
                min={isEdit ? undefined : new Date().toISOString().slice(0, 10)}
                {...register("fecha_inicio_campania")}
              />
              <div className="fe">{errors.fecha_inicio_campania?.message}</div>
            </div>
            <div>
              <div className="fl fl-required">Fin de campaña</div>
              <input className="fi" type="date" disabled={congelado} {...register("fecha_fin_campania")} />
              <div className="fe">{errors.fecha_fin_campania?.message}</div>
            </div>
          </div>
          <div className="r2">
            <div>
              <div className="fl">Duración del spot</div>
              <select className="fsel" disabled={congelado} {...register("duracion_spot")}>
                {OPCIONES_DURACION.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="fl fl-required">Total de spots</div>
              <input
                className="fi"
                style={{ fontFamily: "var(--mono)" }}
                inputMode="numeric"
                disabled={congelado}
                {...register("total_spots")}
              />
              <div className="fe">{errors.total_spots?.message}</div>
            </div>
          </div>
          <div className="fl fl-required">Precio unitario (MXN, por spot)</div>
          <Controller
            control={control}
            name="precio_unitario"
            render={({ field }) => (
              <MoneyInput
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                disabled={congelado}
              />
            )}
          />
          <div className="fe">{errors.precio_unitario?.message}</div>

          <div className="sec">Facturación</div>
          <div className="fl">Dirección de facturación</div>
          <input className="fi" disabled={congelado} {...register("direccion_facturacion")} />
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 8, cursor: "pointer" }}>
            <input type="checkbox" disabled={congelado} {...register("facturacion_directa_cliente")} /> Facturación directa al cliente
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 8, cursor: "pointer" }}>
            <input type="checkbox" disabled={congelado} {...register("afiliado_factura_directo_al_cliente")} /> Afiliado factura directo
            al cliente
          </label>

          <div className="fl">Adjuntar ODC (PDF) — simulado</div>
          <input
            type="file"
            accept="application/pdf"
            disabled={congelado}
            onChange={(e) => setValue("odc_pdf_ref", e.target.files?.[0]?.name ?? "")}
            style={{ fontSize: 12, marginBottom: 4 }}
          />
          {odcPdfRef && (
            <div className="fv mono" style={{ fontSize: 12 }}>
              📎 {odcPdfRef}
            </div>
          )}

          <div className="sec">Equipo comercial y comisiones</div>
          <div className="r2">
            <div>
              <div className="fl fl-required">Vendedor principal</div>
              <select
                className="fsel"
                disabled={congelado}
                value={vpId}
                onChange={(e) => onVendedorChange("vendedor_principal_id", e.target.value)}
              >
                <option value="">Selecciona…</option>
                {vendedores.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.nombre_vendedor}
                  </option>
                ))}
              </select>
              <div className="fe">{errors.vendedor_principal_id?.message}</div>
            </div>
            <div>
              <div className="fl">Vendedor secundario</div>
              <select
                className="fsel"
                disabled={congelado}
                value={vsId}
                onChange={(e) => onVendedorChange("vendedor_secundario_id", e.target.value)}
              >
                <option value="">Sin vendedor secundario</option>
                {vendedores.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.nombre_vendedor}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {congelado && (
            <div
              style={{
                background: "var(--amber-bg)",
                color: "var(--amber-text)",
                borderRadius: "var(--r)",
                padding: "8px 11px",
                fontSize: 12,
                marginBottom: 10,
              }}
            >
              🔒 Orden congelada ({estatusActual}): el formulario completo es de solo lectura.{" "}
              {canEditComisiones
                ? "Tienes admin_parametros: puedes sobrescribir los % de comisión (queda auditado)."
                : "Necesitas el rol admin_parametros para sobrescribir los % de comisión."}
            </div>
          )}

          <SensitiveField
            label="% comisión vendedor principal"
            register={register("porcentaje_comision_vendedor_principal_snap", { disabled: !canEditComisiones })}
            error={errors.porcentaje_comision_vendedor_principal_snap?.message}
            badge={badgeOverride(pctVp, findVendedor(vpId)?.porcentaje_comision_default)}
          />
          <SensitiveField
            label="% comisión vendedor secundario"
            register={register("porcentaje_comision_vendedor_secundario_snap", { disabled: !canEditComisiones })}
            error={errors.porcentaje_comision_vendedor_secundario_snap?.message}
            badge={vsId ? badgeOverride(pctVs, findVendedor(vsId)?.porcentaje_comision_default) : null}
          />
          <SensitiveField
            label="% comisión agencia"
            register={register("porcentaje_comision_agencia_snap", { disabled: !canEditComisiones })}
            error={errors.porcentaje_comision_agencia_snap?.message}
            badge={agId ? badgeOverride(pctAg, findAgencia(agId)?.porcentaje_comision_agencia_default) : null}
          />
          {/* Compartido entre los 3 % de arriba (antes solo vivía junto al de agencia, lo
              que dejaba sin dónde capturar el motivo un cambio de comisión de vendedor). */}
          {isEdit && canEditComisiones && (
            <>
              <div className="fl fl-required">
                Motivo del cambio <span style={{ color: "var(--text3)", fontWeight: 400 }}>(si modificas cualquiera de los 3 % anteriores)</span>
              </div>
              <input className="fi" placeholder="Requerido al modificar el valor…" {...register("motivo_cambio_comision")} />
              <div className="fe">{errors.motivo_cambio_comision?.message}</div>
            </>
          )}

          <div className="sec">Observaciones</div>
          <div className="fl">Observación predefinida</div>
          <select className="fsel" disabled={congelado} {...register("observaciones_predefinidas")}>
            <option value="">Ninguna</option>
            {OBS_PREDEFINIDAS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <div className="fl">Observaciones libres</div>
          <textarea className="ftxt" rows={2} disabled={congelado} {...register("observaciones_libres")} />
        </div>

        {/* ── Columna de resumen ── */}
        <div>
          <div className="info-panel">
            <div className="info-panel-title">Cálculos en vivo</div>
            <div className="fl">Días de campaña</div>
            <div className="fv mono">{dias != null && dias > 0 ? `${dias} días` : "—"}</div>
            <div className="fl">Subtotal</div>
            <div className="fv mono">{fmtMonto(subtotal)}</div>
            <div className="fl">
              IVA ({(IVA_RATE * 100).toFixed(0)}%)
            </div>
            <div className="fv mono">{fmtMonto(iva)}</div>
            <div className="fl">Total</div>
            <div className="fv mono" style={{ fontSize: 18, fontWeight: 600, color: "var(--purple-text)" }}>
              {fmtMonto(total)}
            </div>
            {estimaciones.length > 0 && (
              <>
                <div className="fl" style={{ marginTop: 8 }}>
                  Comisiones estimadas <span style={{ fontWeight: 400 }}>(base: total c/IVA)</span>
                </div>
                {estimaciones.map((e) => (
                  <div key={e.label} className="fv" style={{ fontSize: 12, marginBottom: 4 }}>
                    {e.label} ({e.pct}%): <span className="mono">{fmtMonto(e.monto)}</span>
                  </div>
                ))}
              </>
            )}
          </div>

          {puedeMostrarChecklist && <ChecklistVoBo checklist={checklist} onChange={setChecklist} />}
        </div>
      </div>

      <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {submitError && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {submitError}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={onCancelar} disabled={submitting}>
            Cancelar
          </button>
          <button type="button" className="btn btn-sm btn-teal" onClick={guardar} disabled={submitting}>
            {isEdit ? "Guardar cambios" : "Guardar como recibida"}
          </button>
          {puedeMostrarChecklist && (
            <button
              type="button"
              className="btn btn-sm btn-teal"
              onClick={darVobo}
              disabled={submitting || !checklistCompleto}
              title={checklistCompleto ? undefined : "Completa el checklist para dar Vo.Bo."}
            >
              Dar Vo.Bo. {isEdit ? "" : "y capturar"} →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
