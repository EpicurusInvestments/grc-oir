/** Pruebas de la bandeja "Listas para facturar" (F2).
 *
 * Cubre lo que decide la pantalla: que muestra la tarjeta con los datos ya resueltos por
 * el backend, que el estado vacío es el del mockup, y que «Generar factura →» abre el
 * formulario existente con la orden FIJA (sin selector) — que es el punto de la bandeja.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ListasParaFacturarPage } from "../facturaCliente/pages/ListasParaFacturarPage";
import type { OrdenPorFacturar } from "../types";

const porFacturarMock = vi.fn();
const facturaListMock = vi.fn();

vi.mock("../api", () => ({
  ordenesPorFacturar: (p: unknown) => porFacturarMock(p),
  facturaClienteApi: {
    list: (p: unknown) => facturaListMock(p),
    create: vi.fn(),
    enviarATimbrado: vi.fn(),
    timbrar: vi.fn(),
    entregar: vi.fn(),
    cancelar: vi.fn(),
    descargarArchivoPlano: vi.fn(),
  },
  ordenesFacturables: vi.fn().mockResolvedValue([]),
  cuentasContables: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  afiliadosActivos: vi.fn().mockResolvedValue([]),
  agenciasActivas: vi.fn().mockResolvedValue([]),
  facturaAfiliadoApi: {},
  facturaAgenciaApi: {},
  costoApi: {},
}));

const orden: OrdenPorFacturar = {
  orden_id: "oc-11",
  folio_orden: "OC-2025-0051",
  numero_orden_cliente: "LALA-YOG-11",
  anunciante_id: "an-11",
  anunciante: "OXXO",
  agencia: null,
  vendedor: "Patricia Méndez",
  producto: "Yoghurt Lala Bebible 900ml",
  fecha_inicio_campania: "2025-06-01",
  fecha_fin_campania: "2025-06-30",
  subtotal: "504000.00",
  total: "584640.00",
  empresa_emisora: "OIR Comercial",
  total_spots: 60,
  duracion_spot: "30s",
  facturacion_directa_cliente: true,
  receptor_razon_social: "Cadena Comercial OXXO SA de CV",
  receptor_rfc: "CCO8605231N4",
  receptor_direccion: "CDMX, Insurgentes Sur 800",
};

function renderCon(items: OrdenPorFacturar[]) {
  porFacturarMock.mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    size: 20,
    pages: 1,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ListasParaFacturarPage />
    </QueryClientProvider>,
  );
}

describe("ListasParaFacturarPage", () => {
  beforeEach(() => {
    porFacturarMock.mockReset();
    facturaListMock.mockReset();
    facturaListMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 });
  });

  it("muestra la orden pendiente con los datos ya resueltos por el backend", async () => {
    renderCon([orden]);
    expect(await screen.findByText("OC-2025-0051")).toBeInTheDocument();
    expect(screen.getByText("OXXO")).toBeInTheDocument();
    // Sin agencia se rotula "Trato directo", no un guion suelto.
    expect(screen.getByText(/Trato directo/)).toBeInTheDocument();
    expect(screen.getByText(/\$584,640\.00/)).toBeInTheDocument();
  });

  it("sin pendientes muestra el estado vacío del mockup", async () => {
    renderCon([]);
    expect(
      await screen.findByText(/No hay órdenes pendientes de facturar/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Todas las órdenes cerradas ya tienen factura generada/),
    ).toBeInTheDocument();
  });

  it("«Generar factura →» abre el formulario con la orden FIJA, sin selector", async () => {
    renderCon([orden]);
    (await screen.findByText("Generar factura →")).click();

    await waitFor(() =>
      expect(screen.getByText(/Nueva factura · OC-2025-0051/)).toBeInTheDocument(),
    );
    // El formulario abre con el bloque de datos heredados y SIN selector de orden: la
    // orden ya está decidida por la tarjeta desde la que se entró.
    expect(screen.getByText("Datos heredados de la orden")).toBeInTheDocument();
    expect(screen.getByText("OC-2025-0051")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Busca por folio o número/)).not.toBeInTheDocument();
    // Y la descripción viene pre-cargada, como en la pantalla aprobada.
    expect(screen.getByDisplayValue(/Servicios de transmisión publicitaria/)).toBeInTheDocument();
  });

  it('"Factura relacionada" se filtra por el anunciante de la orden y admite varias (ADR-062)', async () => {
    facturaListMock.mockResolvedValue({
      items: [
        { factura_id: "f-1", numero_factura: "A-1010", estado_facturacion: "timbrada" },
        { factura_id: "f-2", numero_factura: "A-1020", estado_facturacion: "cancelada" },
      ],
      total: 2,
      page: 1,
      size: 100,
      pages: 1,
    });

    renderCon([orden]);
    (await screen.findByText("Generar factura →")).click();
    await waitFor(() =>
      expect(screen.getByText(/Nueva factura · OC-2025-0051/)).toBeInTheDocument(),
    );

    const buscador = await screen.findByPlaceholderText(/Busca por número de factura/);
    fireEvent.focus(buscador);

    // Se pidieron filtradas por el anunciante de la ORDEN (no todas las del sistema).
    await waitFor(() =>
      expect(facturaListMock).toHaveBeenCalledWith({ anunciante_id: "an-11", size: 100 }),
    );

    fireEvent.mouseDown(await screen.findByText("A-1010 · Timbrada"));
    fireEvent.mouseDown(await screen.findByText("A-1020 · Cancelada"));

    // Ambas quedan seleccionadas como chips — incluida la cancelada, que es justo el
    // control que pidió negocio (ver que una factura del cliente se canceló).
    expect(screen.getByText("A-1010 · Timbrada")).toBeInTheDocument();
    expect(screen.getByText("A-1020 · Cancelada")).toBeInTheDocument();
  });
});
