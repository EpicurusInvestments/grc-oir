/** Formulario de alta/edición de OrdenCliente — pantalla completa, dos columnas (captura +
 * panel de resumen), como pide el patrón "form full-screen" de la propuesta.
 *
 * Selectores encadenados de verdad (E.2): Contrato y Marca se filtran por el anunciante
 * elegido (son relaciones anidadas de Anunciante en F0), con estado vacío explícito si un
 * anunciante no tuviera ninguno. Agencia y dirección de facturación se SUGIEREN desde el
 * anunciante (se prellenan solo si el campo está vacío) sin forzar la relación, igual que
 * en el prototipo aprobado.
 *
 * ADR-167 (petición del usuario): "Producto" y "Duración" (sección "Campaña y montos") se
 * llenan desde el catálogo `DuracionSpotCatalogo` ("Producto Duración", F0-06) — mismo
 * patrón Producto→Duración que ya usa Tarifa (ADR-166): el select de Producto lista los
 * valores distintos y activos del catálogo; al elegir uno, el select de Duración lista las
 * `descripcion_duracion` de ESE producto, excluyendo siempre el literal "sin resultado"
 * (nunca se muestra como opción). A DIFERENCIA de Tarifa, Duración NO es obligatoria: si
 * el producto elegido (p.ej. Mención) no tiene ninguna duración real en el catálogo, el
 * combo simplemente queda vacío/deshabilitado ("Selecciona…", pero internamente `null`) y
 * la captura continúa sin bloquear nada.
 *
 * ADR-168 (petición del usuario, probado en vivo): "Producto" SÍ es obligatorio — Total
 * de spots/Spots bonificables/Precio unitario quedan deshabilitados hasta elegir uno, y
 * no se puede guardar la orden sin él.
 *
 * ADR-180 (petición del usuario): editar "Inicio de campaña"/"Fin de campaña" exige un
 * "Motivo del cambio" — select con las Descripciones del catálogo Constantes del
 * Sistema, grupo `MotivoCambio`, clave `CambioFecha`/`CambioFecha_N` (ADR-178); si el
 * catálogo no tiene ninguna opción activa, cae de regreso a texto libre (mismo patrón
 * que `TarifaForm.tsx`, ADR-179). El campo se deshabilita mientras ninguna de las dos
 * fechas difiera de su valor original — se habilita solo al modificar alguna.
 *
 * ADR-181 (petición del usuario): el radio "Afiliado factura directo al cliente" se
 * renombra a "Facturación a la Agencia" (su columna real,
 * `afiliado_factura_directo_al_cliente`, NO cambia — sigue siendo la misma del modelo,
 * solo cambia la etiqueta visible). Al elegirlo, "Dirección de facturación" se
 * autocompleta con el domicilio ESTRUCTURADO de la Agencia (ADR-175, vía
 * `formatDomicilio`); si la Agencia no tiene domicilio capturado (o no hay ninguna
 * ligada), el campo se VACÍA para que el usuario la capture a mano. Al elegir
 * "Facturación directa al cliente" vuelve a la del Anunciante (mismo texto que ya usaba
 * `onAnuncianteChange`) si hay uno elegido.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { useConstantes, useCrearMotivoCambio } from "@/modules/catalogos/constantesSistema/hooks";
import { useDuracionesSpot } from "@/modules/catalogos/duracionSpot/hooks";
import { SIN_RESULTADO } from "@/modules/catalogos/duracionSpot/types";
import { formatDomicilio } from "@/shared/lib/formatDomicilio";
import type { HistorialCambio } from "@/shared/types";
import { FieldTag, MoneyInput, SavingOverlay, SearchableSelect, SensitiveField } from "@/shared/ui";

import { AdjuntoOrdenInput } from "../../components/AdjuntoOrdenInput";
import { FROZEN_STATES, IVA_RATE, OBS_PREDEFINIDAS } from "../../constants";
import { fmtMonto } from "../../format";
import {
  agencias,
  anunciantes,
  categorias,
  contratosVigentesDeAnunciante,
  empresasFacturadoras,
  esActivo,
  findAgencia,
  findVendedor,
  marcasDeAnunciante,
  vendedores,
} from "../../state/catalogosCache";
import { esComisionOverride } from "../../state/selectors";
import type { EstadoOC, OrdenClienteInput } from "../../types";

const esSinResultado = (v: string) => v.trim().toLowerCase() === SIN_RESULTADO;

// ADR-238 (bug reportado por el usuario): `new Date().toISOString()` convierte a UTC antes
// de cortar la fecha — en México (UTC-6), desde las 18:00 hora local el día en UTC ya es
// el siguiente, así que "hoy" se calculaba mal y el calendario bloqueaba el día real. Esta
// función arma la fecha ISO a partir de los componentes LOCALES (año/mes/día), nunca de UTC.
const hoyLocal = () => {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
};

// ADR-180: clave base (sin sufijo) del grupo MotivoCambio reservada para estas fechas.
const CLAVE_BASE_MOTIVO_FECHA = "cambiofecha";
// ADR-244: ídem, para "Motivo del cambio" de los 3 % de comisión (antes texto libre).
const CLAVE_BASE_MOTIVO_COMISION = "cambiocomision";

// ADR-181: misma fórmula en 2 lugares (al elegir Anunciante, y al volver a "Facturación
// directa al cliente") — un helper evita que diverjan.
const direccionDeAnunciante = (a: { nombre_fiscal: string; rfc_anunciante: string }) =>
  `${a.nombre_fiscal} · RFC ${a.rfc_anunciante}`;

const numeroOpcionalPct = () =>
  z
    .string()
    .trim()
    .optional()
    .refine((v) => v == null || v === "" || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 100), "El % debe estar entre 0 y 100.");

/** `fechaInicioOriginal`/`fechaVentaOriginal` son los valores YA GUARDADOS (vacíos al
 * crear). La regla de "no puede ser fecha pasada" solo se aplica si el valor CAMBIÓ: una
 * orden ya en curso legítimamente tiene esas fechas en el pasado, y dejarlas intactas
 * (editar otro campo) no debe bloquearse por el simple paso del calendario — pero si
 * alguien las MODIFICA, el nuevo valor sí debe ser hoy o futuro. */
function buildSchema(fechaInicioOriginal: string, fechaVentaOriginal: string) {
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
    // ADR-168 (petición del usuario): Producto SÍ es obligatorio — habilita el resto de
    // "Campaña y montos" y es requisito para poder guardar. Duración sigue opcional
    // (ADR-167): a diferencia de Tarifa, aquí no se obliga a capturar una duración real
    // (p.ej. Mención puede quedarse sin ninguna, "sin resultado" nunca es seleccionable).
    producto_tarifa: z.string().trim().min(1, "Selecciona un producto.").max(60),
    duracion_spot: z.string().optional(),
    total_spots: z
      .string()
      .trim()
      .min(1, "El total de spots es obligatorio.")
      .refine((v) => Number.isInteger(Number(v)) && Number(v) >= 1, "Debe ser un entero ≥ 1."),
    // ADR-067: spots que se transmiten pero no se cobran al cliente. Opcional (default 0);
    // se valida contra total_spots más abajo, en el .refine de nivel de objeto, porque aquí
    // todavía no se conoce el otro valor.
    cantidad_spots_bonificables: z
      .string()
      .trim()
      .optional()
      .refine((v) => v == null || v === "" || (Number.isInteger(Number(v)) && Number(v) >= 0), "Debe ser un entero ≥ 0."),
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
    motivo_cambio_fecha: z.string().trim().max(500).optional(),
    })
    .refine(
      (d) =>
        d.fecha_venta === fechaVentaOriginal ||
        d.fecha_venta >= hoyLocal(),
      {
        path: ["fecha_venta"],
        message: "La fecha de venta no puede ser una fecha pasada.",
      },
    )
    .refine(
      (d) =>
        d.fecha_inicio_campania === fechaInicioOriginal ||
        d.fecha_inicio_campania >= hoyLocal(),
      {
        path: ["fecha_inicio_campania"],
        message: "La fecha de inicio no puede ser una fecha pasada.",
      },
    )
    .refine((d) => d.fecha_fin_campania >= d.fecha_inicio_campania, {
      path: ["fecha_fin_campania"],
      message: "La fecha de fin debe ser mayor o igual que la de inicio.",
    })
    .refine((d) => Number(d.cantidad_spots_bonificables || 0) <= Number(d.total_spots || 0), {
      path: ["cantidad_spots_bonificables"],
      message: "No puede exceder el total de spots.",
    })
    // Bug corregido (petición del usuario, con captura): no se puede facturar a la
    // agencia sin haber seleccionado una. El radio ya no se puede elegir sin agencia
    // (ver JSX), pero este refine es el respaldo — p.ej. una orden ya guardada antes de
    // este fix, con ese estado inconsistente, no podrá reguardarse sin corregirlo.
    .refine((d) => !d.afiliado_factura_directo_al_cliente || !!d.agencia_id, {
      path: ["agencia_id"],
      message: "Selecciona una agencia para poder facturar a la agencia.",
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
  defaultValues?: Partial<OrdenClienteInput>;
  /** Nº de OrdenEstacion YA creadas para esta OC (solo aplica en edición). Aviso, no
   *  candado: cambiar la tarifa aquí no toca las OE existentes (cada una guarda su
   *  propio `precio_spot`), pero conviene que quien edita sepa que ya hay órdenes
   *  internas con la tarifa vieja antes de tocarla. */
  oeCount?: number;
  /** Bug corregido (petición del usuario, con captura — ADR-250): historial de
   *  `LogCambioParametro` de ESTA OC (ya filtrado por `entidad_id`, viene de
   *  `state.historialComisiones`) — se usa solo para precargar el combo "Motivo del
   *  cambio" con el motivo MÁS RECIENTE de los 3 % de comisión al abrir en edición (antes
   *  arrancaba siempre vacío, aunque el motivo ya existiera en la bitácora). */
  historialComisiones?: HistorialCambio[];
  submitting?: boolean;
  submitError?: string | null;
  onGuardar: (input: OrdenClienteInput, opts: { motivoComision?: string }) => void;
  onCancelar: () => void;
}

const vacio = (v: string | number | null | undefined) => (v == null ? "" : String(v));

export function OrdenClienteForm({
  title,
  isEdit = false,
  estatusActual,
  defaultValues,
  oeCount = 0,
  historialComisiones = [],
  submitting,
  submitError,
  onGuardar,
  onCancelar,
}: OrdenClienteFormProps) {
  const congelado = isEdit && estatusActual ? FROZEN_STATES.includes(estatusActual) : false;
  // Con la OC congelada (orden_cerrada+), el formulario completo es de solo lectura sin
  // excepción — el canal dedicado de comisiones (`PATCH /comisiones`) sigue existiendo en
  // el backend, pero este formulario ya no ofrece forma de llegar a él.
  const canEditComisiones = !congelado;

  // Bug corregido (petición del usuario, con captura — ADR-250): el motivo más reciente
  // de CUALQUIERA de los 3 % de comisión (el mismo criterio "compartido" que ya usa el
  // resto del flujo) — precarga el combo en vez de arrancar siempre vacío.
  const ultimoMotivoComision = useMemo(() => {
    if (!isEdit) return "";
    const ultimo = [...historialComisiones]
      .filter((h) => (CAMPOS_SNAP as readonly string[]).includes(h.campo) && h.motivo_cambio)
      .sort((a, b) => b.fecha_cambio.localeCompare(a.fecha_cambio))[0];
    return ultimo?.motivo_cambio ?? "";
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(defaultValues?.fecha_inicio_campania ?? "", defaultValues?.fecha_venta ?? "")),
    defaultValues: {
      numero_orden_cliente: defaultValues?.numero_orden_cliente ?? "",
      fecha_venta: defaultValues?.fecha_venta ?? hoyLocal(),
      empresa_facturadora_id: defaultValues?.empresa_facturadora_id ?? "",
      anunciante_id: defaultValues?.anunciante_id ?? "",
      agencia_id: defaultValues?.agencia_id ?? "",
      contrato_id: defaultValues?.contrato_id ?? "",
      marca_id: defaultValues?.marca_id ?? "",
      producto: defaultValues?.producto ?? "",
      categoria_id: defaultValues?.categoria_id ?? "",
      direccion_facturacion: defaultValues?.direccion_facturacion ?? "",
      // ADR-141 (petición del usuario): default del radio group en el ALTA (sin
      // defaultValues) es "Facturación directa al cliente" — editar una orden existente
      // conserva su valor real tal cual, incluido un `false` explícito.
      facturacion_directa_cliente: defaultValues?.facturacion_directa_cliente ?? true,
      afiliado_factura_directo_al_cliente: defaultValues?.afiliado_factura_directo_al_cliente ?? false,
      fecha_inicio_campania: defaultValues?.fecha_inicio_campania ?? "",
      fecha_fin_campania: defaultValues?.fecha_fin_campania ?? "",
      producto_tarifa: defaultValues?.producto_tarifa ?? "",
      duracion_spot: defaultValues?.duracion_spot ?? "",
      total_spots: vacio(defaultValues?.total_spots),
      cantidad_spots_bonificables: vacio(defaultValues?.cantidad_spots_bonificables ?? 0),
      precio_unitario: vacio(defaultValues?.precio_unitario),
      vendedor_principal_id: defaultValues?.vendedor_principal_id ?? "",
      vendedor_secundario_id: defaultValues?.vendedor_secundario_id ?? "",
      porcentaje_comision_vendedor_principal_snap: vacio(defaultValues?.porcentaje_comision_vendedor_principal_snap),
      porcentaje_comision_vendedor_secundario_snap: vacio(defaultValues?.porcentaje_comision_vendedor_secundario_snap),
      porcentaje_comision_agencia_snap: vacio(defaultValues?.porcentaje_comision_agencia_snap),
      observaciones_predefinidas: defaultValues?.observaciones_predefinidas ?? "",
      observaciones_libres: defaultValues?.observaciones_libres ?? "",
      odc_pdf_ref: defaultValues?.odc_pdf_ref ?? "",
      motivo_cambio_comision: ultimoMotivoComision,
      motivo_cambio_fecha: "",
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
    // Bug corregido (petición del usuario): al autocargar la agencia por default del
    // anunciante, también hay que autocargar su % de comisión — igual que hace
    // `onAgenciaChange` cuando el usuario la elige a mano.
    if (anunciante.agencia_id && !watch("agencia_id")) {
      setValue("agencia_id", anunciante.agencia_id);
      if (!watch("porcentaje_comision_agencia_snap")) {
        const agencia = findAgencia(anunciante.agencia_id);
        if (agencia) {
          setValue("porcentaje_comision_agencia_snap", String(agencia.porcentaje_comision_agencia_default));
        }
      }
    }
    if (!watch("direccion_facturacion")) {
      setValue("direccion_facturacion", direccionDeAnunciante(anunciante));
    }
  };

  const onVendedorChange = (campo: "vendedor_principal_id" | "vendedor_secundario_id", id: string) => {
    setValue(campo, id);
    const pctCampo = campo === "vendedor_principal_id" ? "porcentaje_comision_vendedor_principal_snap" : "porcentaje_comision_vendedor_secundario_snap";
    const vendedor = findVendedor(id);
    if (vendedor) {
      if (!watch(pctCampo)) setValue(pctCampo, String(vendedor.porcentaje_comision_default));
    } else {
      // ADR-142 (corrige un bug real): volver a "Sin vendedor secundario" dejaba pegado
      // el % de comisión del vendedor elegido antes por error — sin vendedor no hay
      // comisión que aplique (mismo criterio que "Sin agencia" en `onAgenciaChange`).
      setValue(pctCampo, "");
    }
  };

  const onAgenciaChange = (id: string) => {
    setValue("agencia_id", id);
    // A diferencia de vendedor (que respeta un % ya capturado a mano al cambiar de
    // vendedor), aquí SIEMPRE se sigue a la agencia recién elegida: un % que quedó de
    // la agencia anterior (autollenado o no) ya no aplica a la nueva selección. "Sin
    // agencia" limpia el campo.
    const agencia = findAgencia(id);
    setValue("porcentaje_comision_agencia_snap", agencia ? String(agencia.porcentaje_comision_agencia_default) : "");
    // Bug corregido (petición del usuario, con captura): no debe quedar "Facturación a
    // la Agencia" seleccionada sin una agencia elegida — si se quita la agencia
    // mientras esa opción está activa, se regresa a "Facturación directa al cliente"
    // (el default del alta, ADR-141). El radio además ya no se puede ELEGIR sin
    // agencia (ver `disabled` más abajo); esto cubre quitar la agencia después.
    if (!id && watch("afiliado_factura_directo_al_cliente")) {
      setValue("afiliado_factura_directo_al_cliente", false);
      setValue("facturacion_directa_cliente", true);
      const anunciante = anunciantes.find((a) => a.id === watch("anunciante_id"));
      setValue("direccion_facturacion", anunciante ? direccionDeAnunciante(anunciante) : "");
    }
  };

  // ── Producto/Duración desde el catálogo "Producto Duración" (ADR-167) ─────────
  const catalogoDuraciones = useDuracionesSpot().useList({ activo: true, size: 100 });
  const entradasDuracion = useMemo(
    () => catalogoDuraciones.data?.items ?? [],
    [catalogoDuraciones.data],
  );
  const productoTarifaActual = watch("producto_tarifa") ?? "";

  const productosDuracion = useMemo(() => {
    const vistos = new Map<string, string>();
    for (const e of entradasDuracion) vistos.set(e.producto.trim().toLowerCase(), e.producto);
    if (
      defaultValues?.producto_tarifa &&
      !vistos.has(defaultValues.producto_tarifa.trim().toLowerCase())
    ) {
      vistos.set(defaultValues.producto_tarifa.trim().toLowerCase(), defaultValues.producto_tarifa);
    }
    return [...vistos.values()].sort((a, b) => a.localeCompare(b, "es"));
  }, [entradasDuracion, defaultValues?.producto_tarifa]);

  const duracionesDelProducto = useMemo(() => {
    const delProducto = entradasDuracion.filter(
      (e) => e.producto.trim().toLowerCase() === productoTarifaActual.trim().toLowerCase(),
    );
    const vistos = new Map<string, string>();
    for (const e of delProducto) {
      if (esSinResultado(e.descripcion_duracion)) continue;
      vistos.set(e.descripcion_duracion.trim().toLowerCase(), e.descripcion_duracion);
    }
    if (
      defaultValues?.duracion_spot &&
      !esSinResultado(defaultValues.duracion_spot) &&
      productoTarifaActual.trim().toLowerCase() ===
        (defaultValues?.producto_tarifa ?? "").trim().toLowerCase() &&
      !vistos.has(defaultValues.duracion_spot.trim().toLowerCase())
    ) {
      vistos.set(defaultValues.duracion_spot.trim().toLowerCase(), defaultValues.duracion_spot);
    }
    return [...vistos.values()];
  }, [entradasDuracion, productoTarifaActual, defaultValues?.producto_tarifa, defaultValues?.duracion_spot]);

  // ── cálculos en vivo ────────────────────────────────────────────────────────
  const fechaVenta = watch("fecha_venta");
  const anioVenta = fechaVenta ? fechaVenta.slice(0, 4) : "—";
  const mesVenta = fechaVenta ? fechaVenta.slice(5, 7) : "—";
  const fechaInicio = watch("fecha_inicio_campania");
  const fechaFin = watch("fecha_fin_campania");

  // ADR-180: "Motivo del cambio" de fechas — habilitado solo si alguna de las dos
  // difiere de su valor original (mismo criterio que `algunSensibleCambio` de Tarifa).
  const fechaInicioCambiada =
    isEdit &&
    defaultValues?.fecha_inicio_campania !== undefined &&
    fechaInicio !== defaultValues.fecha_inicio_campania;
  const fechaFinCambiada =
    isEdit &&
    defaultValues?.fecha_fin_campania !== undefined &&
    fechaFin !== defaultValues.fecha_fin_campania;
  const algunaFechaCambio = fechaInicioCambiada || fechaFinCambiada;

  const motivosFechaQuery = useConstantes().useList({ grupo: "MotivoCambio", activo: true, size: 100 });
  const motivosCambioFecha = useMemo(() => {
    const items = motivosFechaQuery.data?.items ?? [];
    return items.filter((c) => {
      const clave = c.clave.trim().toLowerCase();
      return clave === CLAVE_BASE_MOTIVO_FECHA || clave.startsWith(`${CLAVE_BASE_MOTIVO_FECHA}_`);
    });
  }, [motivosFechaQuery.data]);
  // ADR-246 (petición del usuario): combo "creatable" — reemplaza el fallback a texto
  // libre de ADR-180 (ver también el de comisión, más abajo, y el de Tarifa en
  // TarifaForm.tsx/OrdenEstacionForm.tsx — los 4 comparten el mismo mecanismo).
  const crearMotivoFecha = useCrearMotivoCambio();

  const totalSpots = Number(watch("total_spots")) || 0;
  const spotsBonificables = Math.min(Number(watch("cantidad_spots_bonificables")) || 0, totalSpots);
  const precioUnitario = Number(watch("precio_unitario")) || 0;
  // ADR-067: el subtotal/IVA/total se calculan sobre lo FACTURABLE (total_spots menos los
  // bonificables), no sobre el total de spots — mismo criterio que `totalesOC` (selectors.ts).
  const spotsFacturables = totalSpots - spotsBonificables;
  const subtotalBonificables = spotsBonificables * precioUnitario;
  const subtotal = spotsFacturables * precioUnitario;
  const subtotalBruto = subtotal + subtotalBonificables;
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

  // ADR-244 (petición del usuario): "Motivo del cambio de comisión" ahora se puede
  // deshabilitar/habilitar en vivo igual que `algunaFechaCambio` — antes solo se sabía
  // si de verdad cambió algún % hasta el `construir()` del submit.
  // ADR-249 (petición del usuario): en ALTA también exige motivo — pero ahí no hay un
  // valor guardado contra qué comparar (es captura inicial, ADR-029), así que el
  // criterio es distinto: diverge del % SUGERIDO DEL CATÁLOGO (mismo cálculo que ya usa
  // el badge "sobrescrito", `esComisionOverride`) — si se deja tal cual lo sugirió el
  // catálogo, no hace falta justificar nada. En EDICIÓN se conserva el criterio de
  // siempre: diverge de `defaultValues` (lo guardado), nunca del catálogo de hoy (que
  // pudo cambiar desde entonces por razones ajenas a esta orden).
  const divergeDelCatalogo = (pct: string | undefined, defaultCatalogo: number | undefined) =>
    defaultCatalogo != null && esComisionOverride(pct ? Number(pct) : null, defaultCatalogo);
  // Bug corregido (petición del usuario, con captura): se calcula en AMBOS modos —en
  // edición también— porque el combo de motivo debe poder consultarse/usarse siempre que
  // algún % ya esté sobrescrito respecto al catálogo, no solo cuando lo tocas en esta
  // sesión (ver uso en `disabled` del combo, más abajo).
  const algunaComisionDivergeCatalogo =
    divergeDelCatalogo(pctVp, findVendedor(vpId || null)?.porcentaje_comision_default) ||
    divergeDelCatalogo(pctVs, findVendedor(vsId || null)?.porcentaje_comision_default) ||
    divergeDelCatalogo(pctAg, findAgencia(agId || null)?.porcentaje_comision_agencia_default);
  const algunaComisionCambio = isEdit
    ? CAMPOS_SNAP.some((campo) => {
        const actual = watch(campo);
        const nuevo = actual ? Number(actual) : null;
        return nuevo !== (defaultValues?.[campo] ?? null);
      })
    : algunaComisionDivergeCatalogo;

  const motivosComisionQuery = useConstantes().useList({ grupo: "MotivoCambio", activo: true, size: 100 });
  const motivosCambioComision = useMemo(() => {
    const items = motivosComisionQuery.data?.items ?? [];
    return items.filter((c) => {
      const clave = c.clave.trim().toLowerCase();
      return clave === CLAVE_BASE_MOTIVO_COMISION || clave.startsWith(`${CLAVE_BASE_MOTIVO_COMISION}_`);
    });
  }, [motivosComisionQuery.data]);
  const crearMotivoComision = useCrearMotivoCambio();

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

  // ── adjunto ODC (subida real; ver AdjuntoOrdenInput) ──
  const odcPdfRef = watch("odc_pdf_ref");

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
      producto_tarifa: data.producto_tarifa?.trim() || null,
      duracion_spot: data.duracion_spot || null,
      total_spots: Number(data.total_spots),
      cantidad_spots_bonificables: Number(data.cantidad_spots_bonificables) || 0,
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
      // ADR-180: transitorio — solo se manda si de verdad cambió alguna de las dos fechas.
      ...(isEdit && algunaFechaCambio && data.motivo_cambio_fecha?.trim()
        ? { motivo_cambio_fecha: data.motivo_cambio_fecha.trim() }
        : {}),
    };
    // ADR-249 (petición del usuario): `algunaComisionCambio` ya cubre tanto edición
    // (diverge de lo guardado) como alta (diverge del % sugerido del catálogo) — un
    // solo criterio, calculado arriba, reutilizado aquí para no duplicar la regla.
    return {
      input,
      motivoComision: algunaComisionCambio ? data.motivo_cambio_comision?.trim() || undefined : undefined,
      cambioComision: algunaComisionCambio,
    };
  };

  /** Si de verdad cambió algún % de comisión (en alta: diverge del catálogo; en
   * edición: diverge de lo guardado) o alguna fecha de campaña (solo edición), el
   * motivo correspondiente es obligatorio — ninguno lo exige el schema de Zod (que no
   * conoce `defaultValues` ni los catálogos al definirse), así que se valida aquí y se
   * marca el error manualmente en el campo compartido de cada uno. */
  const construirYValidar = (data: FormValues) => {
    const { input, motivoComision, cambioComision } = construir(data);
    if (isEdit && algunaFechaCambio && !data.motivo_cambio_fecha?.trim()) {
      setError("motivo_cambio_fecha", {
        type: "manual",
        message: "El motivo es obligatorio al cambiar la fecha de inicio o fin de campaña.",
      });
      return null;
    }
    if (cambioComision && !motivoComision) {
      setError("motivo_cambio_comision", { type: "manual", message: "El motivo es obligatorio al cambiar un % de comisión." });
      return null;
    }
    return { input, motivoComision };
  };

  const guardar = handleSubmit((data) => {
    const resultado = construirYValidar(data);
    if (!resultado) return;
    onGuardar(resultado.input, { motivoComision: resultado.motivoComision });
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="cat-header">
        <div className="cat-title">{title}</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, alignContent: "start" }}>
        {/* ── Columna de captura ── */}
        <div>
          <div className="zone-header">
            <div className="zone-bar a" />
            <div>
              <div className="zone-title">ZONA A · DATOS DE LA ODC DEL CLIENTE</div>
              <div className="zone-sub">Lo que viene en el documento que mandó el cliente o la agencia.</div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Identificación</div>
            <div className="r3">
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
                <input
                  className="fi"
                  type="date"
                  disabled={congelado}
                  min={hoyLocal()}
                  {...register("fecha_venta")}
                />
                <div className="fe">{errors.fecha_venta?.message}</div>
              </div>
              <div>
                <div className="fl fl-required">
                  Empresa facturadora <FieldTag origin="catalogo" />
                </div>
                <select className="fsel" disabled={congelado} {...register("empresa_facturadora_id")}>
                  <option value="">Selecciona…</option>
                  {empresasFacturadoras.filter(esActivo).map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.nombre_empresa}
                    </option>
                  ))}
                </select>
                <div className="fe">{errors.empresa_facturadora_id?.message}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text3)" }}>
              <span>
                Año venta <FieldTag origin="derivado" />: <span className="mono">{anioVenta}</span>
              </span>
              <span>
                Mes <FieldTag origin="derivado" />: <span className="mono">{mesVenta}</span>
              </span>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Cliente comercial</div>
            <div className="form-card-sub">
              El anunciante define al cliente final de la venta. Si hay agencia, ella es la que típicamente factura y paga.
            </div>
            <div className="r2">
              <div>
                <div className="fl fl-required">
                  Anunciante <FieldTag origin="catalogo" />
                </div>
                <select className="fsel" disabled={congelado} value={anuncianteId} onChange={(e) => onAnuncianteChange(e.target.value)}>
                  <option value="">Selecciona…</option>
                  {anunciantes.filter(esActivo).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.nombre_comercial}
                    </option>
                  ))}
                </select>
                <div className="fe">{errors.anunciante_id?.message}</div>
              </div>
              <div>
                <div className="fl">
                  Agencia <FieldTag origin="catalogo" /> <span className="derivado-hint">sugerida del anunciante</span>
                </div>
                <select className="fsel" disabled={congelado} value={watch("agencia_id")} onChange={(e) => onAgenciaChange(e.target.value)}>
                  <option value="">Sin agencia (venta directa)</option>
                  {agencias.filter(esActivo).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.nombre_agencia}
                    </option>
                  ))}
                </select>
                <div className="fe">{errors.agencia_id?.message}</div>
              </div>
            </div>

            <div className="r2">
              <div>
                <div className="fl">
                  Contrato <FieldTag origin="catalogo" /> <span className="derivado-hint">vigentes del anunciante</span>
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
              <div />
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Producto anunciado</div>
            <div className="r2">
              <div>
                <div className="fl">
                  Marca <FieldTag origin="catalogo" /> <span className="derivado-hint">filtrada por anunciante</span>
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
              <div>
                <div className="fl">Campaña</div>
                <input className="fi" placeholder="Descripción de la campaña anunciada" disabled={congelado} {...register("producto")} />
              </div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Campaña y montos</div>
            <div className="r3">
              <div>
                <div className="fl fl-required">Inicio de campaña</div>
                <input
                  className="fi"
                  type="date"
                  disabled={congelado}
                  min={hoyLocal()}
                  {...register("fecha_inicio_campania")}
                />
                <div className="fe">{errors.fecha_inicio_campania?.message}</div>
              </div>
              <div>
                <div className="fl fl-required">Fin de campaña</div>
                <input
                  className="fi"
                  type="date"
                  disabled={congelado}
                  min={fechaInicio || hoyLocal()}
                  {...register("fecha_fin_campania")}
                />
                <div className="fe">{errors.fecha_fin_campania?.message}</div>
              </div>
              <div>
                <div className="fl">
                  Días campaña <FieldTag origin="calculado" />
                </div>
                <div className="fv mono">{dias != null && dias > 0 ? `${dias} días` : "—"}</div>
              </div>
            </div>

            {/* ADR-180: compartido entre inicio/fin de campaña (un solo motivo para las
                dos), mismo criterio que el motivo de comisiones y el de Tarifa. */}
            {isEdit && (
              <>
                <div className="fl fl-required">
                  Motivo del cambio{" "}
                  <span style={{ color: "var(--text3)", fontWeight: 400 }}>
                    (si modificas el inicio o el fin de campaña)
                  </span>
                </div>
                <SearchableSelect
                  value={watch("motivo_cambio_fecha") ?? ""}
                  onChange={(v) => setValue("motivo_cambio_fecha", v)}
                  options={motivosCambioFecha.map((m) => ({ value: m.descripcion, label: m.descripcion }))}
                  placeholder={motivosFechaQuery.isLoading ? "Cargando…" : "Requerido al modificar la fecha…"}
                  disabled={!algunaFechaCambio}
                  onCreate={(texto) =>
                    crearMotivoFecha.mutate(
                      { clave_base: "CambioFecha", descripcion: texto },
                      { onSuccess: (nuevo) => setValue("motivo_cambio_fecha", nuevo.descripcion) },
                    )
                  }
                  creando={crearMotivoFecha.isPending}
                />
                <div className="fe">{errors.motivo_cambio_fecha?.message}</div>
              </>
            )}

            <div className="r2">
              <div>
                <div className="fl fl-required">
                  Producto{" "}
                  <FieldTag origin="catalogo" />{" "}
                  <span style={{ color: "var(--text3)", fontWeight: 400 }}>
                    (catálogo Producto Duración)
                  </span>
                </div>
                <select
                  className="fsel"
                  disabled={congelado || catalogoDuraciones.isLoading}
                  {...register("producto_tarifa", { onChange: () => setValue("duracion_spot", "") })}
                >
                  <option value="">{catalogoDuraciones.isLoading ? "Cargando…" : "Selecciona…"}</option>
                  {productosDuracion.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <div className="fe">{errors.producto_tarifa?.message}</div>
              </div>
              <div>
                <div className="fl">
                  Duración <FieldTag origin="catalogo" />
                </div>
                <select
                  className="fsel"
                  disabled={congelado || !productoTarifaActual || duracionesDelProducto.length === 0}
                  {...register("duracion_spot")}
                >
                  <option value="">
                    {!productoTarifaActual
                      ? "Elige un producto primero"
                      : duracionesDelProducto.length === 0
                        ? "Sin duración capturada para este producto"
                        : "Selecciona…"}
                  </option>
                  {duracionesDelProducto.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="r3">
              <div>
                <div className="fl fl-required">Total de spots</div>
                <input
                  className="fi"
                  style={{ fontFamily: "var(--mono)" }}
                  inputMode="numeric"
                  disabled={congelado || !productoTarifaActual}
                  {...register("total_spots")}
                />
                <div className="fe">{errors.total_spots?.message}</div>
              </div>
              <div>
                <div className="fl">Spots bonificables</div>
                <input
                  className="fi"
                  style={{ fontFamily: "var(--mono)" }}
                  inputMode="numeric"
                  disabled={congelado || !productoTarifaActual}
                  {...register("cantidad_spots_bonificables")}
                />
                <div className="fe">{errors.cantidad_spots_bonificables?.message}</div>
              </div>
              <div>
                <div className="fl fl-required">Precio unitario (MXN, por spot)</div>
                <Controller
                  control={control}
                  name="precio_unitario"
                  render={({ field }) => (
                    <MoneyInput
                      value={field.value}
                      onChange={field.onChange}
                      onBlur={field.onBlur}
                      disabled={congelado || !productoTarifaActual}
                    />
                  )}
                />
                <div className="fe">{errors.precio_unitario?.message}</div>
              </div>
            </div>

            {isEdit && !congelado && oeCount > 0 && (
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
                ⚠ Esta orden ya tiene {oeCount}{" "}
                {oeCount === 1 ? "Orden de Transmisión creada" : "Órdenes de Transmisión creadas"} con la
                tarifa anterior; las nuevas usarán la tarifa actualizada.
              </div>
            )}

            <div style={{ background: "var(--surface2)", borderRadius: "var(--r)", padding: "12px 14px", marginTop: 4 }} className="r5">
              <div>
                <div className="fl">Subtotal</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                  {fmtMonto(subtotalBruto)}
                </div>
              </div>
              <div>
                <div className="fl">Spots bonificables</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600, color: "var(--red-text)" }}>
                  {fmtMonto(subtotalBonificables)}
                </div>
              </div>
              <div>
                <div className="fl">Spots facturables</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                  {fmtMonto(subtotal)}
                </div>
              </div>
              <div>
                <div className="fl">IVA ({(IVA_RATE * 100).toFixed(0)}%)</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                  {fmtMonto(iva)}
                </div>
              </div>
              <div>
                <div className="fl">Total c/IVA</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600, color: "var(--purple-text)" }}>
                  {fmtMonto(total)}
                </div>
              </div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Facturación</div>
            <div className="fl">Dirección de facturación</div>
            {/* ADR-200 (petición del usuario): el campo SIEMPRE es de solo lectura — se
                autocompleta con el domicilio del Anunciante o la Agencia (ADR-181) y no
                se captura a mano; si el catálogo no tiene domicilio, se queda vacío y se
                corrige ahí (catálogo de Anunciante/Agencia), no aquí. */}
            <textarea className="ftxt" rows={2} readOnly {...register("direccion_facturacion")} />
            {/* ADR-141 (petición del usuario): antes eran 2 checkboxes independientes —
                permitían los 4 estados (ninguno/uno/otro/los dos), pero solo UNO tiene
                sentido de negocio a la vez. Un solo radio group garantiza exactamente
                uno seleccionado siempre; siguen siendo 2 columnas booleanas del modelo
                (spec BD v2, sin cambio de esquema) — el radio solo pone la contraria en
                `false` al elegir una. Default (alta nueva): "Facturación directa al
                cliente".
                ADR-181 (petición del usuario): al elegir cada opción, "Dirección de
                facturación" se recalcula desde la fuente correspondiente. "Facturación
                directa al cliente" siempre trae algo del Anunciante (si hay uno
                elegido). "Facturación a la Agencia" usa su domicilio estructurado si lo
                tiene capturado — si NO lo tiene (o no hay Agencia ligada), VACÍA el
                campo para que el usuario la capture a mano (a propósito: no debe quedar
                pegada la dirección del Anunciante bajo esta opción). */}
            <div className="r2" style={{ marginTop: 6 }}>
              <label className="check-box" style={{ cursor: congelado ? "not-allowed" : "pointer" }}>
                <input
                  type="radio"
                  name="tipo_facturacion"
                  disabled={congelado}
                  checked={watch("facturacion_directa_cliente")}
                  onChange={() => {
                    setValue("facturacion_directa_cliente", true);
                    setValue("afiliado_factura_directo_al_cliente", false);
                    const anunciante = anunciantes.find((a) => a.id === watch("anunciante_id"));
                    if (anunciante) setValue("direccion_facturacion", direccionDeAnunciante(anunciante));
                  }}
                />
                <div>
                  <div className="check-box-title">Facturación directa al cliente</div>
                  <div className="check-box-desc">Se factura al anunciante sin pasar por la agencia.</div>
                </div>
              </label>
              <label
                className="check-box"
                style={{ cursor: congelado || !agId ? "not-allowed" : "pointer" }}
              >
                <input
                  type="radio"
                  name="tipo_facturacion"
                  // Bug corregido (petición del usuario, con captura): no se puede elegir
                  // "Facturación a la Agencia" sin antes tener una agencia seleccionada.
                  disabled={congelado || !agId}
                  checked={watch("afiliado_factura_directo_al_cliente")}
                  onChange={() => {
                    setValue("afiliado_factura_directo_al_cliente", true);
                    setValue("facturacion_directa_cliente", false);
                    const agencia = findAgencia(watch("agencia_id") || null);
                    const domicilio = agencia
                      ? formatDomicilio({
                          calle: agencia.calle ?? null,
                          numero_exterior: agencia.numero_exterior ?? null,
                          numero_interior: agencia.numero_interior ?? null,
                          colonia: agencia.colonia ?? null,
                          localidad: agencia.localidad ?? null,
                          municipio: agencia.municipio ?? null,
                          estado: agencia.estado ?? null,
                          pais: agencia.pais ?? null,
                          codigo_postal: agencia.codigo_postal ?? null,
                        })
                      : null;
                    // Con domicilio, lo usa; sin él, limpia el campo para que el usuario
                    // capture la dirección a mano (a diferencia de "Facturación directa
                    // al cliente", que siempre trae algo del Anunciante).
                    setValue("direccion_facturacion", domicilio ?? "");
                  }}
                />
                <div>
                  <div className="check-box-title">Facturación a la Agencia</div>
                  <div className="check-box-desc">
                    {agId
                      ? "La agencia factura al anunciante."
                      : "Selecciona una agencia para poder usar esta opción."}
                  </div>
                </div>
              </label>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Adjuntos del cliente</div>
            <div className="fl">Adjuntar ODC</div>
            <AdjuntoOrdenInput
              tipo="odc"
              value={odcPdfRef}
              onChange={(ref) => setValue("odc_pdf_ref", ref)}
              disabled={congelado}
            />
          </div>

          <div className="zone-header">
            <div className="zone-bar b" />
            <div>
              <div className="zone-title">ZONA B · PROCESAMIENTO INTERNO</div>
              <div className="zone-sub">Decisiones de OIR sobre esta venta. No vienen del cliente.</div>
            </div>
          </div>

          <div className="form-card">
            <div className="form-card-title">Equipo comercial y comisiones</div>
            <div className="form-card-sub">
              El % de cada uno se sugiere desde el catálogo pero queda <strong>snapshot en la OC</strong>: el catálogo puede
              cambiar después sin afectar esta venta. <strong>Editable durante captura y operación; se congela al cerrar la
              orden</strong> — desde ese momento solo editable con permiso (parámetro sensible, queda en LogCambioParametro).
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
                🔒 Orden congelada ({estatusActual}): el formulario completo es de solo lectura, incluyendo los % de comisión.
              </div>
            )}

            <div className="r2">
              <div>
                <div className="fl fl-required">
                  Vendedor principal <FieldTag origin="catalogo" />
                </div>
                <select
                  className="fsel"
                  disabled={congelado}
                  value={vpId}
                  onChange={(e) => onVendedorChange("vendedor_principal_id", e.target.value)}
                >
                  <option value="">Selecciona…</option>
                  {vendedores
                    .filter(esActivo)
                    .filter((v) => v.id !== vsId)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.nombre_vendedor}
                      </option>
                    ))}
                </select>
                <div className="fe">{errors.vendedor_principal_id?.message}</div>
              </div>
              <div>
                <SensitiveField
                  label="% comisión vendedor principal"
                  register={register("porcentaje_comision_vendedor_principal_snap", { disabled: !canEditComisiones })}
                  error={errors.porcentaje_comision_vendedor_principal_snap?.message}
                  badge={
                    <>
                      <FieldTag origin="derivado" text="Snapshot" /> {badgeOverride(pctVp, findVendedor(vpId)?.porcentaje_comision_default)}
                    </>
                  }
                />
              </div>
            </div>
            <div className="r2">
              <div>
                <div className="fl">
                  Vendedor secundario <FieldTag origin="catalogo" />
                </div>
                <select
                  className="fsel"
                  disabled={congelado}
                  value={vsId}
                  onChange={(e) => onVendedorChange("vendedor_secundario_id", e.target.value)}
                >
                  <option value="">Sin vendedor secundario</option>
                  {vendedores
                    .filter(esActivo)
                    .filter((v) => v.id !== vpId)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.nombre_vendedor}
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <SensitiveField
                  label="% comisión vendedor secundario"
                  register={register("porcentaje_comision_vendedor_secundario_snap", { disabled: !canEditComisiones })}
                  error={errors.porcentaje_comision_vendedor_secundario_snap?.message}
                  badge={
                    <>
                      <FieldTag origin="derivado" text="Snapshot" />{" "}
                      {vsId ? badgeOverride(pctVs, findVendedor(vsId)?.porcentaje_comision_default) : null}
                    </>
                  }
                />
              </div>
            </div>

            <div className="r2">
              <div>
                <SensitiveField
                  label="% comisión agencia"
                  register={register("porcentaje_comision_agencia_snap", { disabled: !canEditComisiones })}
                  error={errors.porcentaje_comision_agencia_snap?.message}
                  badge={
                    <>
                      <FieldTag origin="derivado" text="Snapshot" /> {agId ? badgeOverride(pctAg, findAgencia(agId)?.porcentaje_comision_agencia_default) : null}
                    </>
                  }
                />
              </div>
              <div>
                <div className="fl">
                  Giro empresarial <FieldTag origin="catalogo" />
                </div>
                <select className="fsel" disabled={congelado} {...register("categoria_id")}>
                  <option value="">Selecciona…</option>
                  {categorias.filter(esActivo).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre_categoria}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {/* Compartido entre los 3 % de arriba (antes solo vivía junto al de agencia, lo
                que dejaba sin dónde capturar el motivo un cambio de comisión de vendedor). */}
            {/* ADR-249 (petición del usuario): visible también en ALTA (antes solo en
                edición) — `canEditComisiones` ya es siempre `true` en alta (`congelado`
                exige `isEdit`). Bug corregido (petición del usuario, con captura): en
                edición el combo se habilitaba SOLO si el % cambiaba en esta sesión
                (`algunaComisionCambio`), dejándolo inerte —sin poder abrirlo siquiera—
                cuando el % ya venía sobrescrito de una edición anterior; ahora también se
                habilita si diverge del catálogo ahora mismo (`algunaComisionDivergeCatalogo`),
                aunque no lo hayas vuelto a tocar. El motivo sigue sin ser obligatorio para
                guardar si no cambiaste nada. */}
            {canEditComisiones && (
              <>
                <div className="fl fl-required">
                  Motivo del cambio <span style={{ color: "var(--text3)", fontWeight: 400 }}>(si modificas cualquiera de los 3 % anteriores)</span>
                </div>
                <SearchableSelect
                  value={watch("motivo_cambio_comision") ?? ""}
                  onChange={(v) => setValue("motivo_cambio_comision", v)}
                  options={motivosCambioComision.map((m) => ({ value: m.descripcion, label: m.descripcion }))}
                  placeholder={motivosComisionQuery.isLoading ? "Cargando…" : "Requerido al modificar el valor…"}
                  disabled={!(algunaComisionCambio || algunaComisionDivergeCatalogo)}
                  onCreate={(texto) =>
                    crearMotivoComision.mutate(
                      { clave_base: "CambioComision", descripcion: texto },
                      { onSuccess: (nuevo) => setValue("motivo_cambio_comision", nuevo.descripcion) },
                    )
                  }
                  creando={crearMotivoComision.isPending}
                />
                <div className="fe">{errors.motivo_cambio_comision?.message}</div>
              </>
            )}
          </div>

          <div className="form-card">
            <div className="form-card-title">Observaciones internas</div>
            <div className="fl">
              Observación predefinida <FieldTag origin="catalogo" />
            </div>
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
        </div>

        {/* ── Columna de resumen ── */}
        <div>
          <div className="info-panel">
            <div className="info-panel-title">Cálculos en vivo</div>
            <div className="fl">Días de campaña</div>
            <div className="fv mono">{dias != null && dias > 0 ? `${dias} días` : "—"}</div>
            <div className="fl">Subtotal</div>
            <div className="fv mono">{fmtMonto(subtotalBruto)}</div>
            <div className="fl">Spots bonificables</div>
            <div className="fv mono">{fmtMonto(subtotalBonificables)}</div>
            <div className="fl">Spots facturables</div>
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
            {isEdit ? "Guardar cambios" : "Guardar"}
          </button>
        </div>
      </div>
    </div>
  );
}
