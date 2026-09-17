/** Facturas de agencia (F2): pantalla llevada a la misma paridad que Facturas de
 * afiliado — timeline con las 4 fases, tarjetas de importes, sección "Orden
 * relacionada" y "Cálculo de comisión" (denormalizadas por el backend), columnas
 * homologadas en la lista, y edición que permite reasignar agencia/orden.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FacturasAgenciaPage } from "../facturaAgencia/pages/FacturasAgenciaPage";
import type { FacturaAgencia } from "../types";

const listMock = vi.fn();
const actualizarMock = vi.fn();
const cambiarEstatusMock = vi.fn();
const autorizarMock = vi.fn();

vi.mock("../api", () => ({
  facturaAgenciaApi: {
    list: (params: unknown) => listMock(params),
    create: vi.fn(),
    actualizar: (id: string, data: unknown) => actualizarMock(id, data),
    ordenesFacturables: vi.fn().mockResolvedValue([]),
    cambiarEstatus: (...args: unknown[]) => cambiarEstatusMock(...args),
    autorizar: (...args: unknown[]) => autorizarMock(...args),
  },
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
  agenciasActivas: vi.fn().mockResolvedValue([{ id: "ag-1", etiqueta: "OMD México" }]),
}));

const base: FacturaAgencia = {
  factura_agencia_id: "fg-1",
  agencia_id: "ag-1",
  orden_id: "oc-1",
  folio_factura_agencia: "OMD-2025-0287",
  fecha_factura_agencia: "2025-06-08",
  monto_factura_agencia: "177480.00",
  iva_factura_agencia: "28397.00",
  total_factura_agencia: "205877.00",
  porcentaje_comision_agencia: "15.00",
  comision_agencia: "150000.00",
  archivo_nombre: null,
  archivo_path: null,
  archivo_pdf_path: null,
  archivo_xml_path: null,
  estatus_factura_agencia: "autorizada",
  created_by: "u-1",
  created_at: "2025-06-08T10:00:00",
  updated_at: null,
  agencia: "OMD México",
  folio_orden: "OC-2025-0041",
  numero_orden_cliente: "PO-BIMBO-0419",
  anunciante: "Grupo Bimbo",
  producto: "Pan Bimbo Integral 680g",
  orden_total: "1000000.00",
};

function renderCon(factura: FacturaAgencia) {
  listMock.mockResolvedValue({ items: [factura], total: 1, page: 1, size: 20, pages: 1 });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FacturasAgenciaPage />
    </QueryClientProvider>,
  );
}

async function abrirDetalle(factura: FacturaAgencia) {
  const utils = renderCon(factura);
  (await screen.findByText(factura.folio_factura_agencia as string)).click();
  // "Orden relacionada" también es el encabezado de columna de la lista — se espera
  // por un texto que solo existe en el panel de detalle.
  await screen.findByText("Cálculo de comisión");
  return utils;
}

/** El total de la factura también aparece en la columna "Total" de la lista (misma
 *  fila, seleccionada) — se acota al panel de detalle, mismo criterio que en
 *  `FacturasAfiliadoPage.test.tsx`. */
function panelDeDetalle(): HTMLElement {
  return document.querySelector(".detail-pane") as HTMLElement;
}

describe("FacturasAgenciaPage — paridad con Facturas de afiliado", () => {
  beforeEach(() => {
    listMock.mockReset();
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

  it("la lista muestra Folio, Agencia, Orden relacionada, Fecha, Subtotal, Total y Estatus", async () => {
    await abrirDetalle(base);
    const celda = screen
      .getAllByText("OMD-2025-0287")
      .find((el) => el.closest("tr")) as HTMLElement;
    const fila = within(celda.closest("tr") as HTMLElement);
    expect(fila.getByText("OMD México")).toBeInTheDocument();
    expect(fila.getByText("OC-2025-0041")).toBeInTheDocument();
    expect(fila.getByText("08/06/2025")).toBeInTheDocument();
    expect(fila.getByText("$177,480.00")).toBeInTheDocument();
    expect(fila.getByText("$205,877.00")).toBeInTheDocument();
    expect(fila.getByText("Autorizada")).toBeInTheDocument();
  });

  it("muestra las tarjetas Subtotal/IVA/Total", async () => {
    await abrirDetalle(base);
    const panel = within(panelDeDetalle());
    expect(panel.getByText("Subtotal")).toBeInTheDocument();
    expect(panel.getByText("$177,480.00")).toBeInTheDocument();
    expect(panel.getByText("$28,397.00")).toBeInTheDocument();
    expect(panel.getByText("$205,877.00")).toBeInTheDocument();
  });

  it("la sección 'Orden relacionada' muestra folio, anunciante/producto y total de la OC", async () => {
    await abrirDetalle(base);
    // "Orden relacionada"/el folio también aparecen en la lista (misma fila,
    // seleccionada) — se acota al panel de detalle.
    const panel = within(panelDeDetalle());
    expect(panel.getByText("Orden relacionada")).toBeInTheDocument();
    expect(panel.getByText("OC-2025-0041")).toBeInTheDocument();
    expect(panel.getByText("Grupo Bimbo · Pan Bimbo Integral 680g")).toBeInTheDocument();
    expect(panel.getByText("$1,000,000.00")).toBeInTheDocument();
  });

  it("la sección 'Cálculo de comisión' muestra % aplicado y monto calculado", async () => {
    await abrirDetalle(base);
    expect(screen.getByText("Cálculo de comisión")).toBeInTheDocument();
    expect(screen.getByText("15.00 %")).toBeInTheDocument();
    expect(screen.getByText("$150,000.00")).toBeInTheDocument();
    expect(screen.getByText(/Sobre venta total c\/IVA de la orden/)).toBeInTheDocument();
  });

  it("muestra el archivo adjunto (PDF/XML) cuando existe", async () => {
    await abrirDetalle({
      ...base,
      archivo_pdf_path: "facturacion/proveedor/agencia/pdf/abc_factura.pdf",
      archivo_xml_path: "facturacion/proveedor/agencia/xml/abc_factura.xml",
    });
    expect(screen.getByText("facturacion/proveedor/agencia/pdf/abc_factura.pdf")).toBeInTheDocument();
    expect(screen.getByText("facturacion/proveedor/agencia/xml/abc_factura.xml")).toBeInTheDocument();
  });

  it("fix: una factura autorizada no permite editar (candado del backend)", async () => {
    await abrirDetalle(base);
    expect(screen.getByRole("button", { name: "Editar" })).toBeDisabled();
  });

  it("fix: en 'autorizada' no se ofrece 'Marcar pagada' (esa transición va por otro canal)", async () => {
    await abrirDetalle(base);
    expect(screen.queryByRole("button", { name: "Marcar pagada" })).toBeNull();
  });

  it("una factura 'recibida' sí permite editar, y precarga agencia/orden ya asignadas", async () => {
    await abrirDetalle({ ...base, estatus_factura_agencia: "recibida" });
    const boton = screen.getByRole("button", { name: "Editar" });
    expect(boton).toBeEnabled();

    fireEvent.click(boton);
    expect(await screen.findByText("Editar factura de agencia")).toBeInTheDocument();
    expect(screen.getByDisplayValue("OMD-2025-0287")).toBeInTheDocument();
    // fix: la agencia ya se puede reasignar al editar (antes no había edición alguna).
    const comboAgencia = await screen.findByDisplayValue("OMD México");
    expect(comboAgencia).toBeEnabled();
  });

  it("guardar la edición llama a actualizar con el id correcto, agencia_id y orden_id", async () => {
    actualizarMock.mockResolvedValue({ ...base, estatus_factura_agencia: "recibida" });
    await abrirDetalle({ ...base, estatus_factura_agencia: "recibida" });
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    await screen.findByText("Editar factura de agencia");

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(actualizarMock).toHaveBeenCalledTimes(1));
    const [id, payload] = actualizarMock.mock.calls[0];
    expect(id).toBe("fg-1");
    expect(payload.agencia_id).toBe("ag-1");
    expect(payload.orden_id).toBe("oc-1");

    // Vuelve a la vista de detalle (ya no el formulario).
    expect(await screen.findByText("Cálculo de comisión")).toBeInTheDocument();
  });
});
