/** Mapeo de vocabulario spec BD v2 (backend real) → "v5" (prototipo/demo, `types.ts`).
 *
 * El backend (Tanda 3) usa el vocabulario EXACTO de la spec; esta demo fue construida
 * antes de leer la spec y usa un vocabulario "v5" propio con más granularidad en algunos
 * puntos y menos en otros. Este archivo es el ÚNICO lugar donde ambos vocabularios se
 * tocan — nada más en el módulo conoce el vocabulario spec.
 *
 * Direcciones distintas a propósito:
 * - El backend siembra v5→spec (`seed_dev.py`, `MAPEO_ESTATUS_OC`/`MAPEO_ESTATUS_OE`).
 * - Aquí hacemos el camino INVERSO (spec→v5) para pintar datos reales con los mismos
 *   componentes que ya pintan los mocks — es una relación N:1 en ambos sentidos, así que
 *   NO es la función inversa matemática; ver cada mapeo para el porqué de cada casilla.
 */

import type { EstadoOC, EstadoOI } from "../types";

/** `OrdenCliente.estatus_orden` (spec, 8 valores) → `EstadoOC` (v5, 8 valores, pero
 * agrupados distinto).
 *
 * - `recibida`/`capturada`/`orden_cerrada`/`cobrada`/`cancelada`: 1:1, sin ambigüedad.
 * - `en_transmision` y `en_verificacion` (spec) colapsan en el ÚNICO valor `orden_interna`
 *   (v5): la demo no distingue esas dos fases, solo sabe "está en gestión de estaciones".
 * - `facturada` (spec) es AMBIGUO: v5 lo distingue en `facturada_archivo_plano` vs.
 *   `facturada_timbrada`, distinción que la spec no guarda. Se resuelve siempre a
 *   `facturada_timbrada` (decisión explícita, Tanda 4): asume el sub-estado más avanzado;
 *   no bloquea nada visualmente y queda documentado como limitación conocida hasta que
 *   F2 (Facturación) exista en el backend real y aporte el dato que falta.
 */
const MAPA_ESTATUS_OC: Record<string, EstadoOC> = {
  recibida: "orden_cliente_sin_vobo",
  capturada: "orden_cliente_con_vobo",
  en_transmision: "orden_interna",
  en_verificacion: "orden_interna",
  orden_cerrada: "orden_cerrada",
  facturada: "facturada_timbrada",
  cobrada: "cobrada",
  cancelada: "cancelada",
};

export function estatusOCDesdeApi(estatusSpec: string): EstadoOC {
  return MAPA_ESTATUS_OC[estatusSpec] ?? "orden_cliente_sin_vobo";
}

/** `OrdenEstacion.estatus` (spec, 6 valores) → `EstadoOI` (v5, solo 3 valores: la demo
 * modela nada más el tramo "asignada → programada → reales conciliados").
 *
 * - `asignada`/`en_transmision`/`cerrada`: 1:1 con el mapeo inverso del que siembra el
 *   backend (`asignada_afiliado`/`programados_conciliados`/`reales_conciliados`).
 * - `borrador`/`en_revision`/`cancelada` (spec) NO TIENEN equivalente v5 — la demo nunca
 *   modeló un estado "todavía sin asignar" ni "cancelada" para una OE. Son valores que
 *   los datos sembrados (Tanda 2) nunca usan, pero se cubren defensivamente por si la
 *   Tanda 5 los introduce: se mapean al sub-estado v5 más cercano en el flujo
 *   (`borrador`/`en_revision` → el que precede; `cancelada` → `asignada_afiliado`, sin
 *   badge propio) — ES UNA LIMITACIÓN CONOCIDA, no una lectura fiel; revisar cuando F1
 *   escritura (Tanda 5) module el ciclo completo de la OE en el frontend.
 */
const MAPA_ESTATUS_OE: Record<string, EstadoOI> = {
  borrador: "asignada_afiliado",
  asignada: "asignada_afiliado",
  en_transmision: "programados_conciliados",
  en_revision: "programados_conciliados",
  cerrada: "reales_conciliados",
  cancelada: "asignada_afiliado",
};

export function estatusOEDesdeApi(estatusSpec: string): EstadoOI {
  return MAPA_ESTATUS_OE[estatusSpec] ?? "asignada_afiliado";
}

/** `Incidencia.tipo_incidencia` (spec, 5 valores) → v5 (`bonificacion`/`descuento`, 2
 * valores). Inverso exacto del `MAPEO_TIPO_INCIDENCIA` del backend para `faltante`/
 * `excedente` (las 2 únicas que la generación automática puede producir hoy). Los otros 3
 * (`cambio_horario`/`cambio_fecha`/`spot_no_emitido`) son de ALTA MANUAL (no implementada
 * todavía ni en backend ni en esta demo — ver docstring de `incidencia.py`): no pueden
 * aparecer en los datos de la Tanda 3, pero se cubren defensivamente igual. */
const MAPA_TIPO_INCIDENCIA: Record<string, "bonificacion" | "descuento"> = {
  faltante: "descuento",
  excedente: "bonificacion",
  cambio_horario: "descuento",
  cambio_fecha: "descuento",
  spot_no_emitido: "descuento",
};

export function tipoIncidenciaDesdeApi(tipoSpec: string): "bonificacion" | "descuento" {
  return MAPA_TIPO_INCIDENCIA[tipoSpec] ?? "descuento";
}
