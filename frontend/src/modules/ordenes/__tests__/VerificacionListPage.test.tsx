/** Fix: la tabla de Verificaciones debe ordenar de la más reciente a la más antigua por
 * cuándo la OI llegó a 2.3 (`actualizadaEn`, ver `verificacionDerivada` en selectors.ts),
 * no por la fecha de transmisión que muestra la columna "Fecha" (que no cambia).
 *
 * ADR-285 (petición del usuario, con captura): la tabla pagina contra el backend
 * (`paginaOrdenesEstacionApi`, forzando `estatus: "cerrada"`) en vez de derivar sobre
 * `state.ordenesEstacion` completo — se mockea esa llamada (+ días/verificaciones por
 * fila) en vez de precargar `OrdenesProvider` con el arreglo completo. El reordenado por
 * `updated_at` sigue siendo responsabilidad del frontend (`useVerificacionesPagina`,
 * intra-página), por eso esta prueba sigue teniendo sentido aquí.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VerificacionListPage } from "../verificacion/pages/VerificacionListPage";
import { makeOEDTO, makeDiaDTO } from "./fixtures";

vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return { ...actual, listarIncidenciasDeOEApi: vi.fn().mockResolvedValue([]) };
});

vi.mock("../adapters/ordenesApi", () => ({
  paginaOrdenesEstacionApi: vi.fn(async (params: { q?: string; estatus?: string }) => {
    const todas = [
      makeOEDTO({
        orden_estacion_id: "oe-vieja",
        folio_orden_estacion: "OE-2026-0041A",
        estatus: "cerrada",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-02T00:00:00",
      }),
      makeOEDTO({
        orden_estacion_id: "oe-nueva",
        folio_orden_estacion: "OE-2026-0050A",
        estatus: "cerrada",
        created_at: "2026-06-15T00:00:00",
        updated_at: "2026-06-15T00:00:00",
      }),
    ];
    const filtradas = params.q
      ? todas.filter((d) => d.folio_orden_estacion.includes(params.q as string))
      : todas;
    return { items: filtradas, total: filtradas.length, page: 1, size: 20, pages: 1 };
  }),
  paginaOrdenesClienteApi: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
  oesDeLaOCApi: vi.fn().mockResolvedValue([]),
  listarDiasOrdenEstacionApi: vi.fn(async (ordenEstacionId: string) => [
    makeDiaDTO({
      orden_estacion_id: ordenEstacionId,
      fecha_transmision: ordenEstacionId === "oe-vieja" ? "2026-01-01" : "2025-12-01",
    }),
  ]),
  listarVerificacionesApi: vi.fn().mockResolvedValue([]),
  listarHistorialComisionesApi: vi.fn().mockResolvedValue([]),
  paginaIncidenciasApi: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
}));

vi.mock("../adapters/refrescar", () => ({
  refrescarOrdenEstacion: vi.fn(),
  refrescarOrdenCliente: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <VerificacionListPage onVerOE={vi.fn()} />
    </QueryClientProvider>,
  );
  const tabla = () => utils.container.querySelector("table") as HTMLTableElement;
  return { ...utils, tabla };
}

describe("Fix: Verificaciones ordena por cuándo llegó a 2.3, más reciente primero", () => {
  it("una OI que llegó a 2.3 después aparece primero, aunque transmitió antes", async () => {
    const { tabla } = renderPage();

    await screen.findByText("OE-2026-50A");
    const filas = within(tabla()).getAllByRole("row").slice(1); // sin el encabezado
    expect(within(filas[0]).getByText("OE-2026-50A")).toBeInTheDocument();
    expect(within(filas[1]).getByText("OE-2026-41A")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
  });
});
