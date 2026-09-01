/** Pruebas de la pantalla de Facturas al cliente (F2).
 *
 * Lo que se cubre es lo que la UI DECIDE, no lo que el backend ya valida: qué acciones se
 * ofrecen en cada estado de la máquina. Ofrecer un botón que el servidor va a rechazar con
 * 409 es un error de la pantalla, y esto lo detecta.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FacturasClientePage } from "../facturaCliente/pages/FacturasClientePage";
import type { FacturaCliente } from "../types";

const listMock = vi.fn();
const porFacturarMock = vi.fn();

vi.mock("../api", () => ({
  facturaClienteApi: {
    list: (params: unknown) => listMock(params),
    create: vi.fn(),
    enviarATimbrado: vi.fn(),
    timbrar: vi.fn(),
    entregar: vi.fn(),
    cancelar: vi.fn(),
    descargarArchivoPlano: vi.fn(),
  },
  adjuntosFacturacionApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
  ordenesPorFacturar: (params: unknown) => porFacturarMock(params),
  ordenesFacturables: vi.fn().mockResolvedValue([]),
  cuentasContables: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  afiliadosActivos: vi.fn().mockResolvedValue([]),
  agenciasActivas: vi.fn().mockResolvedValue([]),
  facturaAfiliadoApi: {},
  facturaAgenciaApi: {},
  costoApi: {},
}));

const base: FacturaCliente = {
  factura_id: "f-1",
  numero_factura: "A-1041",
  numero_pedido: null,
  referencia_adicional: null,
  orden_id: "oc-1",
  empresa_facturadora_id: "e-1",
  anunciante_id: "an-1",
  agencia_id: null,
  razon_social_facturacion: "Agencia Uno SA de CV",
  rfc_facturacion: "AGU900101AB1",
  direccion_facturacion: null,
  descripcion_factura: "Servicios de transmisión",
  observaciones_factura: null,
  fecha_inicio_transmision: "2026-02-01",
  fecha_fin_transmision: "2026-02-28",
  fecha_factura: "2026-03-01",
  fecha_entrega_factura: null,
  subtotal_factura: "10000.00",
  iva_factura: "1600.00",
  total_factura: "11600.00",
  cuenta_contable_id: "cc-1",
  metodo_pago_clave: "PUE",
  info_cuenta_pago: null,
  layout_factura: null,
  estado_facturacion: "preparada",
  folio_fiscal_sat: null,
  fecha_timbrado: null,
  serie_timbrado: null,
  xml_path: null,
  pdf_path: null,
  created_by: "u-1",
  created_at: "2026-03-01T10:00:00",
  updated_at: null,
  empresa_facturadora: "OIR Comercial",
  folio_orden: "OC-2026-0041",
  facturas_relacionadas_ids: [],
};

function renderCon(factura: FacturaCliente, onIrAListasParaFacturar: () => void = vi.fn()) {
  listMock.mockResolvedValue({ items: [factura], total: 1, page: 1, size: 20, pages: 1 });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FacturasClientePage onIrAListasParaFacturar={onIrAListasParaFacturar} />
    </QueryClientProvider>,
  );
}

describe("FacturasClientePage", () => {
  beforeEach(() => {
    listMock.mockReset();
    porFacturarMock.mockReset();
    porFacturarMock.mockResolvedValue({ items: [], total: 1, page: 1, size: 1, pages: 1 });
  });

  it("lista las facturas con su total en pesos y su estado legible", async () => {
    renderCon(base);
    expect(await screen.findByText("A-1041")).toBeInTheDocument();
    expect(screen.getAllByText("Preparada").length).toBeGreaterThan(0);
    // El monto llega como string decimal y se muestra como moneda MXN.
    expect(screen.getByText(/\$11,600\.00/)).toBeInTheDocument();
  });

  it("fix: muestra el folio de la orden del cliente en el header del detalle", async () => {
    renderCon(base);
    (await screen.findByText("A-1041")).click();
    expect(await screen.findByText("OC-2026-0041")).toBeInTheDocument();
  });

  it("sin folio de orden (dato huérfano), no revienta y simplemente no muestra el badge", async () => {
    renderCon({ ...base, folio_orden: null });
    (await screen.findByText("A-1041")).click();
    await waitFor(() => expect(screen.getByText("Agencia Uno SA de CV")).toBeInTheDocument());
    expect(screen.queryByText("OC-2026-0041")).not.toBeInTheDocument();
  });

  it("en 'preparada' ofrece enviar a timbrado, pero NO registrar timbrado", async () => {
    renderCon(base);
    (await screen.findByText("A-1041")).click();
    await waitFor(() => expect(screen.getByText("Marcar enviada a timbrado →")).toBeInTheDocument());
    expect(screen.queryByText("Registrar respuesta del timbrado →")).not.toBeInTheDocument();
    expect(screen.queryByText("Marcar entregada")).not.toBeInTheDocument();
  });

  it("en 'enviada_a_timbrado' ofrece registrar el timbrado", async () => {
    renderCon({ ...base, estado_facturacion: "enviada_a_timbrado" });
    (await screen.findByText("A-1041")).click();
    await waitFor(() => expect(screen.getByText("Registrar respuesta del timbrado →")).toBeInTheDocument());
    expect(screen.queryByText("Marcar enviada a timbrado →")).not.toBeInTheDocument();
  });

  it("fix: registra el timbrado con folio y fecha desde el formulario de pantalla completa (antes un modal roto)", async () => {
    const { facturaClienteApi } = await import("../api");
    vi.mocked(facturaClienteApi.timbrar).mockResolvedValue({
      ...base,
      estado_facturacion: "timbrada",
      folio_fiscal_sat: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
      fecha_timbrado: "2026-03-05",
    });
    const { container } = renderCon({ ...base, estado_facturacion: "enviada_a_timbrado" });
    (await screen.findByText("A-1041")).click();
    (await screen.findByText("Registrar respuesta del timbrado →")).click();

    expect(await screen.findByText("Registrar timbrado")).toBeInTheDocument();
    const folioInput = container.querySelector(
      'input[placeholder="A1B2C3D4-E5F6-7890-ABCD-EF1234567890"]',
    ) as HTMLInputElement;
    fireEvent.change(folioInput, { target: { value: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890" } });
    screen.getByText("Registrar timbrado").click();

    await waitFor(() =>
      expect(facturaClienteApi.timbrar).toHaveBeenCalledWith(
        "f-1",
        expect.objectContaining({ folio_fiscal_sat: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890" }),
      ),
    );
    // Al confirmar, vuelve a la vista normal de la factura (ya no muestra el formulario).
    expect(await screen.findByText("Marcar entregada →")).toBeInTheDocument();
  });

  it("fix: sin capturar el folio, no permite registrar el timbrado", async () => {
    renderCon({ ...base, estado_facturacion: "enviada_a_timbrado" });
    (await screen.findByText("A-1041")).click();
    (await screen.findByText("Registrar respuesta del timbrado →")).click();

    (await screen.findByText("Registrar timbrado")).click();
    expect(await screen.findByText(/El folio fiscal.*es obligatorio/)).toBeInTheDocument();
  });

  it("una factura cancelada no ofrece ninguna transición", async () => {
    renderCon({ ...base, estado_facturacion: "cancelada" });
    (await screen.findByText("A-1041")).click();
    await waitFor(() =>
      expect(screen.getByText(/Archivo plano/)).toBeInTheDocument(),
    );
    for (const accion of [
      "Marcar enviada a timbrado →",
      "Registrar respuesta del timbrado →",
      "Marcar entregada →",
      "Cancelar",
    ]) {
      expect(screen.queryByText(accion)).not.toBeInTheDocument();
    }
  });

  it("al exportar avisa si el archivo salió incompleto para el PAC", async () => {
    const { facturaClienteApi } = await import("../api");
    vi.mocked(facturaClienteApi.descargarArchivoPlano).mockResolvedValue([
      "Detalle.ClaveProdServ",
      "AGREGADOS.UsoCFDI",
    ]);
    renderCon(base);
    (await screen.findByText("A-1041")).click();
    (await screen.findByText(/Archivo plano/)).click();

    // El aviso es explícito: un archivo incompleto que se envíe al PAC será rechazado.
    expect(await screen.findByText(/INCOMPLETO/)).toBeInTheDocument();
    expect(screen.getByText(/Detalle.ClaveProdServ/)).toBeInTheDocument();
  });

  it("fix: el botón del header navega a «Listas para facturar» en vez de abrir un formulario aquí", async () => {
    const onIr = vi.fn();
    renderCon(base, onIr);
    const boton = await screen.findByText("+ Generar factura desde orden cerrada");
    await waitFor(() => expect(boton).not.toBeDisabled());
    boton.click();
    expect(onIr).toHaveBeenCalledTimes(1);
    // Ya no existe un formulario de alta embebido en esta pantalla.
    expect(screen.queryByLabelText(/Orden/)).not.toBeInTheDocument();
  });

  it("fix: el botón del header se inhabilita cuando ya no hay órdenes por facturar", async () => {
    porFacturarMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 1 });
    renderCon(base);
    await waitFor(() =>
      expect(screen.getByText("+ Generar factura desde orden cerrada")).toBeDisabled(),
    );
  });

  it("si el archivo está completo lo dice, sin alarmar", async () => {
    const { facturaClienteApi } = await import("../api");
    vi.mocked(facturaClienteApi.descargarArchivoPlano).mockResolvedValue([]);
    renderCon(base);
    (await screen.findByText("A-1041")).click();
    (await screen.findByText(/Archivo plano/)).click();

    expect(await screen.findByText(/Archivo generado y completo/)).toBeInTheDocument();
  });
});
