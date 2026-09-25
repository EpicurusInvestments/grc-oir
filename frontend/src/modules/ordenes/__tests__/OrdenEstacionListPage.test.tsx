/** Fix: llegar a "Órdenes internas" con una OI preseleccionada (p.ej. "Ver orden interna →"
 * desde Verificaciones o Incidencias) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio.
 */

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionListPage } from "../ordenEstacion/pages/OrdenEstacionListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { estaciones } from "../state/catalogosCache";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE, makeRow } from "./fixtures";

// ADR-113 (fix): tras "Guardar" en el alta, la pantalla se queda en el mismo formulario
// (ADR-103, ahora en modo edición de la OE recién creada) — se mockean las llamadas reales
// que dispara `crearOE` (OrdenesContext.tsx) para poder probar esa transición sin red.
vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    crearOrdenEstacionApi: vi.fn().mockResolvedValue({ orden_estacion_id: "oe-real-post-guardar" }),
    subirMaterialStagingApi: vi
      .fn()
      .mockResolvedValue({ ref: "orden_estacion/audios/abc_uno.mp3", nombre_archivo: "uno.mp3" }),
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
    <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [oe1, oe2], incidencias: [], historialComisiones: [] }}>
      <OrdenEstacionListPage oeIdPreseleccionada={oeIdPreseleccionada} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
    </OrdenesProvider>,
  );
  const tabla = utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

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
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [vieja, nueva], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
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
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [recienCreada, yaExistia], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
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
  fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
  fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
  fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
  fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });

  // Selector por `accept` (no por posición): "Reporte del afiliado" también es un
  // input[type="file"] en el mismo formulario — ".mp3" en `accept` solo lo trae este.
  const inputAudio = container.querySelector(
    'input[type="file"][accept*=".mp3"]',
  ) as HTMLInputElement;
  fireEvent.change(inputAudio, { target: { files: [new File(["contenido"], "uno.mp3", { type: "audio/mpeg" })] } });
  await waitFor(() => expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull());

  fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));
  const spotsInputs = container.querySelectorAll('input[type="number"]');
  fireEvent.change(spotsInputs[spotsInputs.length - 1], { target: { value: "5" } });
}

describe("ADR-116: tras 'Guardar' en el alta, pregunta si se quiere generar otra Orden de Transmisión", () => {
  it("al guardar aparece el modal de confirmación (no pasa directo a edición, ADR-103 ya no aplica)", async () => {
    const oc = makeOC({ id: "oc-1" });
    render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
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
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
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
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={vi.fn()} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
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

  it("'Cancelar' en el alta regresa a Órdenes de Servicio (la OC elegida), no a la lista de Transmisión", async () => {
    const oc = makeOC({ id: "oc-1" });
    const onVerOC = vi.fn();
    render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionListPage ocIdParaNueva={oc.id} onVerOC={onVerOC} onVerVerificacion={vi.fn()} />
      </OrdenesProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onVerOC).toHaveBeenCalledWith(oc.id);
  });
});
