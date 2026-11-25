/** Fix: llegar a "Órdenes internas" con una OI preseleccionada (p.ej. "Ver orden interna →"
 * desde Verificaciones o Incidencias) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio.
 *
 * ADR-285 (petición del usuario, con captura): la tabla ahora pagina/busca contra el
 * backend (`paginaOrdenesEstacionApi`) en vez de traer el 100% de las OE — se mockea esa
 * llamada (filtrando por `q`/`estatus`, mismo criterio que el backend real) en vez de
 * precargar `OrdenesProvider` con el arreglo completo. La fila SELECCIONADA (detalle,
 * "Clonar" vía doble clic de fila, PDF…) se resuelve con `refrescarOrdenEstacion`
 * (`useOrdenEstacionSeleccionada`), mockeada contra un registro chico que cada test puebla
 * con las OE que de verdad usa — igual que `refrescarOrdenCliente` para "OC de origen".
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrdenEstacionListPage } from "../ordenEstacion/pages/OrdenEstacionListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { estaciones } from "../state/catalogosCache";
import type { EstadoOI, OrdenCliente, OrdenEstacion } from "../types";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE, makeOEDTO, makeRow } from "./fixtures";

// ADR-169: "Producto"/"Duración" (alta de OrdenEstacion) se llenan desde el catálogo
// "Producto Duración" vía react-query — mock del catálogo (sin pegarle a la red real).
vi.mock("@/modules/catalogos/duracionSpot/api", () => ({
  duracionSpotCatalogoApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        { duracion_spot_catalogo_id: "d1", producto: "spot", descripcion_duracion: "30s", activo: true },
      ],
      total: 1,
      page: 1,
      size: 100,
      pages: 1,
    }),
  },
}));

/** Envuelve con el `QueryClientProvider` que ahora necesita `OrdenEstacionForm` (ADR-169)
 *  para leer el catálogo "Producto Duración", Y la tabla/detalle de esta pantalla
 *  (ADR-285) — una instancia nueva por test. */
function conQueryClient(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// ADR-285: registro chico que alimenta los mocks de `refrescarOrdenEstacion`/
// `refrescarOrdenCliente` de abajo — cada test/`renderPage()` registra ahí las OE/OC que
// la pantalla va a necesitar resolver (selección de fila, "OC de origen"), ANTES de montar.
const registroOE = new Map<string, OrdenEstacion>();
const registroOC = new Map<string, OrdenCliente>();
function registrarOE(oe: OrdenEstacion): OrdenEstacion {
  registroOE.set(oe.id, oe);
  return oe;
}
function registrarOC(oc: OrdenCliente): OrdenCliente {
  registroOC.set(oc.id, oc);
  return oc;
}

const paginaOEMock = vi.fn();
const paginaOCMock = vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 });

/** Simula el filtro `q`/`estatus` del backend real (mismo criterio que
 *  `OrdenClienteListPage.test.tsx`) — así las pruebas de "preselección filtra la tabla" y
 *  de visibilidad de "Clonar" por sub-estado siguen teniendo sentido sin pegarle a la red. */
function mockPaginaOE(dtos: ReturnType<typeof makeOEDTO>[]) {
  paginaOEMock.mockImplementation(async (params: { q?: string; estatus?: string }) => {
    let filtradas = dtos;
    if (params.q) {
      const qq = params.q.toLowerCase();
      filtradas = filtradas.filter((d) => d.folio_orden_estacion.toLowerCase().includes(qq));
    }
    if (params.estatus) {
      filtradas = filtradas.filter((d) => d.estatus === params.estatus);
    }
    return { items: filtradas, total: filtradas.length, page: 1, size: 20, pages: 1 };
  });
}

beforeEach(() => {
  mockPaginaOE([]);
});

vi.mock("../adapters/ordenesApi", () => ({
  paginaOrdenesEstacionApi: (params: { q?: string; estatus?: string }) => paginaOEMock(params),
  paginaOrdenesClienteApi: (params: unknown) => paginaOCMock(params),
  oesDeLaOCApi: vi.fn().mockResolvedValue([]),
  listarDiasOrdenEstacionApi: vi.fn().mockResolvedValue([]),
  listarVerificacionesApi: vi.fn().mockResolvedValue([]),
  listarHistorialComisionesApi: vi.fn().mockResolvedValue([]),
  paginaIncidenciasApi: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
}));

// ADR-113 (fix): tras "Guardar" en el alta, la pantalla se queda en el mismo formulario
// (ADR-103, ahora en modo edición de la OE recién creada) — se mockean las llamadas reales
// que dispara `crearOE` (OrdenesContext.tsx) para poder probar esa transición sin red.
// ADR-210: `listarAudiosOrdenEstacionApi` también se mockea — el formulario la llama al
// CLONAR, para precargar el Material a Transmitir; `[]` por default (ninguna de las
// pruebas de este archivo necesita que SÍ clone audios, eso ya se cubre en
// `OrdenEstacionForm.test.tsx`). ADR-285: `listarIncidenciasDeOEApi` también se mockea —
// la tabla ahora resuelve la fila seleccionada vía `useIncidenciasDeLaOC`.
vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    crearOrdenEstacionApi: vi.fn().mockResolvedValue({ orden_estacion_id: "oe-real-post-guardar" }),
    subirMaterialStagingApi: vi
      .fn()
      .mockResolvedValue({ ref: "orden_estacion/audios/abc_uno.mp3", nombre_archivo: "uno.mp3" }),
    listarAudiosOrdenEstacionApi: vi.fn().mockResolvedValue([]),
    listarIncidenciasDeOEApi: vi.fn().mockResolvedValue([]),
  };
});

// ADR-285: `refrescarOrdenEstacion`/`refrescarOrdenCliente` ahora alimentan TAMBIÉN la
// selección de fila de la tabla (`useOrdenEstacionSeleccionada`/`useOrdenClienteSeleccionada`
// las usan), no solo el flujo de alta — resuelven contra `registroOE`/`registroOC`. El
// fallback fijo de siempre ("oe-real-post-guardar") sigue cubriendo el flujo de "Guardar"
// (esa OE nunca se registra a mano, nace de `crearOrdenEstacionApi`).
vi.mock("../adapters/refrescar", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/refrescar")>();
  return {
    ...actual,
    refrescarOrdenEstacion: vi.fn(async (id: string) =>
      registroOE.get(id) ??
      makeOE({
        id: "oe-real-post-guardar",
        folio_orden_interna: "OE-2026-9999A",
        periodo_transmision: [
          makeRow({ orden_estacion_dia_id: "dia-real-post-guardar", fecha: "2026-10-05", hora_inicio: "07:00", hora_termino: "07:00", spots_diarios: 5 }),
        ],
      }),
    ),
    refrescarOrdenCliente: vi.fn(async (id: string) => registroOC.get(id) ?? makeOC({ id })),
  };
});

estaciones.push({ id: "es1", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-AM", frecuencia: "900 AM", tipo_senal: "fm" });

const ESTATUS_OE_V5_A_SPEC: Record<EstadoOI, string> = {
  asignada_afiliado: "asignada",
  programados_conciliados: "en_transmision",
  reales_conciliados: "cerrada",
};

/** Construye un par OE v5 + DTO que comparten id/folio/orden/estatus — evita escribir dos
 *  veces los mismos datos al armar las tablas mockeadas de este archivo (una fila de la
 *  tabla viene del DTO vía `paginaOrdenesEstacionApi`; la fila SELECCIONADA, del v5 vía
 *  `refrescarOrdenEstacion`, registrado aparte con `registrarOE`). */
function parOE(overrides: Partial<OrdenEstacion> = {}) {
  const oe = makeOE(overrides);
  const dto = makeOEDTO({
    orden_estacion_id: oe.id,
    folio_orden_estacion: oe.folio_orden_interna,
    orden_id: oe.orden_id,
    estacion_id: oe.estacion_id,
    plaza_id: oe.plaza_id,
    estatus: ESTATUS_OE_V5_A_SPEC[oe.estatus],
    created_at: `${oe.created_at}T00:00:00`,
  });
  return { oe, dto };
}

function renderPage(oeIdPreseleccionada?: string) {
  const oc = registrarOC(makeOC({ id: "oc-1" }));
  const { oe: oe1, dto: dto1 } = parOE({ id: "oe-1", folio_orden_interna: "OE-2026-0054A", orden_id: oc.id });
  const { oe: oe2, dto: dto2 } = parOE({ id: "oe-2", folio_orden_interna: "OE-2026-0054B", orden_id: oc.id });
  registrarOE(oe1);
  registrarOE(oe2);
  mockPaginaOE([dto1, dto2]);

  const utils = render(
    conQueryClient(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage oeIdPreseleccionada={oeIdPreseleccionada} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
    ),
  );
  const tabla = utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("ADR-210 (manera 2, petición del usuario): columna 'Acciones' con 'Clonar' en la tabla, solo en 2.1", () => {
  it("el botón '📋 Clonar' solo aparece en renglones en 2.1 'Asignada al afiliado'", async () => {
    const oc = registrarOC(makeOC({ id: "oc-1" }));
    const { dto: dtoAsignada } = parOE({ id: "oe-asig", folio_orden_interna: "OE-2026-0070A", orden_id: oc.id, estatus: "asignada_afiliado" });
    const { dto: dtoProgramada } = parOE({ id: "oe-prog", folio_orden_interna: "OE-2026-0071A", orden_id: oc.id, estatus: "programados_conciliados" });
    mockPaginaOE([dtoAsignada, dtoProgramada]);
    const utils = render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;

    const filaAsignada = (await within(tabla).findByText("OE-2026-70A")).closest("tr") as HTMLElement;
    const filaProgramada = within(tabla).getByText("OE-2026-71A").closest("tr") as HTMLElement;
    expect(within(filaAsignada).getByRole("button", { name: "📋 Clonar" })).toBeInTheDocument();
    expect(within(filaProgramada).queryByRole("button", { name: "📋 Clonar" })).toBeNull();
  });

  it("clonar desde la tabla lleva al alta precargada, sin seleccionar la fila (sin activar edición)", async () => {
    const { tabla, container } = renderPage();

    const filaClonar = (await within(tabla).findByText("OE-2026-54A")).closest("tr") as HTMLElement;
    fireEvent.click(within(filaClonar).getByRole("button", { name: "📋 Clonar" }));

    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-54A)")).toBeInTheDocument();
    // Estación sigue editable (no es modo edición) — a diferencia de "Editar", que la
    // deshabilita (`disabled={isEdit}` en `OrdenEstacionForm.tsx`).
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación")).not.toBeDisabled();
  });

  it("fix: 'Cancelar' tras clonar desde la tabla se queda en 'Órdenes de Transmisión' (no navega a Órdenes de Servicio)", async () => {
    const oc = registrarOC(makeOC({ id: "oc-1" }));
    const { dto: dtoAsignada } = parOE({ id: "oe-asig", folio_orden_interna: "OE-2026-0070A", orden_id: oc.id, estatus: "asignada_afiliado" });
    mockPaginaOE([dtoAsignada]);
    const onVerOC = vi.fn();
    const { container } = render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage onVerOC={onVerOC} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const tabla = container.querySelector("table") as HTMLTableElement;
    const fila = (await within(tabla).findByText("OE-2026-70A")).closest("tr") as HTMLElement;
    fireEvent.click(within(fila).getByRole("button", { name: "📋 Clonar" }));
    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-70A)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    // A diferencia de "+ Nueva Orden de Transmisión"/"+ Asignar estaciones" (que sí vienen
    // de Órdenes de Servicio y regresan ahí), clonar desde ESTA lista nunca estuvo en esa
    // pantalla — "Cancelar" debe quedarse aquí mismo.
    expect(onVerOC).not.toHaveBeenCalled();
    expect(screen.getByText("Órdenes de Transmisión")).toBeInTheDocument();
    expect(screen.queryByText("Nueva Orden de Transmisión (clonada de OE-2026-70A)")).toBeNull();
  });
});

describe("ADR-139 (corrige un bug real): cambiar de OE seleccionada resetea el panel de detalle", () => {
  it("un diálogo de PDF abierto en la OE anterior no sigue abierto al seleccionar otra OE", async () => {
    const { tabla } = renderPage();

    fireEvent.click(await within(tabla).findByText("OE-2026-54A"));
    fireEvent.click(await screen.findByText(/PDF #1 · Orden de servicio/));
    expect(screen.getByText("🖨️ Imprimir")).toBeInTheDocument();

    fireEvent.click(within(tabla).getByText("OE-2026-54B"));
    // Sin `key={oe.id}` en <OrdenEstacionDetailPanel>, React reutiliza la misma
    // instancia (y su estado local `abierto`) — el diálogo de la OE anterior seguiría
    // visible aquí, aunque nunca se le dio clic para esta OE.
    expect(screen.queryByText("🖨️ Imprimir")).toBeNull();
  });
});

describe("Fix: OI preseleccionada filtra la tabla (no solo resalta la fila)", () => {
  it("sin preselección, se ven todas las OI", async () => {
    const { tabla } = renderPage();
    await waitFor(() => expect(within(tabla).getByText("OE-2026-54A")).toBeInTheDocument());
    expect(within(tabla).getByText("OE-2026-54B")).toBeInTheDocument();
    expect(await screen.findByText("2 de 2")).toBeInTheDocument();
  });

  it("con una OI preseleccionada, el buscador arranca con su folio y la tabla muestra solo esa fila", async () => {
    const { tabla } = renderPage("oe-2");

    // El buscador arranca con el folio CRUDO (sin formatear) — el formateo (ADR-275)
    // es solo de despliegue en la tabla.
    const buscador = screen.getByPlaceholderText("Buscar folio, estación, afiliado, OC de origen…");
    await waitFor(() => expect((buscador as HTMLInputElement).value).toBe("OE-2026-0054B"));

    await waitFor(() => expect(within(tabla).getByText("OE-2026-54B")).toBeInTheDocument());
    expect(within(tabla).queryByText("OE-2026-54A")).toBeNull();
    // ADR-285: `total` ahora es el total YA FILTRADO por el backend (mismo criterio que
    // Facturación/Cobranza), no el total general de la tabla sin filtrar.
    expect(await screen.findByText("1 de 1")).toBeInTheDocument();
  });
});

describe("Fix (ADR-288): el filtro de sub-estado (pills 2.1/2.2/2.3 y 'Pendientes de asignar'/'Pendientes de verificar' del sidebar) manda al backend su vocabulario (spec), no el v5 de la pantalla", () => {
  it("al arrancar con un filtroInicial v5 (p.ej. 'Pendientes de asignar'), el backend recibe 'asignada', no 'asignada_afiliado'", async () => {
    const oc = registrarOC(makeOC({ id: "oc-1" }));
    const { dto } = parOE({ id: "oe-asig", folio_orden_interna: "OE-2026-0080A", orden_id: oc.id, estatus: "asignada_afiliado" });
    mockPaginaOE([dto]);

    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage filtroInicial="asignada_afiliado" onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );

    await waitFor(() =>
      expect(paginaOEMock).toHaveBeenCalledWith(expect.objectContaining({ estatus: "asignada" })),
    );
    expect(await screen.findByText("1 de 1")).toBeInTheDocument();
  });

  it("al elegir la pill '2.2 Programados', el backend recibe 'en_transmision', no 'programados_conciliados'", async () => {
    const { tabla } = renderPage();
    fireEvent.click(screen.getByText("2.2 Programados"));

    await waitFor(() =>
      expect(paginaOEMock).toHaveBeenCalledWith(expect.objectContaining({ estatus: "en_transmision" })),
    );
    expect(tabla).toBeInTheDocument();
  });
});

// ADR-285 (petición del usuario, con captura): el orden "más reciente primero" ya NO lo
// decide el frontend (se quitó su propio `.sort()` sobre `state.ordenesEstacion`): lo
// decide el `default_order_by` del backend — cubierto por
// `test_listado_ordena_por_fecha_de_creacion_mas_reciente_primero_oe` en
// `test_f1_03_ordenes_lectura.py`, no aquí (mismo criterio que `OrdenClienteListPage.test.tsx`).

// Helper compartido por las pruebas de ADR-116 (abajo): llena lo mínimo para poder
// guardar (Estación/Producto/Duración/Tarifa + un audio + un día con spots).
async function capturarOEMinima(container: HTMLElement) {
  // ADR-221b: "Estación" ahora es un `SearchableSelect` (input con filtro + lista), no un
  // `<select>` nativo — hay que teclear y luego elegir la opción de la lista.
  fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Estación"), { target: { value: "XEW" } });
  fireEvent.mouseDown(screen.getByText("900 AM FM XEW-AM"));
  // ADR-169: "Producto" se llena desde el catálogo "Producto Duración" vía react-query —
  // hay que esperar a que la opción exista antes de poder seleccionarla.
  await waitFor(() =>
    expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
  );
  fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
  fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
  fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });

  // ADR-266: ya no hay `accept` (ya no es lista blanca de audio) — el único
  // `input[type="file"]` del formulario de alta es el de "Material a Transmitir".
  const inputAudio = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(inputAudio, { target: { files: [new File(["contenido"], "uno.mp3", { type: "audio/mpeg" })] } });
  await waitFor(() => expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull());

  fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));
  const spotsInputs = container.querySelectorAll('input[type="number"]');
  fireEvent.change(spotsInputs[spotsInputs.length - 1], { target: { value: "5" } });
}

// ADR-210: sube un material si hace falta, sin tocar Estación/Producto/Duración/Tarifa —
// a diferencia de `capturarOEMinima`, se usa sobre un formulario YA precargado (clonado),
// solo para habilitar "+ Agregar día"/"Quitar día" (ADR-110, gated por `hayMaterial`).
async function asegurarMaterialListPage(container: HTMLElement) {
  if (!screen.queryByText("Sin audios elegidos todavía.")) return;
  const inputAudio = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(inputAudio, { target: { files: [new File(["contenido"], "uno.mp3", { type: "audio/mpeg" })] } });
  await waitFor(() => expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull());
}

describe("ADR-116: tras 'Guardar' en el alta, pregunta si se quiere generar otra Orden de Transmisión", () => {
  it("al guardar aparece el modal de confirmación (no pasa directo a edición, ADR-103 ya no aplica)", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const container = document.body;
    await capturarOEMinima(container);

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    await waitFor(() =>
      expect(screen.getByText("¿Deseas generar otra Orden de Transmisión para esta misma Orden de Servicio?")).toBeInTheDocument(),
    );
    // Ya no se pasa directo a modo edición de la OE recién creada.
    expect(screen.queryByText("Editar: OE-2026-9999A")).toBeNull();
  });

  it("'Sí, generar otra' limpia el formulario (no arrastra los datos de la OE anterior)", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const container = document.body;
    await capturarOEMinima(container);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sí, generar otra" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Sí, generar otra" }));

    // Sigue en el formulario de alta (misma OC), pero en blanco — sin la estación,
    // producto, tarifa ni audio de la OE que se acaba de guardar.
    expect(screen.getByText("Nueva Orden de Transmisión")).toBeInTheDocument();
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación").value).toBe("");
    expect(screen.getByText("Sin audios elegidos todavía.")).toBeInTheDocument();
  });

  it("'No, ir a la lista' regresa a la lista con la OE recién creada seleccionada", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const container = document.body;
    await capturarOEMinima(container);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "No, ir a la lista" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "No, ir a la lista" }));

    expect(screen.queryByText("Nueva Orden de Transmisión")).toBeNull();
    expect(screen.getByText("Órdenes de Transmisión")).toBeInTheDocument();
    // Aparece en la tabla Y en el panel de detalle (queda seleccionada) — basta con que
    // exista al menos una vez.
    await waitFor(() => expect(screen.getAllByText("OE-2026-9999A").length).toBeGreaterThan(0));
  });

  it("ADR-210: 'Clonar' se queda en el alta, precargada con los datos de la OE recién guardada", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const container = document.body;
    await capturarOEMinima(container);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Clonar" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Clonar" }));

    // Sigue en el alta (misma OC), pero precargada con los datos de la OE que acaba de
    // guardarse ("OE-2026-9999A", mock de `refrescarOrdenEstacion` arriba) — no es edición.
    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-9999A)")).toBeInTheDocument();
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("800.00");
    // ADR-210: el material TAMBIÉN se clona (mock `listarAudiosOrdenEstacionApi` arriba,
    // `[]` por default) — la OE recién guardada no tenía ninguno, así que sigue
    // pidiéndolo, pero solo tras resolver esa consulta.
    await screen.findByText("Sin audios elegidos todavía.");
  });

  it("ADR-210: tras clonar, 'Sí, generar otra' en el siguiente guardado ya no arrastra la clonación", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const container = document.body;
    await capturarOEMinima(container);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Clonar" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Clonar" }));
    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-9999A)")).toBeInTheDocument();

    // ADR-210 Fix 3/4 (corrige una prueba intermitente real, vista en CI): clonar dispara
    // una consulta async para precargar el Material a Transmitir
    // (`listarAudiosOrdenEstacionApi`, mockeada arriba) — hay que esperar a que resuelva
    // ANTES de seguir, o una corrida lenta (como un runner de CI) puede dejar
    // `asegurarMaterialListPage` (abajo) actuando sobre un estado "Cargando…" todavía en
    // vuelo y saltarse la subida por completo.
    await waitFor(() =>
      expect(screen.queryByText("Cargando material de la Orden de Transmisión clonada…")).toBeNull(),
    );

    // La OE clonada ("OE-2026-9999A", mock de `refrescarOrdenEstacion` arriba) no
    // corresponde a ningún dato real de este test (su `estacion_id` default no está en
    // el catálogo de este archivo y la fecha de su período cae fuera del rango de
    // campaña de la OC) — se vuelve a capturar completa, como cualquier alta, para poder
    // guardar de verdad una segunda vez; lo que esta prueba evalúa es que la clonación no
    // se arrastre al SIGUIENTE alta.
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Estación"), { target: { value: "XEW" } });
    fireEvent.mouseDown(screen.getByText("900 AM FM XEW-AM"));
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await asegurarMaterialListPage(container);
    // El período heredado del clon ("2026-10-05") cae fuera del rango de campaña de esta
    // OC — se quita antes de agregar uno nuevo.
    fireEvent.click(screen.getByRole("button", { name: "Quitar día" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));
    const spotsInputs = container.querySelectorAll('input[type="number"]');
    fireEvent.change(spotsInputs[spotsInputs.length - 1], { target: { value: "5" } });

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sí, generar otra" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Sí, generar otra" }));

    // En blanco otra vez — "Sí, generar otra" no debe dejar la clonación pegada.
    expect(screen.getByText("Nueva Orden de Transmisión")).toBeInTheDocument();
    expect(screen.queryByText(/clonada de/)).toBeNull();
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación").value).toBe("");
  });

  it("'Cancelar' en el alta regresa a Órdenes de Servicio (la OC elegida), no a la lista de Transmisión", async () => {
    const oc = makeOC({ id: "oc-1" });
    const onVerOC = vi.fn();
    render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={onVerOC} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onVerOC).toHaveBeenCalledWith(oc.id);
  });
});
