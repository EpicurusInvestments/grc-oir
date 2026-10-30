/** Fix: llegar a "Órdenes internas" con una OI preseleccionada (p.ej. "Ver orden interna →"
 * desde Verificaciones o Incidencias) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionListPage } from "../ordenEstacion/pages/OrdenEstacionListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { estaciones } from "../state/catalogosCache";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE, makeRow } from "./fixtures";

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
 *  para leer el catálogo "Producto Duración" — una instancia nueva por test. */
function conQueryClient(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// ADR-113 (fix): tras "Guardar" en el alta, la pantalla se queda en el mismo formulario
// (ADR-103, ahora en modo edición de la OE recién creada) — se mockean las llamadas reales
// que dispara `crearOE` (OrdenesContext.tsx) para poder probar esa transición sin red.
// ADR-210: `listarAudiosOrdenEstacionApi` también se mockea — el formulario la llama al
// CLONAR, para precargar el Material a Transmitir; `[]` por default (ninguna de las
// pruebas de este archivo necesita que SÍ clone audios, eso ya se cubre en
// `OrdenEstacionForm.test.tsx`).
vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    crearOrdenEstacionApi: vi.fn().mockResolvedValue({ orden_estacion_id: "oe-real-post-guardar" }),
    subirMaterialStagingApi: vi
      .fn()
      .mockResolvedValue({ ref: "orden_estacion/audios/abc_uno.mp3", nombre_archivo: "uno.mp3" }),
    listarAudiosOrdenEstacionApi: vi.fn().mockResolvedValue([]),
  };
});
vi.mock("../adapters/refrescar", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/refrescar")>();
  return {
    ...actual,
    refrescarOrdenEstacion: vi.fn().mockImplementation(async () =>
      makeOE({
        id: "oe-real-post-guardar",
        folio_orden_interna: "OE-2026-9999A",
        periodo_transmision: [
          makeRow({ orden_estacion_dia_id: "dia-real-post-guardar", fecha: "2026-10-05", hora_inicio: "07:00", hora_termino: "07:00", spots_diarios: 5 }),
        ],
      }),
    ),
    refrescarOrdenCliente: vi.fn().mockImplementation(async (id: string) => makeOC({ id })),
  };
});

estaciones.push({ id: "es1", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-AM", frecuencia: "900 AM", tipo_senal: "fm" });

function renderPage(oeIdPreseleccionada?: string) {
  const oc = makeOC({ id: "oc-1" });
  const oe1 = makeOE({ id: "oe-1", folio_orden_interna: "OE-2026-0054A", orden_id: oc.id });
  const oe2 = makeOE({ id: "oe-2", folio_orden_interna: "OE-2026-0054B", orden_id: oc.id });
  const utils = render(
    conQueryClient(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [oe1, oe2], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage oeIdPreseleccionada={oeIdPreseleccionada} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
    ),
  );
  const tabla = utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("ADR-210 (manera 2, petición del usuario): columna 'Acciones' con 'Clonar' en la tabla, solo en 2.1", () => {
  it("el botón '📋 Clonar' solo aparece en renglones en 2.1 'Asignada al afiliado'", () => {
    const oc = makeOC({ id: "oc-1" });
    const asignada = makeOE({ id: "oe-asig", folio_orden_interna: "OE-2026-0070A", orden_id: oc.id, estatus: "asignada_afiliado" });
    const programada = makeOE({ id: "oe-prog", folio_orden_interna: "OE-2026-0071A", orden_id: oc.id, estatus: "programados_conciliados" });
    const { tabla } = (() => {
      const utils = render(
        conQueryClient(
          <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [asignada, programada], incidencias: [], historialComisiones: [] }}>
            <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
          </OrdenesProvider>,
        ),
      );
      return { tabla: utils.container.querySelector("table") as HTMLTableElement };
    })();

    const filaAsignada = within(tabla).getByText("OE-2026-0070A").closest("tr") as HTMLElement;
    const filaProgramada = within(tabla).getByText("OE-2026-0071A").closest("tr") as HTMLElement;
    expect(within(filaAsignada).getByRole("button", { name: "📋 Clonar" })).toBeInTheDocument();
    expect(within(filaProgramada).queryByRole("button", { name: "📋 Clonar" })).toBeNull();
  });

  it("clonar desde la tabla lleva al alta precargada, sin seleccionar la fila (sin activar edición)", () => {
    const { tabla, container } = renderPage();

    const filaClonar = within(tabla).getByText("OE-2026-0054A").closest("tr") as HTMLElement;
    fireEvent.click(within(filaClonar).getByRole("button", { name: "📋 Clonar" }));

    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-0054A)")).toBeInTheDocument();
    // Estación sigue editable (no es modo edición) — a diferencia de "Editar", que la
    // deshabilita (`disabled={isEdit}` en `OrdenEstacionForm.tsx`).
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación")).not.toBeDisabled();
  });

  it("fix: 'Cancelar' tras clonar desde la tabla se queda en 'Órdenes de Transmisión' (no navega a Órdenes de Servicio)", () => {
    const oc = makeOC({ id: "oc-1" });
    const asignada = makeOE({ id: "oe-asig", folio_orden_interna: "OE-2026-0070A", orden_id: oc.id, estatus: "asignada_afiliado" });
    const onVerOC = vi.fn();
    const { container } = render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [asignada], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage onVerOC={onVerOC} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const tabla = container.querySelector("table") as HTMLTableElement;
    const fila = within(tabla).getByText("OE-2026-0070A").closest("tr") as HTMLElement;
    fireEvent.click(within(fila).getByRole("button", { name: "📋 Clonar" }));
    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2026-0070A)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    // A diferencia de "+ Nueva Orden de Transmisión"/"+ Asignar estaciones" (que sí vienen
    // de Órdenes de Servicio y regresan ahí), clonar desde ESTA lista nunca estuvo en esa
    // pantalla — "Cancelar" debe quedarse aquí mismo.
    expect(onVerOC).not.toHaveBeenCalled();
    expect(screen.getByText("Órdenes de Transmisión")).toBeInTheDocument();
    expect(screen.queryByText("Nueva Orden de Transmisión (clonada de OE-2026-0070A)")).toBeNull();
  });
});

describe("ADR-139 (corrige un bug real): cambiar de OE seleccionada resetea el panel de detalle", () => {
  it("un diálogo de PDF abierto en la OE anterior no sigue abierto al seleccionar otra OE", async () => {
    const { tabla } = renderPage();

    fireEvent.click(within(tabla).getByText("OE-2026-0054A"));
    fireEvent.click(await screen.findByText(/PDF #1 · Orden de servicio/));
    expect(screen.getByText("🖨️ Imprimir")).toBeInTheDocument();

    fireEvent.click(within(tabla).getByText("OE-2026-0054B"));
    // Sin `key={oe.id}` en <OrdenEstacionDetailPanel>, React reutiliza la misma
    // instancia (y su estado local `abierto`) — el diálogo de la OE anterior seguiría
    // visible aquí, aunque nunca se le dio clic para esta OE.
    expect(screen.queryByText("🖨️ Imprimir")).toBeNull();
  });
});

describe("Fix: OI preseleccionada filtra la tabla (no solo resalta la fila)", () => {
  it("sin preselección, se ven todas las OI", () => {
    const { tabla } = renderPage();
    expect(within(tabla).getByText("OE-2026-0054A")).toBeInTheDocument();
    expect(within(tabla).getByText("OE-2026-0054B")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });

  it("con una OI preseleccionada, el buscador arranca con su folio y la tabla muestra solo esa fila", () => {
    const { tabla } = renderPage("oe-2");

    const buscador = screen.getByPlaceholderText("Buscar folio, estación, afiliado, OC de origen…");
    expect((buscador as HTMLInputElement).value).toBe("OE-2026-0054B");

    expect(within(tabla).getByText("OE-2026-0054B")).toBeInTheDocument();
    expect(within(tabla).queryByText("OE-2026-0054A")).toBeNull();
    expect(screen.getByText("1 de 2")).toBeInTheDocument();
  });
});

describe("Fix: la tabla muestra columna Fecha y ordena de la más reciente a la más antigua", () => {
  it("una OI dada de alta después aparece primero, sin importar el orden en que llegaron los datos", () => {
    const oc = makeOC({ id: "oc-1" });
    const vieja = makeOE({ id: "oe-vieja", folio_orden_interna: "OE-2026-0041A", orden_id: oc.id, created_at: "2026-01-01" });
    const nueva = makeOE({ id: "oe-nueva", folio_orden_interna: "OE-2026-0050A", orden_id: oc.id, created_at: "2026-06-15" });
    const utils = render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [vieja, nueva], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;

    expect(within(tabla).getByText("Fecha")).toBeInTheDocument();
    const filas = within(tabla).getAllByRole("row").slice(1); // sin el encabezado
    expect(within(filas[0]).getByText("OE-2026-0050A")).toBeInTheDocument();
    expect(within(filas[0]).getByText("2026-06-15")).toBeInTheDocument();
    expect(within(filas[1]).getByText("OE-2026-0041A")).toBeInTheDocument();
  });

  it("fix: con dos OI del MISMO día (empate en `created_at`, sin hora), la que va primero en el arreglo queda primero en la tabla", () => {
    // `created_at` se trunca a solo fecha (sin hora) al leer del backend, así que dos OI
    // dadas de alta el mismo día EMPATAN en el sort — el orden entre ellas lo decide el
    // orden ya existente en `state.ordenesEstacion` (sort estable). Por eso el reducer
    // (`REEMPLAZAR_OE`, OrdenesContext.tsx) agrega las OE nuevas AL FRENTE del arreglo:
    // así, al desempatar, la recién creada queda primero.
    const oc = makeOC({ id: "oc-1" });
    const recienCreada = makeOE({ id: "oe-nueva", folio_orden_interna: "OE-2026-0060A", orden_id: oc.id, created_at: "2026-09-11" });
    const yaExistia = makeOE({ id: "oe-vieja", folio_orden_interna: "OE-2026-0059A", orden_id: oc.id, created_at: "2026-09-11" });
    const utils = render(
      conQueryClient(
        <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [recienCreada, yaExistia], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
        </OrdenesProvider>,
      ),
    );
    const tabla = utils.container.querySelector("table") as HTMLTableElement;
    const filas = within(tabla).getAllByRole("row").slice(1);
    expect(within(filas[0]).getByText("OE-2026-0060A")).toBeInTheDocument();
    expect(within(filas[1]).getByText("OE-2026-0059A")).toBeInTheDocument();
  });
});

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

  // Selector por `accept` (no por posición) — ".mp3" en `accept` solo lo trae este input.
  const inputAudio = container.querySelector(
    'input[type="file"][accept*=".mp3"]',
  ) as HTMLInputElement;
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
  const inputAudio = container.querySelector('input[type="file"][accept*=".mp3"]') as HTMLInputElement;
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
    expect(screen.getAllByText("OE-2026-9999A").length).toBeGreaterThan(0);
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
