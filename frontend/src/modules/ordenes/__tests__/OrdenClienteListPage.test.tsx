/** Fix: llegar a "Órdenes del cliente" con una OC preseleccionada (p.ej. "Ver OC →" desde
 * el detalle de una orden interna) debe filtrar la tabla a esa sola fila, no solo
 * resaltarla entre todas — el buscador arranca con su folio (mismo fix que
 * OrdenEstacionListPage.tsx para "Ver orden interna →").
 *
 * ADR-285 (petición del usuario, con captura): la tabla ahora pagina/busca contra el
 * backend (`paginaOrdenesClienteApi`) en vez de traer el 100% de las órdenes — se
 * mockea esa llamada en vez de precargar `OrdenesProvider` con el arreglo completo. El
 * orden "más reciente primero" ya NO lo decide el frontend (se quitó su propio
 * `.sort()`): lo decide el `default_order_by` del backend — cubierto por
 * `test_listado_ordena_por_fecha_de_creacion_mas_reciente_primero` en
 * `test_f1_03_ordenes_lectura.py`, no aquí.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenClienteListPage } from "../ordenCliente/pages/OrdenClienteListPage";
import { OrdenesProvider } from "../state/OrdenesContext";
import { makeOC, makeOCDTO } from "./fixtures";

// ADR-208: el detalle de OrdenCliente ahora pide su FacturaCliente (React Query) —
// mismo mock que OrdenClienteDetailPanel.test.tsx (ninguna OC de este archivo llega a
// "facturada", así que no se usa de verdad; solo evita "No QueryClient set").
vi.mock("@/modules/facturacion/api", () => ({
  facturaClienteApi: { list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 10, pages: 0 }) },
  adjuntosFacturacionApi: { ver: vi.fn(), verEnVisor: vi.fn() },
}));

const paginaMock = vi.fn();
const detalleMock = vi.fn();

vi.mock("../adapters/ordenesApi", () => ({
  paginaOrdenesClienteApi: (params: { q?: string }) => paginaMock(params),
  oesDeLaOCApi: vi.fn().mockResolvedValue([]),
  listarDiasOrdenEstacionApi: vi.fn().mockResolvedValue([]),
  listarVerificacionesApi: vi.fn().mockResolvedValue([]),
  listarHistorialComisionesApi: vi.fn().mockResolvedValue([]),
  paginaOrdenesEstacionApi: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
  paginaIncidenciasApi: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
}));

vi.mock("../adapters/refrescar", () => ({
  refrescarOrdenCliente: (id: string) => detalleMock(id),
  refrescarOrdenEstacion: vi.fn(),
}));

function renderPage(ocIdPreseleccionada?: string) {
  const oc1DTO = makeOCDTO({ orden_id: "oc-1", folio_orden: "OC-2026-0041" });
  const oc2DTO = makeOCDTO({ orden_id: "oc-2", folio_orden: "OC-2026-0042" });
  const oc1 = makeOC({ id: "oc-1", folio_orden: "OC-2026-0041" });
  const oc2 = makeOC({ id: "oc-2", folio_orden: "OC-2026-0042" });

  // La búsqueda (`q`) sí filtra — mismo criterio `ilike` que el backend real (ADR-285:
  // la tabla ya no filtra en el cliente, así que el mock necesita comportarse como la
  // consulta real para que las pruebas de "preselección filtra la tabla" sigan teniendo
  // sentido).
  paginaMock.mockImplementation(async (params: { q?: string }) => {
    const todas = [oc1DTO, oc2DTO];
    const filtradas = params.q ? todas.filter((o) => o.folio_orden.includes(params.q as string)) : todas;
    return { items: filtradas, total: filtradas.length, page: 1, size: 20, pages: 1 };
  });
  detalleMock.mockImplementation((id: string) => Promise.resolve(id === "oc-1" ? oc1 : oc2));

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <OrdenesProvider initialState={{ ordenesCliente: [], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenClienteListPage
          ocIdPreseleccionada={ocIdPreseleccionada}
          onSeleccionarOE={vi.fn()}
          onAsignarEstaciones={vi.fn()}
        />
      </OrdenesProvider>
    </QueryClientProvider>,
  );
  const tabla = () => utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("Fix: OC preseleccionada filtra la tabla (no solo resalta la fila)", () => {
  it("sin preselección, se ven todas las OC", async () => {
    const { tabla } = renderPage();
    await waitFor(() => expect(within(tabla()).getByText("OC-2026-41")).toBeInTheDocument());
    expect(within(tabla()).getByText("OC-2026-42")).toBeInTheDocument();
    expect(await screen.findByText("2 de 2")).toBeInTheDocument();
  });

  it("con una OC preseleccionada, el buscador arranca con su folio y la tabla muestra solo esa fila", async () => {
    const { tabla } = renderPage("oc-2");

    // El buscador arranca con el folio CRUDO (sin formatear) — es lo que de verdad
    // filtra contra el backend, el formateo (ADR-275) es solo de despliegue en la tabla.
    const buscador = await screen.findByPlaceholderText("Buscar folio, anunciante, no. de orden…");
    await waitFor(() => expect((buscador as HTMLInputElement).value).toBe("OC-2026-0042"));

    await waitFor(() => expect(within(tabla()).getByText("OC-2026-42")).toBeInTheDocument());
    expect(within(tabla()).queryByText("OC-2026-41")).toBeNull();
    expect(await screen.findByText("1 de 1")).toBeInTheDocument();
  });
});
