/** Facturas de vendedor (F2) — ADR nuevo (petición del usuario, con captura,
 * 2026-11-06), mismo cambio que para Facturas de agencia: la pantalla deja de mostrar
 * una sola "Orden relacionada" y pasa a mostrar la sección "Órdenes asignadas" (N:M vía
 * `FacturaVendedorOrden`), con la columna "Órdenes asig." homologada en la lista. Sin
 * campos legado `archivo_nombre`/`archivo_path`: esta entidad nace ya con PDF/XML por
 * separado.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FacturasVendedorPage } from "../facturaVendedor/pages/FacturasVendedorPage";
import type { FacturaVendedor, FacturaVendedorOrden } from "../types";

const listMock = vi.fn();
const ordenesMock = vi.fn();
const actualizarMock = vi.fn();
const cambiarEstatusMock = vi.fn();
const autorizarMock = vi.fn();

vi.mock("../api", () => ({
  facturaVendedorApi: {
    list: (params: unknown) => listMock(params),
    create: vi.fn(),
    actualizar: (id: string, data: unknown) => actualizarMock(id, data),
    ordenes: (id: string) => ordenesMock(id),
    ordenesFacturables: vi.fn().mockResolvedValue([]),
    cambiarEstatus: (...args: unknown[]) => cambiarEstatusMock(...args),
    autorizar: (...args: unknown[]) => autorizarMock(...args),
  },
  facturaAgenciaApi: {},
  facturaAfiliadoApi: {},
  facturaClienteApi: {},
  costoApi: {},
  adjuntosFacturacionApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
  ordenesPorFacturar: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 1 }),
  anunciantesFacturables: vi.fn().mockResolvedValue([]),
  ordenesFacturables: vi.fn().mockResolvedValue([]),
  cuentasContables: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  formasDePago: vi.fn().mockResolvedValue([]),
  afiliadosActivos: vi.fn().mockResolvedValue([]),
  agenciasActivas: vi.fn().mockResolvedValue([]),
  vendedoresActivos: vi.fn().mockResolvedValue([{ id: "vd-1", etiqueta: "Juan Pérez" }]),
}));

const base: FacturaVendedor = {
  factura_vendedor_id: "fv-1",
  vendedor_id: "vd-1",
  folio_factura_vendedor: "VEN-2025-0287",
  fecha_factura_vendedor: "2025-06-08",
  monto_factura_vendedor: "177480.00",
  iva_factura_vendedor: "28396.80",
  total_factura_vendedor: "205876.80",
  comision_vendedor: "177480.00",
  archivo_pdf_path: null,
  archivo_xml_path: null,
  estatus_factura_vendedor: "autorizada",
  created_by: "u-1",
  created_at: "2025-06-08T10:00:00",
  updated_at: null,
  vendedor: "Juan Pérez",
  ordenes_asignadas: 1,
};

const orden1: FacturaVendedorOrden = {
  id: "fvo-1",
  factura_vendedor_id: "fv-1",
  orden_id: "oc-1",
  porcentaje_comision_snap: "15.00",
  comision_calculada: "177480.00",
  folio_orden: "OC-2025-0041",
  numero_orden_cliente: "PO-BIMBO-0419",
  anunciante: "Grupo Bimbo",
  producto: "Pan Bimbo Integral 680g",
  orden_total: "1183200.00",
};

function renderCon(factura: FacturaVendedor) {
  listMock.mockResolvedValue({ items: [factura], total: 1, page: 1, size: 20, pages: 1 });
  ordenesMock.mockResolvedValue([orden1]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FacturasVendedorPage />
    </QueryClientProvider>,
  );
}

async function abrirDetalle(factura: FacturaVendedor) {
  const utils = renderCon(factura);
  (await screen.findByText(factura.folio_factura_vendedor as string)).click();
  await screen.findByText("Órdenes asignadas");
  await waitFor(() => expect(screen.queryByText("Cargando…")).toBeNull());
  return utils;
}

/** El total de la factura también aparece en la columna "Total" de la lista (misma
 *  fila, seleccionada) — se acota al panel de detalle, mismo criterio que en
 *  `FacturasAgenciaPage.test.tsx`. */
function panelDeDetalle(): HTMLElement {
  return document.querySelector(".detail-pane") as HTMLElement;
}

describe("FacturasVendedorPage — Órdenes asignadas (N:M)", () => {
  beforeEach(() => {
    listMock.mockReset();
    ordenesMock.mockReset();
    actualizarMock.mockReset();
    cambiarEstatusMock.mockReset();
    autorizarMock.mockReset();
  });

  it("el timeline muestra las 4 fases reales, en orden", async () => {
    const { container } = await abrirDetalle(base);
    const pasos = [...container.querySelectorAll(".tl-lbl")].map((el) => el.textContent);
    expect(pasos).toEqual(["Recibida", "En revisión", "Autorizada", "Pagada"]);
    const timeline = within(container.querySelector(".timeline") as HTMLElement);
    expect(timeline.getByText("Autorizada")).toBeInTheDocument();
  });

  it("la lista muestra Folio, Vendedor, Fecha, Subtotal, Total, Órdenes asig. y Estatus", async () => {
    await abrirDetalle(base);
    const celda = screen
      .getAllByText("VEN-2025-0287")
      .find((el) => el.closest("tr")) as HTMLElement;
    const fila = within(celda.closest("tr") as HTMLElement);
    expect(fila.getByText("Juan Pérez")).toBeInTheDocument();
    expect(fila.getByText("08/06/2025")).toBeInTheDocument();
    expect(fila.getByText("$177,480.00")).toBeInTheDocument();
    expect(fila.getByText("$205,876.80")).toBeInTheDocument();
    expect(fila.getByText("1")).toBeInTheDocument();
    expect(fila.getByText("Autorizada")).toBeInTheDocument();
  });

  it("muestra las tarjetas Subtotal/IVA/Total", async () => {
    await abrirDetalle(base);
    const panel = within(panelDeDetalle());
    expect(panel.getByText("Subtotal")).toBeInTheDocument();
    expect(panel.getAllByText("$177,480.00").length).toBe(2);
    expect(panel.getByText("$28,396.80")).toBeInTheDocument();
    expect(panel.getByText("$205,876.80")).toBeInTheDocument();
  });

  it("la sección 'Órdenes asignadas' muestra folio, % propio, comisión y anunciante de cada orden", async () => {
    await abrirDetalle(base);
    const panel = within(panelDeDetalle());
    expect(panel.getByText("Órdenes asignadas")).toBeInTheDocument();
    expect(panel.getByText("OC-2025-0041")).toBeInTheDocument();
    expect(panel.getByText(/15\.00 %/)).toBeInTheDocument();
    expect(panel.getByText(/Grupo Bimbo/)).toBeInTheDocument();
    expect(panel.getAllByText("$177,480.00").length).toBe(2);
  });

  it("muestra el archivo adjunto (PDF/XML) cuando existe", async () => {
    await abrirDetalle({
      ...base,
      archivo_pdf_path: "facturacion/proveedor/vendedor/pdf/abc_factura.pdf",
      archivo_xml_path: "facturacion/proveedor/vendedor/xml/abc_factura.xml",
    });
    expect(screen.getByText("facturacion/proveedor/vendedor/pdf/abc_factura.pdf")).toBeInTheDocument();
    expect(screen.getByText("facturacion/proveedor/vendedor/xml/abc_factura.xml")).toBeInTheDocument();
  });

  it("fix: una factura autorizada no permite editar (candado del backend)", async () => {
    await abrirDetalle(base);
    expect(screen.getByRole("button", { name: "Editar" })).toBeDisabled();
  });

  it("fix: en 'autorizada' no se ofrece 'Marcar pagada' (esa transición va por otro canal)", async () => {
    await abrirDetalle(base);
    expect(screen.queryByRole("button", { name: "Marcar pagada" })).toBeNull();
  });

  it("una factura 'recibida' sí permite editar, y precarga vendedor/órdenes ya asignadas", async () => {
    await abrirDetalle({ ...base, estatus_factura_vendedor: "recibida" });
    const boton = screen.getByRole("button", { name: "Editar" });
    expect(boton).toBeEnabled();

    fireEvent.click(boton);
    expect(await screen.findByText("Editar factura de vendedor")).toBeInTheDocument();
    expect(screen.getByDisplayValue("VEN-2025-0287")).toBeInTheDocument();
    const comboVendedor = await screen.findByDisplayValue("Juan Pérez");
    expect(comboVendedor).toBeEnabled();
    expect(screen.getByText("OC-2025-0041")).toBeInTheDocument();
  });

  it("guardar la edición llama a actualizar con el id correcto, vendedor_id y ordenes_ids", async () => {
    actualizarMock.mockResolvedValue({ ...base, estatus_factura_vendedor: "recibida" });
    await abrirDetalle({ ...base, estatus_factura_vendedor: "recibida" });
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    await screen.findByText("Editar factura de vendedor");

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(actualizarMock).toHaveBeenCalledTimes(1));
    const [id, payload] = actualizarMock.mock.calls[0];
    expect(id).toBe("fv-1");
    expect(payload.vendedor_id).toBe("vd-1");
    expect(payload.ordenes_ids).toEqual(["oc-1"]);

    expect(await screen.findByText("Órdenes asignadas")).toBeInTheDocument();
  });
});
