/** Tanda 1: cálculos puros de OrdenCliente/OrdenEstacion (1.1–1.3) + la porción de 1.4 que
 * SÍ vive como selector puro (`oiImporte`, `tarifaReferencia`). El desglose OIR/emisora y el
 * desvío contra tarifa de referencia están calculados inline en `OrdenEstacionDetailPanel.tsx`
 * (un componente, no un selector) — se prueban en la Tanda 3 con React Testing Library.
 *
 * 1.9 (verificaciones derivadas) y 1.10 (contadores/vistas operativas) también viven en
 * `selectors.ts` y son igual de puros, pero se agrupan con la Tanda 3 por acuerdo con el
 * usuario (van junto con la interacción de formularios).
 */

import { describe, expect, it } from "vitest";

import {
  anunciantes,
  contratos,
  contratosVigentesDeAnunciante,
  marcasDeAnunciante,
  tarifas,
  tarifaReferencia,
} from "../state/catalogosCache";
import {
  balanceSpotsOC,
  calcularContadores,
  filtrarOrdenesCliente,
  oiImporte,
  oiPeriodoTexto,
  oiPrimeraFecha,
  oiTotalSpots,
  oiUltimaFecha,
  oiVentanaTipica,
  todasReconciliadas,
  totalesOC,
  verificacionDerivada,
  verificacionesDerivadas,
} from "../state/selectors";
import { makeOC, makeOE, makeRow } from "./fixtures";

// `state/catalogosCache.ts` nace vacío (en la app real lo llena `cargarCatalogosReales()`
// antes de montar); estas pruebas dependen de `findAnunciante`/`contratosVigentesDeAnunciante`/
// `tarifaReferencia`, así que sembramos aquí el mínimo necesario, una sola vez.
anunciantes.push({
  id: "an1",
  agencia_id: null,
  nombre_comercial: "Televisa Publicidad",
  nombre_fiscal: "Televisa Publicidad SA de CV",
  rfc_anunciante: "TPU900101XX1",
  dias_credito_default: 30,
  categoria_id: "",
});
contratos.push(
  { id: "co1", anunciante_id: "an1", numero_contrato: "CT-2025-001", nombre_contrato: "Campaña Verano 2025", estado_contrato: "vigente" },
  { id: "co1b", anunciante_id: "an1", numero_contrato: "CT-2024-098", nombre_contrato: "Anual 2024 (cerrado)", estado_contrato: "finalizado" },
);
tarifas.push({ id: "ta1", plaza_id: "pl1", tipo_senal: "fm", duracion_spot: "30s", tarifa_bruta: 9500, descuento_pct: 10 });

describe("totalesOC — 1.1", () => {
  it("subtotal = total_spots × precio_unitario", () => {
    const oc = makeOC({ total_spots: 100, precio_unitario: 1000 });
    expect(totalesOC(oc).subtotal).toBe(100_000);
  });

  it("iva = subtotal × IVA_RATE (16%)", () => {
    const oc = makeOC({ total_spots: 100, precio_unitario: 1000 });
    expect(totalesOC(oc).iva).toBe(16_000);
  });

  it("total = subtotal + iva", () => {
    const oc = makeOC({ total_spots: 100, precio_unitario: 1000 });
    const { subtotal, iva, total } = totalesOC(oc);
    expect(total).toBe(subtotal + iva);
    expect(total).toBe(116_000);
  });

  it("caso con decimales feos (precio 11,933.33 × 37 spots) da el resultado correcto al centavo", () => {
    const oc = makeOC({ total_spots: 37, precio_unitario: 11_933.33 });
    const { subtotal, iva, total } = totalesOC(oc);
    expect(subtotal).toBeCloseTo(441_533.21, 2);
    expect(iva).toBeCloseTo(70_645.31, 2);
    expect(total).toBeCloseTo(512_178.52, 2);
  });

  it("hallazgo: totalesOC no redondea a centavos — el residuo de punto flotante queda en el número crudo", () => {
    // 0.1 × 3 es el ejemplo clásico de imprecisión de punto flotante en JS (da
    // 0.30000000000000004, no 0.3). totalesOC no aplica ningún redondeo interno: el
    // redondeo a 2 decimales solo ocurre al formatear con fmtMonto(), nunca antes.
    const oc = makeOC({ total_spots: 3, precio_unitario: 0.1 });
    const { subtotal } = totalesOC(oc);
    expect(subtotal).not.toBe(0.3);
    expect(subtotal).toBeCloseTo(0.3, 2);
  });

  it("total_spots = 0 y precio_unitario = 0 no producen NaN", () => {
    const oc = makeOC({ total_spots: 0, precio_unitario: 0 });
    const { subtotal, iva, total } = totalesOC(oc);
    expect(subtotal).toBe(0);
    expect(iva).toBe(0);
    expect(total).toBe(0);
    expect(Number.isNaN(subtotal)).toBe(false);
    expect(Number.isNaN(iva)).toBe(false);
    expect(Number.isNaN(total)).toBe(false);
  });
});

describe("balanceSpotsOC — 1.2", () => {
  it("OC de 120 spots con una OI de 50 → por asignar 70", () => {
    const oc = makeOC({ total_spots: 120 });
    const oe1 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 50 })] });
    const balance = balanceSpotsOC(oc, [oe1]);
    expect(balance.asignados).toBe(50);
    expect(balance.porAsignar).toBe(70);
    expect(balance.sobreAsignado).toBe(false);
  });

  it("agregar una segunda OI de 70 deja por asignar en 0 exacto", () => {
    const oc = makeOC({ total_spots: 120 });
    const oe1 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 50 })] });
    const oe2 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 70 })] });
    const balance = balanceSpotsOC(oc, [oe1, oe2]);
    expect(balance.asignados).toBe(120);
    expect(balance.porAsignar).toBe(0);
    expect(balance.pctAsignado).toBe(100);
    expect(balance.sobreAsignado).toBe(false);
  });

  it("una OI adicional de 1 spot detecta sobre-asignación", () => {
    const oc = makeOC({ total_spots: 120 });
    const oe1 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 50 })] });
    const oe2 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 70 })] });
    const oe3 = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 1 })] });
    const balance = balanceSpotsOC(oc, [oe1, oe2, oe3]);
    expect(balance.asignados).toBe(121);
    expect(balance.porAsignar).toBe(-1);
    expect(balance.sobreAsignado).toBe(true);
    // El % asignado se limita a 100 aunque haya sobre-asignación (para no romper la barra visual).
    expect(balance.pctAsignado).toBe(100);
  });

  it("una OI con 0 spots (periodo vacío) no rompe el cálculo", () => {
    const oc = makeOC({ total_spots: 120 });
    const oeVacia = makeOE({ periodo_transmision: [] });
    const balance = balanceSpotsOC(oc, [oeVacia]);
    expect(balance.asignados).toBe(0);
    expect(balance.porAsignar).toBe(120);
    expect(balance.sobreAsignado).toBe(false);
  });

  it("sin ninguna OI, todo el total está por asignar", () => {
    const oc = makeOC({ total_spots: 120 });
    const balance = balanceSpotsOC(oc, []);
    expect(balance.asignados).toBe(0);
    expect(balance.porAsignar).toBe(120);
    expect(balance.pctAsignado).toBe(0);
  });

  it("total_spots = 0 en la OC no produce división entre cero (pctAsignado queda en 0, no NaN)", () => {
    const oc = makeOC({ total_spots: 0 });
    const oe = makeOE({ periodo_transmision: [makeRow({ spots_diarios: 10 })] });
    const balance = balanceSpotsOC(oc, [oe]);
    expect(balance.pctAsignado).toBe(0);
    expect(Number.isNaN(balance.pctAsignado)).toBe(false);
    expect(balance.sobreAsignado).toBe(true);
  });
});

describe("Periodo de transmisión de una OI — 1.3", () => {
  it("oiTotalSpots suma spots_diarios de todas las filas del periodo", () => {
    const oe = makeOE({
      periodo_transmision: [makeRow({ fecha: "2025-06-01", spots_diarios: 10 }), makeRow({ fecha: "2025-06-02", spots_diarios: 15 })],
    });
    expect(oiTotalSpots(oe)).toBe(25);
  });

  it("oiImporte = total de spots del periodo × precio_spot", () => {
    const oe = makeOE({
      precio_spot: 800,
      periodo_transmision: [makeRow({ fecha: "2025-06-01", spots_diarios: 10 }), makeRow({ fecha: "2025-06-02", spots_diarios: 15 })],
    });
    expect(oiImporte(oe)).toBe(25 * 800);
  });

  it("periodo vacío da 0 spots e importe 0, sin romperse", () => {
    const oe = makeOE({ periodo_transmision: [] });
    expect(oiTotalSpots(oe)).toBe(0);
    expect(oiImporte(oe)).toBe(0);
  });

  it("primera/última fecha se calculan por orden cronológico, no por orden de captura", () => {
    // Las filas se capturan fuera de orden a propósito.
    const oe = makeOE({
      periodo_transmision: [
        makeRow({ fecha: "2025-06-15" }),
        makeRow({ fecha: "2025-06-01" }),
        makeRow({ fecha: "2025-06-30" }),
      ],
    });
    expect(oiPrimeraFecha(oe)).toBe("2025-06-01");
    expect(oiUltimaFecha(oe)).toBe("2025-06-30");
  });

  it("oiVentanaTipica toma el horario de la PRIMERA fila capturada (no la cronológicamente primera)", () => {
    // Documenta el comportamiento real: usa periodo_transmision[0], sin ordenar. Si el
    // equipo esperaba que fuera el horario de la fecha más temprana, esto es un hallazgo.
    const oe = makeOE({
      periodo_transmision: [
        makeRow({ fecha: "2025-06-15", hora_inicio: "20:00", hora_termino: "21:00" }),
        makeRow({ fecha: "2025-06-01", hora_inicio: "07:00", hora_termino: "08:00" }),
      ],
    });
    expect(oiVentanaTipica(oe)).toEqual({ inicio: "20:00", termino: "21:00" });
  });

  it("oiPeriodoTexto muestra '(1 día)' en singular cuando inicio y fin coinciden", () => {
    const oe = makeOE({ periodo_transmision: [makeRow({ fecha: "2025-06-15" })] });
    expect(oiPeriodoTexto(oe)).toBe("2025-06-15 (1 día)");
  });

  it("oiPeriodoTexto muestra el rango con el número de días capturados cuando difieren", () => {
    const oe = makeOE({
      periodo_transmision: [makeRow({ fecha: "2025-06-01" }), makeRow({ fecha: "2025-06-02" }), makeRow({ fecha: "2025-06-10" })],
    });
    expect(oiPeriodoTexto(oe)).toBe("2025-06-01 → 2025-06-10 (3 días)");
  });

  it("oiPeriodoTexto regresa — con periodo vacío", () => {
    expect(oiPeriodoTexto(makeOE({ periodo_transmision: [] }))).toBe("—");
  });
});

describe("Tarifa de referencia — parte pura de 1.4", () => {
  it("encuentra la tarifa vigente para plaza + tipo de señal + duración", () => {
    const tarifa = tarifaReferencia("pl1", "fm", "30s");
    expect(tarifa).toBeDefined();
    expect(tarifa?.tarifa_bruta).toBe(9500);
    expect(tarifa?.descuento_pct).toBe(10);
  });

  it("sin tarifa de referencia vigente para la combinación, regresa undefined sin romperse (no lanza)", () => {
    expect(() => tarifaReferencia("pl1", "fm", "10s")).not.toThrow();
    expect(tarifaReferencia("pl1", "fm", "10s")).toBeUndefined();
  });

  it("una plaza inexistente también regresa undefined, no lanza", () => {
    expect(tarifaReferencia("plaza-que-no-existe", "fm", "30s")).toBeUndefined();
  });
});

describe("Cascada de catálogos — parte pura de 1.7", () => {
  it("un anunciante sin marcas/contratos vigentes (id inexistente) regresa listas vacías, no lanza", () => {
    // En datos reales, un anunciante activo normalmente tiene ≥1 contrato vigente y
    // ≥1 marca, pero el código no asume esa garantía. Se prueba con un id que no existe.
    expect(contratosVigentesDeAnunciante("anunciante-que-no-existe")).toEqual([]);
    expect(marcasDeAnunciante("anunciante-que-no-existe")).toEqual([]);
  });

  it("filtra correctamente los contratos vigentes de un anunciante real, excluyendo los finalizados", () => {
    // an1 (Televisa Publicidad) tiene co1 (vigente) y co1b (finalizado) en el catálogo.
    const contratos = contratosVigentesDeAnunciante("an1");
    expect(contratos.map((c) => c.id)).toContain("co1");
    expect(contratos.map((c) => c.id)).not.toContain("co1b");
  });
});

describe("todasReconciliadas — precondición de cierre (1.5)", () => {
  it("una lista vacía de OI no cuenta como 'todas reconciliadas' (no hay ninguna)", () => {
    expect(todasReconciliadas([])).toBe(false);
  });

  it("si alguna OI no está en 2.3, no cuentan como todas reconciliadas", () => {
    const oes = [makeOE({ estatus: "reales_conciliados" }), makeOE({ estatus: "asignada_afiliado" })];
    expect(todasReconciliadas(oes)).toBe(false);
  });

  it("si todas las OI están en 2.3, sí cuentan como todas reconciliadas", () => {
    const oes = [makeOE({ estatus: "reales_conciliados" }), makeOE({ estatus: "reales_conciliados" })];
    expect(todasReconciliadas(oes)).toBe(true);
  });
});

describe("Verificaciones derivadas — 1.9", () => {
  it("solo proyecta las OI que llegaron a 2.3 (reales_conciliados)", () => {
    const oes = [
      makeOE({ estatus: "asignada_afiliado" }),
      makeOE({ estatus: "programados_conciliados" }),
      makeOE({ estatus: "reales_conciliados" }),
    ];
    const verificaciones = verificacionesDerivadas(oes);
    expect(verificaciones).toHaveLength(1);
    expect(verificaciones[0].ordenEstacionId).toBe(oes[2].id);
  });

  it("compara programado (efectivo) contra real día a día y marca reconciliada=true", () => {
    const oe = makeOE({
      estatus: "reales_conciliados",
      periodo_transmision: [makeRow({ fecha: "2025-06-01", spots_diarios: 10 }), makeRow({ fecha: "2025-06-02", spots_diarios: 10 })],
      horarios_reales: [makeRow({ fecha: "2025-06-01", spots_diarios: 8 })],
    });
    const verificacion = verificacionDerivada(oe);
    expect(verificacion.reconciliada).toBe(true);
    expect(verificacion.totalProgramado).toBe(20);
    expect(verificacion.totalReal).toBe(18); // 8 (con override) + 10 (sin override, cae al programado)
    const dia1 = verificacion.dias.find((d) => d.fecha === "2025-06-01");
    expect(dia1?.diferenciaSpots).toBe(-2);
    const dia2 = verificacion.dias.find((d) => d.fecha === "2025-06-02");
    expect(dia2?.diferenciaSpots).toBe(0);
  });

  it("fix (orden más reciente primero): `actualizadaEn` toma `updated_at`, y cae a `created_at` si no hay `updated_at`", () => {
    const conUpdated = verificacionDerivada(makeOE({ estatus: "reales_conciliados", created_at: "2025-01-01", updated_at: "2025-06-15" }));
    expect(conUpdated.actualizadaEn).toBe("2025-06-15");

    const sinUpdated = verificacionDerivada(makeOE({ estatus: "reales_conciliados", created_at: "2025-01-01", updated_at: null }));
    expect(sinUpdated.actualizadaEn).toBe("2025-01-01");
  });

  it("una OI en 2.1 o 2.2 no aparece en la lista, aunque se le pida directamente su proyección individual (documenta que la función no valida el estatus por sí sola)", () => {
    const oe21 = makeOE({ estatus: "asignada_afiliado" });
    expect(verificacionesDerivadas([oe21])).toHaveLength(0);
    // verificacionDerivada() en sí no valida el estatus — es responsabilidad de
    // verificacionesDerivadas() filtrar antes de proyectar. Se documenta el límite.
    expect(() => verificacionDerivada(oe21)).not.toThrow();
  });
});

describe("Contadores de sidebar / vistas operativas — 1.10", () => {
  it("cuenta correctamente cada categoría de OrdenesCounts", () => {
    const ordenesCliente = [
      makeOC({ estatus_orden: "orden_interna" }),
      makeOC({ estatus_orden: "orden_cerrada" }),
    ];
    const ordenesEstacion = [
      makeOE({ orden_id: ordenesCliente[0].id, estatus: "asignada_afiliado" }),
      makeOE({ orden_id: ordenesCliente[0].id, estatus: "reales_conciliados" }),
    ];
    const counts = calcularContadores(ordenesCliente, ordenesEstacion, 5);
    expect(counts.ordenesCliente).toBe(2);
    expect(counts.ordenesEstacion).toBe(2);
    expect(counts.verificaciones).toBe(1); // solo la que está en reales_conciliados
    expect(counts.incidencias).toBe(5);
    expect(counts.pendientesAsignar).toBe(1); // la OI en 2.1
    expect(counts.pendientesVerificar).toBe(0); // ninguna en 2.2
    expect(counts.listasFacturar).toBe(1); // la OC en orden_cerrada
  });

  it("'listas para cerrar' exige que la OC esté en orden_interna Y que TODAS sus OI estén en 2.3", () => {
    const ocConUnaPendiente = makeOC({ estatus_orden: "orden_interna" });
    const ocTodasReconciliadas = makeOC({ estatus_orden: "orden_interna" });
    const ordenesEstacion = [
      makeOE({ orden_id: ocConUnaPendiente.id, estatus: "asignada_afiliado" }),
      makeOE({ orden_id: ocTodasReconciliadas.id, estatus: "reales_conciliados" }),
    ];
    const counts = calcularContadores([ocConUnaPendiente, ocTodasReconciliadas], ordenesEstacion, 0);
    expect(counts.listasCerrar).toBe(1);
  });

  it("'pendientes de asignar' cuenta OI en 2.1 (asignada_afiliado) — no OC sin ninguna OI", () => {
    // Esta es la definición del prototipo aprobado (docs/referencias/.../Fase_1_-_Ordenes.html
    // líneas 693-694), distinta de lo que se asumió al redactar el guion de pruebas.
    const oc = makeOC();
    const ordenesEstacion = [makeOE({ orden_id: oc.id, estatus: "asignada_afiliado" })];
    expect(calcularContadores([oc], ordenesEstacion, 0).pendientesAsignar).toBe(1);
  });
});

describe("filtrarOrdenesCliente — 1.10", () => {
  it("'activas' excluye los estados facturados/cobrada/cancelada", () => {
    const activa = makeOC({ estatus_orden: "orden_interna" });
    const cobrada = makeOC({ estatus_orden: "cobrada" });
    const cancelada = makeOC({ estatus_orden: "cancelada" });
    const resultado = filtrarOrdenesCliente([activa, cobrada, cancelada], [], { filtro: "activas", search: "" });
    expect(resultado.map((o) => o.id)).toEqual([activa.id]);
  });

  it("'listas_cerrar' exige orden_interna con todas sus OI en 2.3", () => {
    const lista = makeOC({ estatus_orden: "orden_interna" });
    const noLista = makeOC({ estatus_orden: "orden_interna" });
    const ordenesEstacion = [
      makeOE({ orden_id: lista.id, estatus: "reales_conciliados" }),
      makeOE({ orden_id: noLista.id, estatus: "programados_conciliados" }),
    ];
    const resultado = filtrarOrdenesCliente([lista, noLista], ordenesEstacion, { filtro: "listas_cerrar", search: "" });
    expect(resultado.map((o) => o.id)).toEqual([lista.id]);
  });

  it("'listas_facturar' exige estatus orden_cerrada exacto", () => {
    const cerrada = makeOC({ estatus_orden: "orden_cerrada" });
    const interna = makeOC({ estatus_orden: "orden_interna" });
    const resultado = filtrarOrdenesCliente([cerrada, interna], [], { filtro: "listas_facturar", search: "" });
    expect(resultado.map((o) => o.id)).toEqual([cerrada.id]);
  });

  it("la búsqueda encuentra por folio, número de orden del cliente o nombre del anunciante (catálogo real)", () => {
    const oc = makeOC({ folio_orden: "OC-2025-0099", numero_orden_cliente: "PO-ABC-1", anunciante_id: "an1" });
    expect(filtrarOrdenesCliente([oc], [], { filtro: "todas", search: "0099" }).map((o) => o.id)).toEqual([oc.id]);
    expect(filtrarOrdenesCliente([oc], [], { filtro: "todas", search: "PO-ABC-1" }).map((o) => o.id)).toEqual([oc.id]);
    expect(filtrarOrdenesCliente([oc], [], { filtro: "todas", search: "Televisa Publicidad" }).map((o) => o.id)).toEqual([oc.id]);
    expect(filtrarOrdenesCliente([oc], [], { filtro: "todas", search: "no existe" })).toEqual([]);
  });
});
