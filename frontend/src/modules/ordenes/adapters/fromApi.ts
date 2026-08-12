/** Adaptadores DTO (backend real, Tanda 3) → tipos v5 (`types.ts`, los que ya consumen
 * todos los componentes/selectores de la demo). Es el ÚNICO lugar donde se reconcilian
 * las diferencias de forma entre el modelo real y el modelo v5 — nada más en el módulo
 * debería necesitar conocer la forma de los DTOs (`ordenesApiDTO.ts`).
 */

import type { Incidencia, OrdenCliente, OrdenEstacion, PeriodoTransmisionRow } from "../types";
import { estatusOCDesdeApi, estatusOEDesdeApi, tipoIncidenciaDesdeApi } from "./vocabulario";
import type {
  IncidenciaApiDTO,
  OrdenClienteApiDTO,
  OrdenClienteVoBoItemApiDTO,
  OrdenEstacionApiDTO,
  OrdenEstacionDiaApiDTO,
  VerificacionApiDTO,
} from "./ordenesApiDTO";

/** "HH:MM:SS" (backend, `datetime.time` de Python) → "HH:MM" (v5, como ya lo capturan
 * los mocks/formularios de esta demo). */
function soloHoraMinuto(hora: string): string {
  return hora.slice(0, 5);
}

export function ordenClienteFromApi(
  dto: OrdenClienteApiDTO,
  voboItems: OrdenClienteVoBoItemApiDTO[],
): OrdenCliente {
  const documentosFaltantes: ("odc_cerrada" | "carta_conciliacion")[] = [];
  if (dto.cierre_sin_odc_cerrada) documentosFaltantes.push("odc_cerrada");
  if (dto.cierre_sin_carta_conciliacion) documentosFaltantes.push("carta_conciliacion");

  return {
    id: dto.orden_id,
    folio_orden: dto.folio_orden,
    numero_orden_cliente: dto.numero_orden_cliente,
    fecha_venta: dto.fecha_venta,
    empresa_facturadora_id: dto.empresa_facturadora_id,
    vendedor_principal_id: dto.vendedor_principal_id,
    vendedor_secundario_id: dto.vendedor_secundario_id,
    anunciante_id: dto.anunciante_id,
    agencia_id: dto.agencia_id,
    contrato_id: dto.contrato_id,
    marca_id: dto.marca_id,
    producto: dto.producto ?? "",
    categoria_id: dto.categoria_id,
    direccion_facturacion: dto.direccion_facturacion ?? "",
    facturacion_directa_cliente: dto.facturacion_directa_cliente,
    afiliado_factura_directo_al_cliente: dto.afiliado_factura_directo_al_cliente,
    fecha_inicio_campania: dto.fecha_inicio_campania,
    fecha_fin_campania: dto.fecha_fin_campania,
    duracion_spot: dto.duracion_spot,
    total_spots: dto.total_spots,
    precio_unitario: Number(dto.precio_unitario),
    porcentaje_comision_vendedor_principal_snap:
      dto.porcentaje_comision_vendedor_principal_snap != null
        ? Number(dto.porcentaje_comision_vendedor_principal_snap)
        : null,
    porcentaje_comision_vendedor_secundario_snap:
      dto.porcentaje_comision_vendedor_secundario_snap != null
        ? Number(dto.porcentaje_comision_vendedor_secundario_snap)
        : null,
    porcentaje_comision_agencia_snap:
      dto.porcentaje_comision_agencia_snap != null
        ? Number(dto.porcentaje_comision_agencia_snap)
        : null,
    observaciones_predefinidas: dto.observaciones_predefinidas ?? "",
    observaciones_libres: dto.observaciones_libres ?? "",
    revision_checklist: Object.fromEntries(voboItems.map((v) => [v.item_clave, v.completado])),
    estatus_orden: estatusOCDesdeApi(dto.estatus_orden),
    estatus_pago_afiliado: dto.estatus_pago_afiliado as OrdenCliente["estatus_pago_afiliado"],
    estatus_pago_agencia: dto.estatus_pago_agencia as OrdenCliente["estatus_pago_agencia"],
    // Sin equivalente real todavía (no están en la spec BD v2 ni en el schema Tanda 3):
    odc_pdf_ref: null,
    audio_spot_ref: null,
    odc_cerrada_ref: dto.odc_cerrada_ref,
    carta_conciliacion_ref: dto.carta_conciliacion_ref,
    documentos_cierre_faltantes: documentosFaltantes,
    // El backend liga `created_by` a un Usuario real (UUID), no al username legible del
    // vendedor que usa la demo — se muestra el UUID hasta que F5 resuelva usuarios.
    created_by: dto.created_by,
    created_at: dto.created_at.slice(0, 10),
    fecha_cierre: dto.fecha_cierre,
    updated_at: dto.updated_at ? dto.updated_at.slice(0, 10) : null,
  };
}

export function ordenEstacionFromApi(
  dto: OrdenEstacionApiDTO,
  dias: OrdenEstacionDiaApiDTO[],
  verificaciones: VerificacionApiDTO[],
): OrdenEstacion {
  const diasOrdenados = [...dias].sort((a, b) =>
    a.fecha_transmision.localeCompare(b.fecha_transmision),
  );

  const periodo_transmision: PeriodoTransmisionRow[] = diasOrdenados.map((d) => ({
    fecha: d.fecha_transmision,
    hora_inicio: soloHoraMinuto(d.hora_inicio),
    hora_termino: soloHoraMinuto(d.hora_fin),
    spots_diarios: d.spots_asignados,
  }));

  // Solo los días con un valor CONFIRMADO que difiere del asignado (v5 solo guarda
  // overrides, no la serie completa — ver `programadoEfectivo` en selectors.ts).
  const horarios_programados: PeriodoTransmisionRow[] = diasOrdenados
    .filter((d) => d.spots_programados != null && d.spots_programados !== d.spots_asignados)
    .map((d) => ({
      fecha: d.fecha_transmision,
      hora_inicio: soloHoraMinuto(d.hora_inicio),
      hora_termino: soloHoraMinuto(d.hora_fin),
      spots_diarios: d.spots_programados as number,
    }));

  const verificacionPorDia = new Map(verificaciones.map((v) => [v.orden_estacion_dia_id, v]));
  const horarios_reales: PeriodoTransmisionRow[] = [];
  for (const d of diasOrdenados) {
    const verificacion = verificacionPorDia.get(d.orden_estacion_dia_id);
    if (!verificacion) continue;
    const programadoEfectivo = d.spots_programados ?? d.spots_asignados;
    if (verificacion.spots_verificados !== programadoEfectivo) {
      horarios_reales.push({
        fecha: d.fecha_transmision,
        hora_inicio: soloHoraMinuto(d.hora_inicio),
        hora_termino: soloHoraMinuto(d.hora_fin),
        spots_diarios: verificacion.spots_verificados,
      });
    }
  }

  return {
    id: dto.orden_estacion_id,
    folio_orden_interna: dto.folio_orden_estacion,
    orden_id: dto.orden_id,
    estacion_id: dto.estacion_id,
    plaza_id: dto.plaza_id,
    precio_spot: Number(dto.precio_spot),
    porcentaje_participacion_oir: Number(dto.porcentaje_participacion_oir),
    periodo_transmision,
    horarios_programados: horarios_programados.length > 0 ? horarios_programados : undefined,
    horarios_reales: horarios_reales.length > 0 ? horarios_reales : undefined,
    testigos_url: dto.testigos_url,
    testigos_ubicacion_alterna: dto.testigos_ubicacion_alterna,
    notas_transmision: dto.notas_transmision,
    reporte_programados_ref: dto.reporte_programados_ref,
    reporte_reales_ref: dto.reporte_reales_ref,
    observaciones_estacion: dto.observaciones_estacion ?? undefined,
    estatus: estatusOEDesdeApi(dto.estatus),
    created_at: dto.created_at.slice(0, 10),
    updated_at: dto.updated_at ? dto.updated_at.slice(0, 10) : null,
  };
}

export function incidenciaFromApi(dto: IncidenciaApiDTO): Incidencia {
  return {
    id: dto.incidencia_id,
    orden_interna_id: dto.orden_estacion_id,
    tipo: tipoIncidenciaDesdeApi(dto.tipo_incidencia),
    fecha_transmision: dto.fecha_incidencia,
    spots_asignados: dto.spots_ordenados,
    spots_reales: dto.spots_ejecutados,
    diferencia: dto.diferencia_spots,
    monto_ajuste: dto.monto_ajuste != null ? Number(dto.monto_ajuste) : 0,
    nota_excepcion: dto.descripcion_incidencia ?? "",
    created_at: dto.fecha_incidencia,
  };
}
