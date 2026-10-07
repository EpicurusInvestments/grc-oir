/** Alta de OrdenEstacion — pantalla completa (patrón form full-screen). Puede llegar ya
 * "amarrada" a una OrdenCliente (desde su detalle, botón "+ Asignar estaciones") o abrirse
 * suelta desde la lista de Órdenes de Transmisión, en cuyo caso primero hay que elegir la
 * Orden de Servicio de origen entre las elegibles (capturada o ya en estado 2; no
 * congeladas).
 *
 * Balance de spots en vivo + constructor de `periodo_transmision`, igual que en el
 * prototipo aprobado: nada se calcula "a mano", todo sale de `state/selectors.ts`.
 *
 * ADR-169 (petición del usuario): "Producto" y "Duración" se llenan desde el catálogo
 * `DuracionSpotCatalogo` ("Producto Duración", F0-06) — mismo patrón ya usado en Tarifa
 * (ADR-166) y "Orden de Servicio" (OrdenCliente, ADR-167/168): el select de Producto
 * lista los valores distintos y activos del catálogo; al elegir uno, el select de
 * Duración lista las `descripcion_duracion` de ESE producto, excluyendo siempre el
 * literal "sin resultado" (nunca se muestra como opción). Si no queda ninguna duración
 * real, el select de Duración se deshabilita ("Sin duración capturada para este
 * producto") pero SIN bloquear nada — Tarifa y el resto de los campos se habilitan en
 * cuanto se elige un Producto (antes dependían de Duración). La sugerencia de tarifa
 * del catálogo (`tarifaReferencia`) sigue funcionando igual: sigue siendo una
 * comparación de texto exacta contra `TarifaPlaza`, que también es texto libre desde
 * ADR-166.
 *
 * ADR-173 (petición del usuario): al CREAR una OE que llega ya amarrada a su OC
 * (`ocIdFijo`, el flujo normal desde "+ Asignar estaciones"), Producto/Duración
 * arrancan precargados con los de esa Orden de Servicio en vez de vacíos — el resto de
 * la pantalla (validaciones, habilitado/deshabilitado de Duración, sugerencia de
 * tarifa) no cambia en nada, el usuario sigue pudiendo editarlos como siempre.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useDuracionesSpot } from "@/modules/catalogos/duracionSpot/hooks";
import { SIN_RESULTADO } from "@/modules/catalogos/duracionSpot/types";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { MoneyInput, SavingOverlay, SearchableSelect } from "@/shared/ui";

import {
  asignarAudioDiaApi,
  listarAudiosOrdenEstacionApi,
  subirMaterialStagingApi,
} from "../../adapters/escrituraApi";
import { ordenEstacionAudioFromApi } from "../../adapters/fromApi";
import { CalendarioPeriodoTransmision } from "../../components/CalendarioPeriodoTransmision";
import { PeriodoTransmisionGrid, problemasDeFila } from "../../components/PeriodoTransmisionGrid";
import { SpotBalanceBar } from "../../components/SpotBalanceBar";
import { AUDIO_ORDEN_ACCEPT, AUDIO_ORDEN_MAX_BYTES, EXTENSIONES_AUDIO_ORDENES } from "../../constants";
import { fmtMonto, fmtPct } from "../../format";
import {
  esActivo,
  findAfiliado,
  findEstacion,
  findPlaza,
  estaciones,
  tarifaReferencia,
} from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { oesDeOC, oiTotalSpots, type BalanceSpotsOC } from "../../state/selectors";
import type {
  OrdenCliente,
  OrdenEstacion,
  OrdenEstacionAudio,
  OrdenEstacionInput,
  PeriodoTransmisionRow,
} from "../../types";
import { MaterialATransmitir } from "./MaterialATransmitir";

const esSinResultado = (v: string) => v.trim().toLowerCase() === SIN_RESULTADO;

interface OrdenEstacionFormProps {
  /** Si viene fija (desde el detalle de una OC), aquí ya no se puede cambiar de OC. */
  ocIdFijo?: string;
  /** OE ya existente a corregir (edición). Si viene, el form arranca precargado y
   *  bloquea OC/estación — el backend real no permite reasignarlas por esta vía, solo
   *  corregir tarifa/días/observaciones (ver `FROZEN_STATES_OE` del backend). */
  oe?: OrdenEstacion;
  submitting?: boolean;
  submitError?: string | null;
  /** ADR-109: devuelve la OE creada/actualizada (con su id REAL) para que el propio
   *  formulario pueda subir el material a transmitir "pendiente" justo después de
   *  guardar — `undefined` si `onGuardar` falló (el formulario simplemente no sube
   *  nada; el error ya lo muestra `submitError`, que sigue siendo responsabilidad del
   *  padre). */
  onGuardar: (ocId: string, input: OrdenEstacionInput) => Promise<OrdenEstacion | undefined>;
  /** Al CREAR, manda la OC de origen elegida (si ya hay una) para que el padre pueda
   *  regresar a "Órdenes de Servicio" ubicada ahí — `undefined` en edición (no aplica,
   *  ahí Cancelar solo vuelve al detalle de la propia OE). */
  onCancelar: (ocId?: string) => void;
}

const OC_ELEGIBLE = (oc: OrdenCliente) => oc.estatus_orden === "orden_cliente_con_vobo" || oc.estatus_orden === "orden_interna";

export function OrdenEstacionForm({ ocIdFijo, oe, submitting, submitError, onGuardar, onCancelar }: OrdenEstacionFormProps) {
  const isEdit = oe != null;
  const { state, cancelarDia } = useOrdenes();
  const [ocId, setOcId] = useState<string>(ocIdFijo ?? oe?.orden_id ?? "");
  const [estacionId, setEstacionId] = useState(oe?.estacion_id ?? "");
  // ADR-173 (petición del usuario): al CREAR una OE ya amarrada a una OC (llega con
  // `ocIdFijo`, el flujo normal desde "+ Asignar estaciones" de la Orden de Servicio),
  // Producto/Duración se precargan con los que esa OC capturó — el usuario los puede
  // cambiar igual, es solo el valor inicial. Si la OC no capturó Duración (quedó sin
  // seleccionar o es el literal "sin resultado"), arranca vacía — el que el select se
  // deshabilite o no sigue siendo el mismo criterio de siempre (si el producto tiene
  // duraciones reales en el catálogo), sin ningún cambio ahí.
  const ocOrigen = !isEdit && ocIdFijo ? state.ordenesCliente.find((o) => o.id === ocIdFijo) : undefined;
  const [productoTarifa, setProductoTarifa] = useState(oe?.producto_tarifa ?? ocOrigen?.producto_tarifa ?? "");
  const duracionInicial = oe?.duracion_spot ?? ocOrigen?.duracion_spot ?? "";
  const [duracionSpot, setDuracionSpot] = useState(
    duracionInicial && !esSinResultado(duracionInicial) ? duracionInicial : "",
  );
  const [precioSpot, setPrecioSpot] = useState(oe ? String(oe.precio_spot) : "");
  const [motivoCambioTarifa, setMotivoCambioTarifa] = useState("");
  const [spotsBonificables, setSpotsBonificables] = useState(oe ? String(oe.cantidad_spots_bonificables) : "0");
  const [observaciones, setObservaciones] = useState(oe?.observaciones_estacion ?? "");
  const [periodo, setPeriodo] = useState<PeriodoTransmisionRow[]>(oe?.periodo_transmision ?? []);
  // ADR-103: "Material a Transmitir" solo existe en edición (subir un audio necesita un
  // orden_estacion_id real) — se recarga cada vez que cambia la OE en edición.
  const [audios, setAudios] = useState<OrdenEstacionAudio[]>([]);
  useEffect(() => {
    if (!oe) {
      setAudios([]);
      return;
    }
    let cancelado = false;
    listarAudiosOrdenEstacionApi(oe.id).then((dtos) => {
      if (!cancelado) setAudios(dtos.map(ordenEstacionAudioFromApi));
    });
    return () => {
      cancelado = true;
    };
  }, [oe]);

  // ADR-109: al CREAR, todavía no hay `orden_estacion_id` real contra el que colgar un
  // `OrdenEstacionAudio` — pero SÍ se puede subir el ARCHIVO a S3 de inmediato (mismo
  // mecanismo ya usado para el PDF de la Orden de Servicio: un endpoint "staging" sin
  // ningún id de padre, `POST /ordenes/material-staging`). Se guarda el `ref` devuelto
  // (no el `File`) y se manda en `audios_staging` al crear la OE — el servicio crea las
  // filas reales en ESE mismo orden. Al EDITAR, el material se sigue subiendo con el
  // endpoint dedicado de siempre vía `MaterialATransmitir` (más abajo) — no aplica aquí.
  const [audiosStaging, setAudiosStaging] = useState<{ ref: string; nombre_archivo: string }[]>([]);
  const [errorAudioStaging, setErrorAudioStaging] = useState<string | null>(null);
  const [subiendoAudioStaging, setSubiendoAudioStaging] = useState(false);
  const audiosInputRef = useRef<HTMLInputElement>(null);

  const onElegirAudioStaging = async (archivo: File | undefined) => {
    setErrorAudioStaging(null);
    if (!archivo) return;
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(EXTENSIONES_AUDIO_ORDENES as readonly string[]).includes(ext)) {
      setErrorAudioStaging(`Formato no permitido. Usa: ${EXTENSIONES_AUDIO_ORDENES.join(", ")}.`);
    } else if (archivo.size > AUDIO_ORDEN_MAX_BYTES) {
      setErrorAudioStaging(`El archivo excede el tamaño máximo permitido (${Math.round(AUDIO_ORDEN_MAX_BYTES / 1024 / 1024)} MB).`);
    } else {
      setSubiendoAudioStaging(true);
      try {
        const dto = await subirMaterialStagingApi(archivo);
        setAudiosStaging((prev) => [...prev, { ref: dto.ref, nombre_archivo: dto.nombre_archivo }]);
      } catch (e) {
        setErrorAudioStaging(e instanceof ApiRequestError ? e.message : "No se pudo subir el audio.");
      } finally {
        setSubiendoAudioStaging(false);
      }
    }
    if (audiosInputRef.current) audiosInputRef.current.value = "";
  };
  const quitarAudioStaging = (idx: number) =>
    setAudiosStaging((prev) => prev.filter((_, i) => i !== idx));

  // Vista previa para la tabla: en edición, los audios YA subidos a la OE; al crear, los
  // que ya se subieron a S3 en este mismo formulario (staging) — para que el default se
  // vea de inmediato, sin esperar a guardar la orden.
  const audiosVistaPrevia: OrdenEstacionAudio[] = isEdit
    ? audios
    : audiosStaging.map((a, i) => ({ id: a.ref, nombre_archivo: a.nombre_archivo, orden: i }));
  // ADR-110 (petición del usuario): "Material a Transmitir" pasa a ser OBLIGATORIO
  // para CREAR — se necesita al menos un audio subido antes de poder generar/capturar
  // fechas. Editar una OE que ya tenía días capturados de ANTES de esta regla no debe
  // quedar bloqueada retroactivamente solo porque no tiene material (todavía) — por
  // eso `isEdit` exime la regla aquí.
  const hayMaterial = isEdit || audiosVistaPrevia.length > 0;

  const onAsignarAudio = (diaId: string, audioId: string | null) => {
    if (!oe) return;
    const anterior = periodo.find((r) => r.orden_estacion_dia_id === diaId)?.orden_estacion_audio_id ?? null;
    // Optimista: el endpoint es dedicado e inmediato (no se acumula con "Guardar"), así
    // que se refleja en la fila de inmediato en vez de esperar una recarga completa; si
    // la llamada falla, se revierte al valor anterior.
    setPeriodo((rows) =>
      rows.map((r) => (r.orden_estacion_dia_id === diaId ? { ...r, orden_estacion_audio_id: audioId } : r)),
    );
    asignarAudioDiaApi(oe.id, diaId, audioId).catch(() => {
      setPeriodo((rows) =>
        rows.map((r) => (r.orden_estacion_dia_id === diaId ? { ...r, orden_estacion_audio_id: anterior } : r)),
      );
    });
  };

  const [errorCancelarDia, setErrorCancelarDia] = useState<string | null>(null);
  const onCancelarDia = async (diaId: string, motivo: string) => {
    if (!oe) return;
    setErrorCancelarDia(null);
    // Optimista, igual que `onAsignarAudio` — si el backend rechaza (p.ej. excedería los
    // spots bonificables restantes), se revierte y se muestra el motivo del rechazo.
    setPeriodo((rows) => rows.map((r) => (r.orden_estacion_dia_id === diaId ? { ...r, cancelada: true } : r)));
    try {
      await cancelarDia(oe.id, diaId, motivo);
    } catch (e) {
      setPeriodo((rows) => rows.map((r) => (r.orden_estacion_dia_id === diaId ? { ...r, cancelada: false } : r)));
      setErrorCancelarDia(e instanceof ApiRequestError ? e.message : "No se pudo cancelar la transmisión de ese día.");
    }
  };

  const ocsElegibles = state.ordenesCliente.filter(OC_ELEGIBLE);
  const oc = ocId ? state.ordenesCliente.find((o) => o.id === ocId) : undefined;

  const estacion = estacionId ? findEstacion(estacionId) : undefined;
  const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
  const plaza = estacion ? findPlaza(estacion.plaza_id) : undefined;

  // ── Producto/Duración desde el catálogo "Producto Duración" (ADR-169) ─────────
  const catalogoDuraciones = useDuracionesSpot().useList({ activo: true, size: 100 });
  const entradasDuracion = useMemo(
    () => catalogoDuraciones.data?.items ?? [],
    [catalogoDuraciones.data],
  );

  const productosDuracion = useMemo(() => {
    const vistos = new Map<string, string>();
    for (const e of entradasDuracion) vistos.set(e.producto.trim().toLowerCase(), e.producto);
    // Respaldo: el producto ya elegido (de una OE existente al editar, o precargado
    // desde la OC de origen al crear — ADR-173) que todavía no esté en el catálogo no
    // debe perder su valor.
    if (productoTarifa && !vistos.has(productoTarifa.trim().toLowerCase())) {
      vistos.set(productoTarifa.trim().toLowerCase(), productoTarifa);
    }
    return [...vistos.values()].sort((a, b) => a.localeCompare(b, "es"));
  }, [entradasDuracion, productoTarifa]);

  const duracionesDelProducto = useMemo(() => {
    const delProducto = entradasDuracion.filter(
      (e) => e.producto.trim().toLowerCase() === productoTarifa.trim().toLowerCase(),
    );
    const vistos = new Map<string, string>();
    for (const e of delProducto) {
      if (esSinResultado(e.descripcion_duracion)) continue;
      vistos.set(e.descripcion_duracion.trim().toLowerCase(), e.descripcion_duracion);
    }
    // Mismo respaldo que arriba: la duración ya elegida (de una OE existente al editar,
    // o precargada desde la OC de origen al crear — ADR-173) que todavía no esté en el
    // catálogo para ESTE producto no debe perder su valor. Cambiar de producto siempre
    // limpia `duracionSpot` (ver su `onChange`), así que esto nunca arrastra una
    // duración de un producto distinto al ya seleccionado.
    if (duracionSpot && !esSinResultado(duracionSpot) && !vistos.has(duracionSpot.trim().toLowerCase())) {
      vistos.set(duracionSpot.trim().toLowerCase(), duracionSpot);
    }
    return [...vistos.values()];
  }, [entradasDuracion, productoTarifa, duracionSpot]);

  // ADR-102/ADR-106: tarifa ACTIVA del catálogo para (estación, duración — capturada POR
  // ESTACIÓN, ya no heredada de la orden —, producto). Sin ella no hay nada que
  // sugerir/auditar: precio_spot sigue siendo 100% libre, igual que antes.
  // ADR-158: ya no filtra por tipo de señal — se retiró de TarifaPlaza (es propiedad de
  // la Estación, ya implícita en `estacion.id`).
  const tarifaSugerida = useMemo(() => {
    if (!estacion || !productoTarifa || !duracionSpot) return undefined;
    return tarifaReferencia(estacion.id, duracionSpot, productoTarifa);
  }, [estacion, productoTarifa, duracionSpot]);

  // Auto-carga `precioSpot` con la tarifa sugerida SOLO si el campo está vacío o todavía
  // tiene la ÚLTIMA sugerencia sin tocar — así no pisa un valor que el usuario ya escribió
  // a mano (ni el que ya traía una OE existente al editar). ADR-170 (petición del
  // usuario): cambiar de Producto o Duración ahora limpia `precioSpot` explícitamente
  // (ver los `onChange` de ambos selects) ANTES de que este efecto corra — así, aunque
  // el usuario haya editado la tarifa a mano, cambiar de combinación siempre la
  // reemplaza por la nueva sugerencia (o la deja vacía si no hay ninguna), en vez de
  // arrastrar el valor editado.
  const ultimaSugeridaRef = useRef<string | null>(null);
  useEffect(() => {
    // ADR-115 (fix): el valor "anterior" se captura en un `const` ANTES de mutar el ref —
    // el callback de `setPrecioSpot` no corre de inmediato (React lo difiere a cuando
    // procesa la cola de estado), así que si el callback leyera `ultimaSugeridaRef.current`
    // directo, para entonces el ref ya habría sido reescrito por la línea de abajo (mismo
    // efecto, ejecutada síncrona) y SIEMPRE vería el valor NUEVO en vez del viejo —
    // rompía justo el caso de "sin tarifa": el campo nunca se vaciaba porque la
    // comparación terminaba comparando contra `null` en vez del precio realmente
    // sugerido antes.
    const anteriorSugerida = ultimaSugeridaRef.current;
    if (!tarifaSugerida) {
      // Esta combinación (estación/producto/duración) no tiene tarifa en el catálogo: el
      // campo debe quedar VACÍO para que el usuario la capture — no debe arrastrar el
      // valor de la ÚLTIMA combinación que sí tenía tarifa. Un valor tecleado a mano
      // (que no coincide con la última sugerencia) se respeta.
      setPrecioSpot((actual) => (actual === "" || actual === anteriorSugerida ? "" : actual));
      ultimaSugeridaRef.current = null;
      return;
    }
    const sugerida = String(tarifaSugerida.tarifa_neta);
    setPrecioSpot((actual) => (actual === "" || actual === anteriorSugerida ? sugerida : actual));
    ultimaSugeridaRef.current = sugerida;
  }, [tarifaSugerida]);

  // Al editar, la propia OE ya está en `state.ordenesEstacion` con su periodo VIEJO — sin
  // excluirla aquí, el balance en vivo la contaría dos veces (una vez como "ya asignado",
  // otra vez como `totalEstaOI` con el periodo nuevo que se está editando). Mismo criterio
  // que usa el backend real (`hermanas_ids` excluye la propia OE al validar el balance).
  const otrasOEDeLaOC = useMemo(
    () => (oc ? oesDeOC(state.ordenesEstacion, oc.id).filter((o) => o.id !== oe?.id) : []),
    [oc, state.ordenesEstacion, oe?.id],
  );
  // ADR-104: un día cancelado libera su cupo — no cuenta para el balance ni el importe,
  // mismo criterio que `oiTotalSpots` (selectors.ts) para las OE hermanas de abajo.
  const totalEstaOI = periodo.reduce((s, p) => (p.cancelada ? s : s + (p.spots_diarios || 0)), 0);
  // Balance "en vivo": no se puede reusar `balanceSpotsOC` tal cual porque esta OI todavía
  // no existe como `OrdenEstacion` real — se arma a mano con la misma fórmula.
  const balance: BalanceSpotsOC | null = oc
    ? (() => {
        const spotsYaAsignados = otrasOEDeLaOC.reduce((s, oe) => s + oiTotalSpots(oe), 0);
        const totalOC = oc.total_spots || 0;
        const asignados = spotsYaAsignados + totalEstaOI;
        const porAsignar = totalOC - asignados;
        return {
          totalOC,
          asignados,
          porAsignar,
          pctAsignado: totalOC > 0 ? Math.min(100, (asignados / totalOC) * 100) : 0,
          sobreAsignado: asignados > totalOC,
        };
      })()
    : null;

  const precio = Number(precioSpot) || 0;
  const bonificablesRaw = Number(spotsBonificables) || 0;
  const bonificablesExcede = bonificablesRaw > totalEstaOI;
  // ADR-068: los bonificables reducen el Importe, no los spots asignados (esos siguen
  // contando para el balance de la OC, arriba).
  const spotsFacturables = Math.max(totalEstaOI - bonificablesRaw, 0);
  const importe = spotsFacturables * precio;
  // ADR-101: sin candado — la tarifa de la estación puede superar la tarifa cliente; el
  // % de participación OIR simplemente se vuelve negativo (ver panel "Cálculos en vivo").
  const pctOIR = oc && oc.precio_unitario > 0 ? ((oc.precio_unitario - precio) / oc.precio_unitario) * 100 : 0;

  // ADR-102: solo se exige motivo cuando el precio final se APARTA de la tarifa
  // sugerida — coincidir con ella (o no tener ninguna tarifa capturada) no audita nada.
  // ADR-162: en edición, además debe haber CAMBIADO respecto al precio ya guardado
  // (`oe.precio_spot`) — si no se tocó, la divergencia con el catálogo ya se justificó
  // antes; volver a pedir el motivo en cada edición solo duplicaba el log de auditoría.
  const tarifaDivergente =
    tarifaSugerida != null &&
    precio !== tarifaSugerida.tarifa_neta &&
    (!isEdit || precio !== oe!.precio_spot);

  const errores: string[] = [];
  if (!oc) errores.push("Selecciona la Orden de Servicio de origen.");
  if (oc && !estacionId) errores.push("Selecciona una estación.");
  // Solo obligatorio al CREAR (mismo criterio que el backend: `OrdenEstacionCreate.producto_tarifa`
  // es requerido, `OrdenEstacionUpdate.producto_tarifa` es opcional) — así una OE existente sin
  // este dato (sembrada antes de ADR-102) sigue editable sin forzar a elegirlo primero.
  if (oc && !isEdit && !productoTarifa) errores.push("Selecciona el producto.");
  // ADR-169 (petición del usuario): Duración ya NO es obligatoria — un producto sin
  // ninguna duración real en el catálogo (p.ej. Mención) puede quedarse sin capturar,
  // sin bloquear el resto de la Orden de Transmisión.
  if (oc && (!precioSpot.trim() || precio <= 0)) errores.push("Captura una tarifa por spot mayor a 0.");
  if (tarifaDivergente && !motivoCambioTarifa.trim()) {
    errores.push("El precio no coincide con la tarifa sugerida del catálogo: captura el motivo del cambio.");
  }
  // ADR-110: "Material a Transmitir" es obligatorio — sin al menos un audio no tiene
  // sentido capturar fechas (no habría qué transmitir ese día).
  if (oc && !hayMaterial) errores.push("Sube al menos un material a transmitir.");
  if (periodo.length === 0) errores.push("Captura al menos un día de transmisión.");
  periodo.forEach((p, i) => {
    const problemas = oc ? problemasDeFila(p, { inicio: oc.fecha_inicio_campania, fin: oc.fecha_fin_campania }) : [];
    if (problemas.length > 0) errores.push(`Día ${i + 1}: ${problemas[0]}`);
  });
  if (balance && balance.sobreAsignado) errores.push(`Excede el total de la OC por ${Math.abs(balance.porAsignar)} spots.`);
  if (bonificablesExcede) errores.push(`Los spots bonificables (${bonificablesRaw}) no pueden exceder los spots asignados de esta OI (${totalEstaOI}).`);

  const listo = errores.length === 0;

  const onEstacionChange = (id: string) => {
    setEstacionId(id);
  };

  const guardar = async () => {
    if (!oc || !listo) return;
    const input: OrdenEstacionInput = {
      estacion_id: estacionId,
      plaza_id: estacion!.plaza_id,
      producto_tarifa: productoTarifa || undefined,
      duracion_spot: duracionSpot || undefined,
      precio_spot: precio,
      cantidad_spots_bonificables: bonificablesRaw,
      periodo_transmision: periodo,
      observaciones_estacion: observaciones.trim(),
      motivo_cambio_tarifa: tarifaDivergente ? motivoCambioTarifa.trim() : undefined,
      // ADR-109: ya subidos a S3 (staging) — el backend crea las filas reales al crear
      // la OE, en este mismo orden.
      audios_staging: !isEdit && audiosStaging.length > 0 ? audiosStaging : undefined,
    };
    await onGuardar(oc.id, input);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="cat-header">
        <div className="cat-title">{oe ? `Editar: ${oe.folio_orden_interna}` : "Nueva Orden de Transmisión"}</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 22, display: "grid", gridTemplateColumns: "1fr 320px", gap: 24, alignContent: "start" }}>
        <div>
          <div className="form-card">
            <div className="form-card-title">Orden de Servicio de origen</div>
            {ocIdFijo || isEdit ? (
              <div className="fv mono">{oc?.folio_orden}</div>
            ) : (
              <>
                <SearchableSelect
                  value={ocId}
                  onChange={setOcId}
                  options={ocsElegibles.map((o) => ({ value: o.id, label: `${o.folio_orden} — ${o.numero_orden_cliente}` }))}
                />
                {ocsElegibles.length === 0 && (
                  <div className="fv muted" style={{ fontSize: 12 }}>
                    No hay Órdenes de Servicio elegibles (no deben estar congeladas).
                  </div>
                )}
              </>
            )}
          </div>

          {oc && (
            <>
              <div className="form-card">
                <div className="form-card-title">Datos de la Orden de Transmisión</div>
                <div className="fl fl-required">Estación</div>
                <select
                  className="fsel"
                  value={estacionId}
                  disabled={isEdit}
                  onChange={(e) => onEstacionChange(e.target.value)}
                  title={isEdit ? "La estación no se puede cambiar al editar — crea una OE nueva si es otra estación." : undefined}
                >
                  <option value="">Selecciona…</option>
                  {/* ADR-136 (petición del usuario): "Estación-Siglas-Frecuencia" — antes
                      solo mostraba "Estación (Frecuencia)". */}
                  {estaciones.filter(esActivo).map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.nombre_estacion}-{e.siglas || "—"}-{e.frecuencia}
                    </option>
                  ))}
                </select>
                {estacion && (
                  <div className="heredado-block" style={{ marginTop: 4 }}>
                    <div className="heredado-title">Datos heredados de la estación</div>
                    <div className="heredado-grid">
                      <div className="heredado-row">
                        <span className="heredado-lbl">Plaza</span>
                        <span className="heredado-val">{plaza?.nombre_plaza ?? "—"}</span>
                      </div>
                      <div className="heredado-row">
                        <span className="heredado-lbl">Afiliado</span>
                        <span className="heredado-val">{afiliado?.nombre_afiliado ?? "—"}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* ADR-106: revelado progresivo Estación → Producto → Duración → Tarifa
                    (al CREAR); al editar se muestran todos de una vez, para no dejar
                    inaccesible el campo de una OE existente que aún no lo tenía capturado.
                    Producto y Duración van en la misma fila (petición del usuario).
                    ADR-169: ambos salen del catálogo Producto Duración. */}
                {(isEdit || estacionId) && (
                  <div className="r2" style={{ marginTop: 10 }}>
                    <div>
                      <div className="fl fl-required">
                        Producto{" "}
                        <span style={{ color: "var(--text3)", fontWeight: 400 }}>
                          (catálogo Producto Duración)
                        </span>
                      </div>
                      <select
                        className="fsel"
                        value={productoTarifa}
                        disabled={catalogoDuraciones.isLoading}
                        onChange={(e) => {
                          setProductoTarifa(e.target.value);
                          setDuracionSpot("");
                          // ADR-170 (petición del usuario): cambiar de producto SIEMPRE
                          // limpia la tarifa (aunque se haya editado a mano) — el efecto
                          // de abajo la vuelve a autocargar si la nueva combinación tiene
                          // una tarifa configurada en el catálogo.
                          setPrecioSpot("");
                        }}
                      >
                        <option value="">{catalogoDuraciones.isLoading ? "Cargando…" : "Selecciona…"}</option>
                        {productosDuracion.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="fl">Duración</div>
                      <select
                        className="fsel"
                        value={duracionSpot}
                        disabled={!productoTarifa || duracionesDelProducto.length === 0}
                        onChange={(e) => {
                          setDuracionSpot(e.target.value);
                          // ADR-170 (petición del usuario): cambiar de duración SIEMPRE
                          // limpia la tarifa (aunque se haya editado a mano), igual que
                          // al cambiar de producto.
                          setPrecioSpot("");
                        }}
                      >
                        <option value="">
                          {!productoTarifa
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
                )}

                <div className="r2" style={{ marginTop: 10 }}>
                  <div>
                    {/* ADR-169 (petición del usuario): basta con elegir el Producto —
                        Duración puede quedar sin capturar (sin duración real en el
                        catálogo) y aun así se puede teclear la tarifa y seguir
                        llenando el resto del formulario. */}
                    {isEdit || productoTarifa ? (
                      <>
                        <div className="fl fl-required">Tarifa por spot (MXN)</div>
                        <MoneyInput
                          style={{ maxWidth: 200 }}
                          value={precioSpot}
                          onChange={setPrecioSpot}
                        />
                        {tarifaSugerida && (
                          <div className="fv muted" style={{ fontSize: 11, marginTop: 2 }}>
                            Tarifa del catálogo: {fmtMonto(tarifaSugerida.tarifa_neta)}
                          </div>
                        )}
                        {tarifaDivergente && (
                          <>
                            <div className="fl fl-required" style={{ marginTop: 6 }}>
                              Motivo del cambio de tarifa
                            </div>
                            <input
                              className="fi"
                              placeholder="Por qué el precio no coincide con la tarifa del catálogo…"
                              value={motivoCambioTarifa}
                              onChange={(e) => setMotivoCambioTarifa(e.target.value)}
                            />
                          </>
                        )}
                      </>
                    ) : (
                      <div className="fv muted" style={{ fontSize: 12 }}>
                        Selecciona el producto para capturar la tarifa.
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="fl">Spots bonificables del afiliado</div>
                    <input
                      className="fi"
                      style={{ maxWidth: 200, fontFamily: "var(--mono)" }}
                      inputMode="numeric"
                      value={spotsBonificables}
                      onChange={(e) => setSpotsBonificables(e.target.value.replace(/\D/g, ""))}
                    />
                    {bonificablesExcede && <div className="fe">No puede exceder los spots asignados de esta OI.</div>}
                  </div>
                </div>

                <div className="fl" style={{ marginTop: 10 }}>
                  Observaciones de la estación
                </div>
                <textarea className="ftxt" rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
              </div>

              {isEdit && oe ? (
                <MaterialATransmitir ordenEstacionId={oe.id} audios={audios} onAudiosChange={setAudios} />
              ) : (
                <div className="form-card">
                  <div className="form-card-title fl-required">Material a Transmitir</div>
                  <div className="form-card-sub">
                    Elige uno o más audios (mp3/wav/ogg, máx. 15 MB) — se suben de inmediato. Si eliges solo
                    uno, se usa por default en todos los días; con dos o más, el primero es el default y
                    podrás cambiarlo por día desde "Sustitución de Material" una vez guardada la orden.
                    Es obligatorio: se necesita al menos un material subido para habilitar el calendario.
                  </div>
                  {audiosStaging.length === 0 && (
                    <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
                      Sin audios elegidos todavía.
                    </div>
                  )}
                  {audiosStaging.map((a, idx) => (
                    <div key={a.ref} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span className={`badge ${idx === 0 ? "b-teal" : "b-gray"}`} style={{ fontSize: 10 }}>
                        {idx === 0 ? "Default" : `#${idx + 1}`}
                      </span>
                      <span style={{ flex: 1, fontSize: 13 }}>{a.nombre_archivo}</span>
                      <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarAudioStaging(idx)}>
                        Quitar
                      </button>
                    </div>
                  ))}
                  <input
                    ref={audiosInputRef}
                    className="file-input"
                    type="file"
                    accept={AUDIO_ORDEN_ACCEPT}
                    disabled={subiendoAudioStaging}
                    onChange={(e) => void onElegirAudioStaging(e.target.files?.[0])}
                  />
                  {subiendoAudioStaging && (
                    <span className="fv muted" style={{ marginLeft: 8, fontSize: 11 }}>
                      Subiendo…
                    </span>
                  )}
                  {errorAudioStaging && <div className="fe">{errorAudioStaging}</div>}
                </div>
              )}

              <div className="sec">Periodo de transmisión</div>
              {!hayMaterial && (
                <div className="fv muted" style={{ fontSize: 12, marginBottom: 8 }}>
                  Sube al menos un material a transmitir (arriba) para habilitar el calendario y capturar
                  fechas.
                </div>
              )}
              <CalendarioPeriodoTransmision
                rows={periodo}
                onGenerar={(nuevas) => setPeriodo((prev) => [...prev, ...nuevas])}
                rangoCampania={{ inicio: oc.fecha_inicio_campania, fin: oc.fecha_fin_campania }}
                disabled={!hayMaterial}
              />
              <PeriodoTransmisionGrid
                rows={periodo}
                onChange={setPeriodo}
                rangoCampania={{ inicio: oc.fecha_inicio_campania, fin: oc.fecha_fin_campania }}
                audios={audiosVistaPrevia}
                onAsignarAudio={isEdit && oe ? onAsignarAudio : undefined}
                onCancelarDia={isEdit && oe ? onCancelarDia : undefined}
                disabled={!hayMaterial}
                // ADR-133 (petición del usuario): antes solo se permitía en el ALTA — al
                // editar, una fila agregada con "+ Agregar día" (sin `orden_estacion_dia_id`
                // real todavía) no ofrecía "Sustitución de Material". La selección local
                // ahora sí sobrevive al guardar (ver `ordenEstacionUpdateToApi`).
                permiteAsignacionLocal
              />
              {errorCancelarDia && <div className="fe">{errorCancelarDia}</div>}
            </>
          )}
        </div>

        <div>
          {oc && (
            <>
              {balance && <SpotBalanceBar balance={balance} />}
              <div className="info-panel">
                <div className="info-panel-title">Cálculos en vivo</div>
                <div className="fl">Spots en esta OI</div>
                <div className="fv mono">{totalEstaOI}</div>
                <div className="fl">Spots bonificables del afiliado</div>
                <div className="fv mono" style={{ color: "var(--red-text)" }}>{bonificablesRaw}</div>
                <div className="fl">Spots facturables</div>
                <div className="fv mono">{spotsFacturables}</div>
                <div className="fl">Importe</div>
                <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                  {fmtMonto(importe)}
                </div>
                <div className="fl">% participación OIR</div>
                <div className="fv mono">{fmtPct(pctOIR)}</div>
                <div className="fv muted" style={{ marginTop: -6, fontSize: 11 }}>
                  (tarifa cliente − tarifa estación) / tarifa cliente
                </div>
              </div>
              {errores.length > 0 && (
                <div className="info-panel" style={{ borderColor: "#F5C2C2", background: "var(--red-bg)" }}>
                  <div className="info-panel-title" style={{ color: "var(--red-text)" }}>
                    Antes de guardar
                  </div>
                  {errores.map((e) => (
                    <div key={e} className="fv" style={{ fontSize: 12, color: "var(--red-text)", marginBottom: 4 }}>
                      • {e}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {submitError && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {submitError}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={() => onCancelar(oc?.id)} disabled={submitting || subiendoAudioStaging}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-sm btn-teal"
            onClick={guardar}
            disabled={submitting || subiendoAudioStaging || !listo}
            title={listo ? undefined : errores[0]}
          >
            {subiendoAudioStaging
              ? "Subiendo material…"
              : submitting
                ? "Guardando…"
                : isEdit
                  ? "Guardar cambios"
                  : "Guardar Orden de Transmisión"}
          </button>
        </div>
      </div>
    </div>
  );
}
