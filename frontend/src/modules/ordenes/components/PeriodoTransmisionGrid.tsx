/** Constructor/editor de `periodo_transmision`: filas de fecha + horario de transmisión
 * + spots del día, con día de la semana visible, agregar/quitar fila, y validación de que
 * la fecha cae dentro del rango de la campaña. Se reutiliza en el alta de OrdenEstacion
 * (Tanda 3) y, en modo de solo lectura, en el detalle.
 *
 * ADR-107/ADR-108 (petición del usuario): "Hora inicio"/"Hora término" pasaron de 2
 * columnas Y 2 valores separados a una sola columna "Horario de transmisión" con UN
 * solo `<input type="time">`. **REVERTIDO en ADR-185** (ver abajo).
 *
 * ADR-127 (petición del usuario): cada spot de un día pasó a ser su PROPIA fila real en
 * `OrdenEstacionDia` (antes, una sola fila por día con `spots_diarios = N`) — SIGUE
 * IGUAL por dentro (`rows`/`periodo_transmision` nunca cambió de forma): lo que cambia en
 * ADR-185 es solo CÓMO SE VEN agrupadas en esta pantalla.
 *
 * ADR-185 (petición del usuario, corrige un primer intento que sí se probó en vivo): la
 * grid vuelve a mostrar **UN SOLO RENGLÓN POR FECHA** (como antes de ADR-127), con sus
 * columnas "Hora Inicio"/"Hora Fin" editables — pero por dentro, cada fecha puede seguir
 * teniendo VARIAS filas reales (una por spot, cada una con su propio `hora_inicio` real,
 * generado por `repartirHoras` — ver `CalendarioPeriodoTransmision.tsx`). El renglón
 * visible de una fecha es un AGREGADO: Hora Inicio = la más temprana del grupo, Hora Fin
 * = la más tardía, Spots = la suma. Editar cualquiera de esos 3 campos REGENERA las
 * filas reales de esa fecha con `repartirHoras` (mismo criterio que el generador) — las
 * filas viejas de esa fecha se reemplazan por las nuevas (pierden su
 * `orden_estacion_dia_id`, igual que "Quitar día" + "+ Agregar día" ya hacían). Por qué
 * esto es seguro: "Capturar reales" (`RealesForm.tsx`), la carga del layout CSV
 * (`_parsear_layout_reales_csv`, ADR-174b) y el backend NO cambian — todos siguen
 * leyendo/escribiendo exactamente el mismo arreglo de filas reales de siempre, 1 por
 * spot; esta pantalla es la ÚNICA que ahora las agrupa visualmente.
 * "Cancelar transmisión" (antes por fila) ahora aplica a TODO el grupo de la fecha a la
 * vez (decisión explícita: ya no se puede cancelar un spot suelto dentro del día desde
 * esta pantalla). "Material a Transmitir" SÍ volvió a ser por spot — ver ADR-187.
 *
 * Editar "Spots" SIN que "Hora Inicio" difiera de "Hora Fin" (el default histórico de
 * "+ Agregar día" — ambas nacen iguales) NO reparte: deja un solo renglón con
 * `spots_diarios` tal cual, igual que el comportamiento de siempre para un día agregado
 * a mano (conserva su `orden_estacion_dia_id` si el grupo ya era de 1 sola fila). Repartir
 * con `repartirHoras` solo aplica cuando Hora Inicio y Hora Fin son distintas — ahí sí
 * hay un rango real que llenar con 2+ spots.
 *
 * ADR-103/ADR-107: columna "Material a Transmitir" — solo aparece cuando el padre pasa
 * `audios` (edición o alta, en ambas se arma la lista de materiales ya subidos/en
 * staging). **REVERTIDO en ADR-187** el concepto de "un solo default para todos los
 * días" (ver abajo).
 *
 * ADR-111: en el ALTA (antes de que exista `orden_estacion_dia_id` real), reasignar
 * materiales también está disponible — el padre pasa `permiteAsignacionLocal` y el
 * cambio se guarda en la fila misma (`orden_estacion_audio_id`, sin llamar a ningún
 * endpoint), viajando con el resto del día al hacer "Guardar" (`toApi.ts` lo manda como
 * `audio_staging_ref`, resuelto por el backend contra los audios de la misma solicitud).
 *
 * ADR-187 (petición del usuario) — ya NO hay un solo "material default" compartido por
 * todos los días: cada SPOT (cada fila real) recibe su propio material por POSICIÓN
 * dentro del día, en el orden en que se subieron los materiales — "spot 1 → material 1,
 * spot 2 → material 2…", repitiendo cíclicamente si hay menos materiales que spots
 * (`asignarPorPosicion`, `CalendarioPeriodoTransmision.tsx`). La columna "Material a
 * Transmitir" pasa de "1 nombre + botón de sustitución" a un MULTI-SELECT
 * (`CheckboxMultiSelect`) por fecha: muestra los materiales que YA están asignados a
 * esa fecha (deduplicados, en el orden en que aparecen entre sus filas) y permite
 * agregar/quitar — la selección se reparte 1 a 1 (cíclico) sobre las filas reales del
 * grupo, en el MISMO orden en que se eligieron. Validación: no se puede seleccionar más
 * materiales que SPOTS tiene ese renglón (el multi-select deja de ofrecer opciones
 * nuevas al llegar al tope) — no cuántas filas reales existen hoy, ver ADR-189.
 *
 * ADR-189 (corrige un bug real reportado en vivo): un día sin rango ("+ Agregar día",
 * Hora Inicio === Hora Fin) nace con 1 sola fila real aunque sus spots sean varios
 * (ADR-185/186) — el usuario quiso 2 materiales para un día así de 2 spots y el tope,
 * antes ligado a `grupo.filas.length` (1), se lo impedía. Ahora, al elegir MÁS
 * materiales distintos de los que hay filas, el grupo se EXPANDE a `grupo.spots` filas
 * (pierden su `orden_estacion_dia_id`, mismo efecto que editar Hora Inicio/Hora
 * Fin/Spots) — con un rango real reparte con `repartirHoras`; sin rango, con
 * `dividirPuntoEnFilas` (separa 1 minuto por fila, criterio histórico de ADR-127, solo
 * para que cada una tenga su propio `hora_inicio`).
 *
 * ADR-104: "Cancelar transmisión" de una fecha — solo aparece cuando el padre pasa
 * `onCancelarDia` (mismo criterio que el audio: requiere al menos un
 * `orden_estacion_dia_id` real en el grupo). Captura el motivo en un campo de texto en
 * línea (no `window.prompt`, para mantener el patrón del resto de la app — p.ej. "Motivo
 * del cambio de tarifa"). Una fecha ya cancelada se muestra atenuada, de solo lectura,
 * sin botón de quitar/cancelar.
 */

import { useState, type CSSProperties } from "react";

import { CheckboxMultiSelect, type OpcionBuscable } from "@/shared/ui";

import { diaDeSemana } from "../format";
import type { OrdenEstacionAudio, PeriodoTransmisionRow } from "../types";
import { asignarPorPosicion, dividirPuntoEnFilas, repartirHoras } from "./CalendarioPeriodoTransmision";

// Tamaño fijo (no solo mínimo) + centrado por flex: así los íconos de acción (Quitar
// día, Cancelar transmisión) miden EXACTO lo mismo por fuera, sin importar que sus
// glifos (✕ 🚫) tengan anchos naturales distintos.
const ICON_BTN_STYLE: CSSProperties = {
  width: 44,
  height: 44,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 0,
};
// El emoji a color (🚫) se dibuja más grande que un glifo de texto (✕) al MISMO
// font-size (petición del usuario: que se vean del mismo tamaño) — se compensa con un
// font-size menor solo para el emoji, no para la X.
const ICON_BTN_STYLE_EMOJI: CSSProperties = { ...ICON_BTN_STYLE, fontSize: 14 };
const ICON_BTN_STYLE_X: CSSProperties = { ...ICON_BTN_STYLE, fontSize: 20 };

/** ADR-134: mismo helper que `CalendarioPeriodoTransmision.tsx` — separa por minutos un
 * horario para no chocar con `uq_orden_estacion_dia_oe_fecha_hora` (fecha + hora_inicio). */
function sumarMinutos(hora: string, minutos: number): string {
  const [h, m] = hora.split(":").map(Number);
  const total = (((h * 60 + m + minutos) % 1440) + 1440) % 1440;
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

export function problemasDeFila(row: PeriodoTransmisionRow, rango: { inicio: string; fin: string }): string[] {
  const problemas: string[] = [];
  if (!row.fecha) {
    problemas.push("Falta la fecha.");
  } else if (rango.inicio && rango.fin && (row.fecha < rango.inicio || row.fecha > rango.fin)) {
    problemas.push("La fecha cae fuera del rango de la campaña.");
  }
  if (!row.hora_inicio || !row.hora_termino) {
    problemas.push("Falta el horario de transmisión.");
  } else if (row.hora_termino < row.hora_inicio) {
    problemas.push('"Hora Fin" no puede ser anterior a "Hora Inicio".');
  }
  if (!row.spots_diarios || row.spots_diarios <= 0) {
    problemas.push("Los spots del día deben ser mayores a 0.");
  }
  return problemas;
}

/** ADR-185: agregado de TODAS las filas reales de una misma fecha, para mostrarlas como
 * UN solo renglón editable. `indices` son las posiciones de esas filas dentro del
 * arreglo `rows` original — se usan para reemplazarlas al regenerar el grupo. Exportado
 * (ADR-196): `OrdenEstacionDetailPanel.tsx` lo reusa para mostrar el período de
 * transmisión agrupado por fecha en el detalle de solo lectura, igual que esta grid. */
export interface GrupoFecha {
  fecha: string;
  indices: number[];
  filas: PeriodoTransmisionRow[];
  horaInicio: string;
  horaFin: string;
  spots: number;
  cancelada: boolean;
}

export function agruparPorFecha(rows: PeriodoTransmisionRow[]): GrupoFecha[] {
  const porFecha = new Map<string, number[]>();
  rows.forEach((r, i) => {
    const indices = porFecha.get(r.fecha) ?? [];
    indices.push(i);
    porFecha.set(r.fecha, indices);
  });
  return [...porFecha.entries()]
    .map(([fecha, indices]) => {
      const filas = indices.map((i) => rows[i]);
      const cancelada = filas.every((f) => f.cancelada);
      // Si TODAS están canceladas no hay "activas" que agregar — se usan todas para no
      // quedarse sin horario/spots que mostrar.
      const base = cancelada ? filas : filas.filter((f) => !f.cancelada);
      const horaInicio = base.reduce((min, f) => (f.hora_inicio < min ? f.hora_inicio : min), base[0].hora_inicio);
      const horaFin = base.reduce((max, f) => (f.hora_termino > max ? f.hora_termino : max), base[0].hora_termino);
      const spots = base.reduce((s, f) => s + (f.spots_diarios || 0), 0);
      return { fecha, indices, filas, horaInicio, horaFin, spots, cancelada };
    })
    .sort((a, b) => a.fecha.localeCompare(b.fecha));
}

interface PeriodoTransmisionGridProps {
  rows: PeriodoTransmisionRow[];
  onChange: (rows: PeriodoTransmisionRow[]) => void;
  rangoCampania: { inicio: string; fin: string };
  disabled?: boolean;
  /** ADR-103: lista de audios disponibles, en el orden en que se subieron (ADR-187: ese
   *  orden define qué spot le toca a cada uno) — su sola presencia decide si se muestra
   *  la columna "Material a Transmitir". */
  audios?: OrdenEstacionAudio[];
  /** Asigna (o quita, con `null`) el audio de UN día real — llamada inmediata al backend
   *  (endpoint dedicado, `PUT .../dias/{id}/audio`), no se acumula con "Guardar". ADR-187:
   *  la pantalla la llama una vez POR CADA fila real cuyo material haya cambiado al
   *  editar el multi-select de su grupo. */
  onAsignarAudio?: (diaId: string, audioId: string | null) => void;
  /** ADR-104: cancela un día puntual — llamada inmediata al backend (endpoint dedicado,
   *  `POST .../dias/{id}/cancelar`), no se acumula con "Guardar". Su sola presencia decide
   *  si se muestra el botón "Cancelar transmisión" (requiere la OE ya creada, igual que
   *  `onAsignarAudio`). ADR-185: la pantalla la llama una vez por cada id real del grupo. */
  onCancelarDia?: (diaId: string, motivo: string) => void;
  /** ADR-111: habilita reasignar materiales también para filas SIN
   *  `orden_estacion_dia_id` (recién generadas, antes de guardar) — el cambio se guarda
   *  localmente en la fila (`onChange`), no llama a `onAsignarAudio`. */
  permiteAsignacionLocal?: boolean;
}

export function PeriodoTransmisionGrid({
  rows,
  onChange,
  rangoCampania,
  disabled,
  audios,
  onAsignarAudio,
  onCancelarDia,
  permiteAsignacionLocal,
}: PeriodoTransmisionGridProps) {
  // ADR-108: la columna aparece con solo pasar `audios` (aunque venga vacía, p.ej. al
  // CREAR una OE nueva, antes de poder subir ningún material) — así el usuario ve la
  // columna desde el principio, en vez de que aparezca "de la nada" hasta que edita.
  // `onAsignarAudio` sigue siendo lo que habilita el botón de sustituir (aparte).
  const mostrarColumnaAudio = audios != null;
  // ADR-104: un día cancelado no cuenta para el total (libera su cupo, igual que en el
  // balance de la OC — ver `oiTotalSpots`, selectors.ts).
  const totalSpots = rows.reduce((s, r) => (r.cancelada ? s : s + (r.spots_diarios || 0)), 0);
  const [cancelandoFecha, setCancelandoFecha] = useState<string | null>(null);
  const [motivoCancelacion, setMotivoCancelacion] = useState("");

  const grupos = agruparPorFecha(rows);
  // ADR-187: opciones del multi-select de "Material a Transmitir" — en el orden en que
  // se subieron (ese orden es justo lo que define la posición de cada spot).
  const opcionesAudio: OpcionBuscable[] = (audios ?? []).map((a) => ({ value: a.id, label: a.nombre_archivo }));

  const confirmarCancelacion = (grupo: GrupoFecha) => {
    if (!motivoCancelacion.trim()) return;
    grupo.filas.forEach((f) => {
      if (f.orden_estacion_dia_id) onCancelarDia?.(f.orden_estacion_dia_id, motivoCancelacion.trim());
    });
    setCancelandoFecha(null);
    setMotivoCancelacion("");
  };

  /** ADR-187: materiales ASIGNADOS de verdad a este grupo (fecha) — deduplicados, en el
   *  orden en que aparecen entre las filas reales del grupo (fila 0, fila 1, …). Puede
   *  venir vacío (grupo sin ningún material todavía) — a propósito: es el estado que
   *  alimenta el multi-select EDITABLE, así que debe reflejar el valor real (incluida
   *  una selección intencionalmente vacía), nunca un valor inventado. */
  const materialesAsignados = (grupo: GrupoFecha): string[] => {
    const asignados = grupo.filas.map((f) => f.orden_estacion_audio_id).filter((id): id is string => id != null);
    return [...new Set(asignados)];
  };

  /** ADR-187: para la vista de SOLO LECTURA (sin id real todavía y sin alta en curso) —
   *  si el grupo nunca se tocó, calcula la vista previa por posición (igual que al
   *  generar), solo para que se vea de inmediato qué le tocaría; nunca se usa para
   *  alimentar el multi-select editable (ver `materialesAsignados`). */
  const materialesConVistaPrevia = (grupo: GrupoFecha): string[] => {
    if (!audios || audios.length === 0) return [];
    const asignados = materialesAsignados(grupo);
    if (asignados.length > 0) return asignados;
    const vistaPrevia = asignarPorPosicion(
      audios.map((a) => a.id),
      grupo.filas.length,
    ).filter((id): id is string => id != null);
    return [...new Set(vistaPrevia)];
  };

  /** ADR-187/189: aplica la selección del multi-select al grupo. El tope real son los
   *  SPOTS capturados (`grupo.spots`), no cuántas filas reales existen hoy
   *  (`grupo.filas.length`) — un día sin rango ("+ Agregar día") nace con 1 sola fila
   *  aunque sus spots sean varios (ADR-185/186). Dos casos:
   *  - Si lo elegido cabe en las filas YA existentes: se reparte 1 a 1 (cíclico) sobre
   *    ELLAS, sin tocar su cantidad — con id real, llama a `onAsignarAudio` por cada
   *    fila que cambió de valor (nunca a la que ya tenía ese mismo id); sin id real
   *    (alta), actualiza el estado local.
   *  - Si se necesitan MÁS materiales distintos que filas existen (el bug reportado:
   *    2 spots, 1 sola fila, querían 2 materiales): expande el grupo a `grupo.spots`
   *    filas — con un rango real reparte con `repartirHoras`; sin rango (un PUNTO,
   *    Hora Inicio === Hora Fin) usa `dividirPuntoEnFilas` (separa 1 minuto por fila,
   *    criterio histórico de ADR-127, solo para darle a cada una su propio
   *    `hora_inicio`). Mismo efecto que editar Hora Inicio/Hora Fin/Spots: las filas
   *    viejas pierden su `orden_estacion_dia_id` (ADR-185, ya aceptado). */
  const aplicarSeleccionMateriales = (grupo: GrupoFecha, seleccion: string[]) => {
    if (seleccion.length > grupo.spots) return; // el multi-select ya no debería ofrecer más
    if (seleccion.length <= grupo.filas.length) {
      const idsPorFila = asignarPorPosicion(seleccion, grupo.filas.length);
      if (grupo.filas.some((f) => f.orden_estacion_dia_id != null)) {
        grupo.filas.forEach((f, i) => {
          if (f.orden_estacion_dia_id && f.orden_estacion_audio_id !== idsPorFila[i]) {
            onAsignarAudio?.(f.orden_estacion_dia_id, idsPorFila[i]);
          }
        });
        return;
      }
      const indicesSet = new Set(grupo.indices);
      let i = 0;
      onChange(rows.map((r, idx) => (indicesSet.has(idx) ? { ...r, orden_estacion_audio_id: idsPorFila[i++] } : r)));
      return;
    }
    const rangos =
      grupo.horaInicio === grupo.horaFin
        ? dividirPuntoEnFilas(grupo.horaInicio, grupo.spots)
        : repartirHoras(grupo.horaInicio, grupo.horaFin, grupo.spots);
    const idsPorFila = asignarPorPosicion(seleccion, grupo.spots);
    const nuevasFilas: PeriodoTransmisionRow[] = rangos.map((r, i) => ({
      fecha: grupo.fecha,
      hora_inicio: r.hora_inicio,
      hora_termino: r.hora_termino,
      spots_diarios: 1,
      orden_estacion_audio_id: idsPorFila[i],
    }));
    reemplazarGrupo(grupo, nuevasFilas);
  };

  /** ADR-185: reemplaza TODAS las filas reales de `grupo.fecha` por `nuevasFilas` — las
   *  viejas pierden su `orden_estacion_dia_id` (mismo efecto neto que "Quitar día" +
   *  "+ Agregar día", ya soportado sin cambios de backend). */
  const reemplazarGrupo = (grupo: GrupoFecha, nuevasFilas: PeriodoTransmisionRow[]) => {
    const indicesSet = new Set(grupo.indices);
    onChange([...rows.filter((_, i) => !indicesSet.has(i)), ...nuevasFilas]);
  };

  const actualizarFecha = (grupo: GrupoFecha, nuevaFecha: string) => {
    const indicesSet = new Set(grupo.indices);
    onChange(rows.map((r, i) => (indicesSet.has(i) ? { ...r, fecha: nuevaFecha } : r)));
  };

  /** ADR-185: regenera las filas reales del grupo con `repartirHoras` — mismo criterio
   *  que el generador por calendario (con 1 solo spot conserva el rango genuino, con 2+
   *  reparte un punto por fila). ADR-187: conserva los materiales YA asignados al
   *  grupo, repartidos de nuevo (cíclico) sobre el nuevo número de filas — así cambiar
   *  Hora Inicio/Hora Fin/Spots no resetea lo que el usuario eligió en "Material a
   *  Transmitir".
   *
   *  Sin rango real (Hora Inicio === Hora Fin, el default histórico de "+ Agregar día"):
   *  NO reparte — deja un solo renglón con `spots_diarios = spots` tal cual, igual que
   *  antes de ADR-127/185 (conserva su `orden_estacion_dia_id` si el grupo ya era de 1
   *  sola fila, para no perderlo por un simple cambio de conteo). Repartir solo tiene
   *  sentido cuando el usuario capturó un rango de verdad. */
  const actualizarRango = (
    grupo: GrupoFecha,
    cambios: Partial<{ horaInicio: string; horaFin: string; spots: number }>,
  ) => {
    const horaInicio = cambios.horaInicio ?? grupo.horaInicio;
    const horaFin = cambios.horaFin ?? grupo.horaFin;
    const spots = cambios.spots ?? grupo.spots;
    if (spots <= 0) return; // evita borrar el grupo por un valor transitorio inválido
    const materiales = materialesAsignados(grupo);
    if (horaInicio === horaFin) {
      const base = grupo.filas.length === 1 ? grupo.filas[0] : undefined;
      reemplazarGrupo(grupo, [
        {
          ...base,
          fecha: grupo.fecha,
          hora_inicio: horaInicio,
          hora_termino: horaFin,
          spots_diarios: spots,
          orden_estacion_audio_id: asignarPorPosicion(materiales, 1)[0],
        },
      ]);
      return;
    }
    const rangos = repartirHoras(horaInicio, horaFin, spots);
    const idsAudio = asignarPorPosicion(materiales, rangos.length);
    const nuevasFilas: PeriodoTransmisionRow[] = rangos.map((r, i) => ({
      fecha: grupo.fecha,
      hora_inicio: r.hora_inicio,
      hora_termino: r.hora_termino,
      spots_diarios: 1,
      orden_estacion_audio_id: idsAudio[i],
    }));
    reemplazarGrupo(grupo, nuevasFilas);
  };

  const quitarGrupo = (grupo: GrupoFecha) => {
    const indicesSet = new Set(grupo.indices);
    onChange(rows.filter((_, i) => !indicesSet.has(i)));
  };

  const agregarFila = () => {
    const ultima = rows[rows.length - 1];
    let siguienteFecha = rangoCampania.inicio;
    if (ultima?.fecha) {
      const d = new Date(ultima.fecha);
      d.setDate(d.getDate() + 1);
      siguienteFecha = d.toISOString().slice(0, 10);
      if (rangoCampania.fin && siguienteFecha > rangoCampania.fin) siguienteFecha = rangoCampania.fin;
    }
    // ADR-134 (corrige un bug real): si la fecha calculada ya tiene una fila con el
    // mismo horario — p.ej. la última fila ya estaba en el último día de la campaña, así
    // que "+1 día" se topó con el fin y se quedó en la MISMA fecha — guardar tronaba con
    // el unique constraint `(fecha, hora_inicio)` (normal tener 2+ filas la misma fecha
    // desde ADR-127). Se corre el horario +1 minuto hasta encontrar uno libre para esa
    // fecha, mismo criterio que el generador por calendario.
    let horario = ultima?.hora_inicio ?? "07:00";
    const horariosOcupados = new Set(
      rows.filter((r) => r.fecha === siguienteFecha).map((r) => r.hora_inicio),
    );
    while (horariosOcupados.has(horario)) {
      horario = sumarMinutos(horario, 1);
    }
    // ADR-187: a esta fila le toca el material de SU posición dentro del día (cuántas
    // filas de esa misma fecha ya existen antes de agregar esta).
    const posicion = rows.filter((r) => r.fecha === siguienteFecha).length;
    const audioId = audios && audios.length > 0 ? audios[posicion % audios.length].id : null;
    onChange([
      ...rows,
      {
        fecha: siguienteFecha,
        hora_inicio: horario,
        hora_termino: horario,
        spots_diarios: 1,
        orden_estacion_audio_id: audioId,
      },
    ]);
  };

  return (
    <div>
      <table className="cat-table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th>Día</th>
            <th>Fecha</th>
            <th>Hora Inicio</th>
            <th>Hora Fin</th>
            <th className="td-center" style={{ width: 70, minWidth: 70 }}>
              Spots
            </th>
            {mostrarColumnaAudio && <th>Material a Transmitir</th>}
            <th style={{ width: onCancelarDia ? 120 : 60, minWidth: onCancelarDia ? 120 : 60 }} />
          </tr>
        </thead>
        <tbody>
          {grupos.map((grupo) => {
            const problemas = grupo.cancelada
              ? []
              : problemasDeFila(
                  {
                    fecha: grupo.fecha,
                    hora_inicio: grupo.horaInicio,
                    hora_termino: grupo.horaFin,
                    spots_diarios: grupo.spots,
                  },
                  rangoCampania,
                );
            const tieneIdReal = grupo.filas.some((f) => f.orden_estacion_dia_id != null);
            const mostrarCancelar = onCancelarDia != null && tieneIdReal && !grupo.cancelada;
            const cancelandoEsteGrupo = cancelandoFecha === grupo.fecha;
            return (
              <tr key={grupo.fecha} style={grupo.cancelada ? { opacity: 0.55 } : undefined}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(grupo.fecha)}
                </td>
                <td>
                  <input
                    type="date"
                    className="fi"
                    style={{ marginBottom: 0, borderColor: problemas.length ? "var(--red-text)" : undefined }}
                    value={grupo.fecha}
                    disabled={disabled || grupo.cancelada}
                    onChange={(e) => actualizarFecha(grupo, e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="time"
                    className="fi"
                    style={{ marginBottom: 0, borderColor: problemas.length ? "var(--red-text)" : undefined }}
                    value={grupo.horaInicio}
                    disabled={disabled || grupo.cancelada}
                    onChange={(e) => e.target.value && actualizarRango(grupo, { horaInicio: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="time"
                    className="fi"
                    style={{ marginBottom: 0, borderColor: problemas.length ? "var(--red-text)" : undefined }}
                    value={grupo.horaFin}
                    disabled={disabled || grupo.cancelada}
                    onChange={(e) => e.target.value && actualizarRango(grupo, { horaFin: e.target.value })}
                  />
                </td>
                <td className="td-center" style={{ width: 70, minWidth: 70 }}>
                  <input
                    type="number"
                    className="fi"
                    style={{
                      marginBottom: 0,
                      width: 56,
                      padding: "0 6px",
                      textAlign: "center",
                      fontFamily: "var(--mono)",
                    }}
                    value={grupo.spots}
                    disabled={disabled || grupo.cancelada}
                    onChange={(e) => {
                      const spots = Number.parseInt(e.target.value, 10);
                      if (Number.isFinite(spots) && spots > 0) actualizarRango(grupo, { spots });
                    }}
                  />
                </td>
                {mostrarColumnaAudio && (
                  <td style={{ paddingRight: 0 }}>
                    {grupo.cancelada || !audios || audios.length === 0 ? (
                      <span className="fv muted" style={{ fontSize: 11 }}>
                        —
                      </span>
                    ) : !(tieneIdReal || permiteAsignacionLocal) ? (
                      // Sin id real todavía y sin alta en curso (p.ej. detalle de solo
                      // lectura): se muestra el material que le toca por posición, pero
                      // no es editable — mismo criterio que antes (ADR-107).
                      <span style={{ fontSize: 12 }}>
                        {materialesConVistaPrevia(grupo)
                          .map((id) => audios.find((a) => a.id === id)?.nombre_archivo)
                          .filter(Boolean)
                          .join(", ") || "—"}
                      </span>
                    ) : (
                      <>
                        <CheckboxMultiSelect
                          value={materialesAsignados(grupo)}
                          onChange={(seleccion) => aplicarSeleccionMateriales(grupo, seleccion)}
                          options={opcionesAudio}
                          maxSelected={grupo.spots}
                          placeholder="Elige material…"
                          disabled={disabled}
                        />
                        {materialesAsignados(grupo).length >= grupo.spots && (
                          <div className="fv muted" style={{ fontSize: 10, marginTop: 2 }}>
                            Máximo {grupo.spots} material{grupo.spots === 1 ? "" : "es"} (spots de este día).
                          </div>
                        )}
                      </>
                    )}
                  </td>
                )}
                <td style={{ paddingLeft: 0 }}>
                  {grupo.cancelada ? (
                    <span className="fv" style={{ fontSize: 11, color: "var(--red-text)", fontWeight: 600 }}>
                      Cancelado
                    </span>
                  ) : cancelandoEsteGrupo ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input
                        type="text"
                        className="fi"
                        style={{ marginBottom: 0, fontSize: 11, width: 140 }}
                        placeholder="Motivo de la cancelación"
                        value={motivoCancelacion}
                        autoFocus
                        onChange={(e) => setMotivoCancelacion(e.target.value)}
                      />
                      <button
                        type="button"
                        className="btn btn-xs btn-danger"
                        disabled={!motivoCancelacion.trim()}
                        onClick={() => confirmarCancelacion(grupo)}
                      >
                        Confirmar
                      </button>
                      <button
                        type="button"
                        className="btn btn-xs"
                        onClick={() => {
                          setCancelandoFecha(null);
                          setMotivoCancelacion("");
                        }}
                      >
                        Cancelar
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
                      {!disabled && (
                        <button
                          type="button"
                          className="btn"
                          style={{ ...ICON_BTN_STYLE_X, color: "var(--red-text)" }}
                          onClick={() => quitarGrupo(grupo)}
                          title="Quitar día"
                          aria-label="Quitar día"
                        >
                          ✕
                        </button>
                      )}
                      {mostrarCancelar && (
                        <button
                          type="button"
                          className="btn"
                          style={ICON_BTN_STYLE_EMOJI}
                          title="Cancelar transmisión"
                          aria-label="Cancelar transmisión"
                          onClick={() => {
                            setCancelandoFecha(grupo.fecha);
                            setMotivoCancelacion("");
                          }}
                        >
                          🚫
                        </button>
                      )}
                      {problemas.length > 0 && (
                        <span style={{ ...ICON_BTN_STYLE_X, color: "var(--red-text)" }} title={problemas.join(" ")}>
                          ⚠
                        </span>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        {rows.length > 0 && (
          <tfoot>
            <tr>
              <td colSpan={4} style={{ textAlign: "right", fontWeight: 600, fontSize: 11, padding: "8px 16px" }}>
                Total
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {totalSpots}
              </td>
              {mostrarColumnaAudio && <td />}
              <td />
            </tr>
          </tfoot>
        )}
      </table>
      {!disabled && (
        <button type="button" className="btn btn-xs" style={{ marginTop: 8 }} onClick={agregarFila}>
          + Agregar día
        </button>
      )}
      {rows.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginTop: 8 }}>
          Captura al menos un día de transmisión.
        </div>
      )}
      {audios != null && audios.length === 0 && (
        <div className="fv muted" style={{ fontSize: 11, marginTop: 8 }}>
          El material a transmitir (audios) se sube y se asigna desde "Material a
          Transmitir" después de guardar la orden — necesita un id real.
        </div>
      )}
    </div>
  );
}
