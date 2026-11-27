/** Qué ve cada área en el explorador de F4: Dirección ve "Estado de resultados" (y
 * carga sus datos); un área sin ninguna clave `reportes_*` vigente en Tanda 1 (aquí
 * forzamos una no contemplada) ve el estado vacío explícito, no una pantalla rota.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { currentUser } from "@/shared/lib/currentUser";

import { ReportesExplorerPage } from "../pages/ReportesExplorerPage";
import type {
  DashboardCobranzaRead,
  DashboardComercialRead,
  DashboardOperativoRead,
  EstadoResultadosRead,
} from "../types";

const { periodoDemo } = vi.hoisted(() => ({
  periodoDemo: {
    periodo: "2026-11",
    en_curso: true,
    ingresos_facturado: "10000.00",
    ingresos_cobrado: "8000.00",
    costos_afiliados: { facturado: "3000.00", pagado: "3000.00" },
    costos_agencias: { facturado: "0.00", pagado: "0.00" },
    costos_comisiones_vendedores: { facturado: "500.00", pagado: "500.00" },
    costo_comisiones_agencias_pagado: "0.00",
    costo_nominas: "1000.00",
    costo_overhead: "200.00",
    utilidad_bruta: "4500.00",
    utilidad_neta: "3300.00",
    margen_bruto_pct: "56.25",
    margen_neto_pct: "41.25",
    pct_cobranza: "80.00",
    costo_afiliados_pct_cobrado: "37.50",
  },
}));

vi.mock("../api", () => ({
  reportesApi: {
    estadoResultados: vi.fn().mockResolvedValue({
      actual: periodoDemo,
      anterior: periodoDemo,
      tendencia: {
        ingresos_cobrado_pct: "5.0",
        utilidad_bruta_pct: "2.0",
        utilidad_neta_pct: "1.0",
      },
      historico: [periodoDemo],
    } satisfies EstadoResultadosRead),
    exportarEstadoResultados: vi.fn(),
    dashboardComercial: vi.fn().mockResolvedValue({
      ventana: "mes",
      periodo: "2026-11",
      desde: "2026-11-01",
      hasta: "2026-12-01",
      ventas_total: "1000.00",
      ordenes_total: 1,
      ticket_promedio: "1000.00",
      comisiones_vendedores_total: "100.00",
      anunciantes_con_ventas: 1,
      top_vendedores: [],
      top_anunciantes: [],
      top_categorias: [],
      top_agencias: [],
      evolucion_mensual: [],
    } satisfies DashboardComercialRead),
    exportarDashboardComercial: vi.fn(),
    dashboardCobranza: vi.fn().mockResolvedValue({
      fecha_corte: "2026-11-26",
      mes_cobrado: "2026-11",
      ventana_dso_dias: 90,
      total_por_cobrar: "0",
      total_vencido: "0",
      total_facturas: 0,
      dso_promedio: null,
      cobrado_mes: "0",
      aging: [],
      por_anunciante: [],
      evolucion_mensual: [],
    } satisfies DashboardCobranzaRead),
    exportarDashboardCobranza: vi.fn(),
    dashboardOperativo: vi.fn().mockResolvedValue({
      ventana: "mes",
      periodo: "2026-11",
      desde: "2026-11-01",
      hasta: "2026-12-01",
      cumplimiento_general_pct: "98.50",
      spots_ordenados_total: 200,
      spots_transmitidos_total: 197,
      incidencias_total: 0,
      afiliados_activos: 0,
      cumplimiento_por_estacion: [],
      incidencias_por_afiliado: [],
      composicion_incidencias: [],
    } satisfies DashboardOperativoRead),
    exportarDashboardOperativo: vi.fn(),
  },
}));

function renderExplorer() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReportesExplorerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReportesExplorerPage — RBAC por área", () => {
  const areaOriginal = currentUser.area;

  afterEach(() => {
    currentUser.area = areaOriginal;
  });

  it("Dirección ve 'Estado de resultados' y carga sus datos", async () => {
    currentUser.area = "direccion";
    renderExplorer();

    expect(screen.getAllByText("Estado de resultados").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText(/Noviembre 2026/)).toBeInTheDocument();
    });
  });

  it("un área sin ninguna vista permitida ve el estado vacío, no una pantalla rota", () => {
    currentUser.area = "nominas_sin_reportes_demo";
    renderExplorer();

    expect(screen.queryByText("Estado de resultados")).not.toBeInTheDocument();
    expect(screen.getByText(/no tiene acceso a ningún reporte/i)).toBeInTheDocument();
  });

  it("Ventas ve 'Comercial' y 'Operativo', nunca Estado de resultados ni Cobranza", async () => {
    currentUser.area = "ventas";
    renderExplorer();

    expect(screen.queryByText("Estado de resultados")).not.toBeInTheDocument();
    expect(screen.queryByText("Cobranza")).not.toBeInTheDocument();
    expect(screen.getAllByText("Comercial").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Operativo").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText("Dashboard comercial")).toBeInTheDocument();
    });
  });

  it("Tesorería ve 'Cobranza' y 'Operativo', nunca Estado de resultados ni Comercial", async () => {
    currentUser.area = "tesoreria";
    renderExplorer();

    expect(screen.queryByText("Estado de resultados")).not.toBeInTheDocument();
    expect(screen.queryByText("Comercial")).not.toBeInTheDocument();
    expect(screen.getAllByText("Cobranza").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Operativo").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText("Dashboard de cobranza")).toBeInTheDocument();
    });
  });

  it("Nóminas solo ve 'Operativo' — es la única área sin ningún otro dashboard de F4", async () => {
    currentUser.area = "nominas";
    renderExplorer();

    expect(screen.queryByText("Estado de resultados")).not.toBeInTheDocument();
    expect(screen.queryByText("Comercial")).not.toBeInTheDocument();
    expect(screen.queryByText("Cobranza")).not.toBeInTheDocument();
    expect(screen.getAllByText("Operativo").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText("Dashboard operativo")).toBeInTheDocument();
    });
  });
});
