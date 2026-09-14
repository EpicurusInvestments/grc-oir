/** Pruebas de "Cobranza de facturas" (F3).
 *
 * Igual que las de F2: cubre lo que la UI DECIDE (qué acciones ofrece en cada estado),
 * no lo que el backend ya valida.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CobranzaFacturasPage } from "../cobranzaFactura/pages/CobranzaFacturasPage";
import type { CobranzaFactura } from "../types";

const listMock = vi.fn();
const getMock = vi.fn();
const updateMock = vi.fn();
const pagosListMock = vi.fn();

vi.mock("../api", () => ({
  cobranzaFacturaApi: {
    list: (params: unknown) => listMock(params),
    get: (id: string) => getMock(id),
    update: (id: string, data: unknown) => updateMock(id, data),
  },
  pagoClienteApi: {
    list: (cobranzaId: string, params: unknown) => pagosListMock(cobranzaId, params),
    crear: vi.fn(),
    eliminar: vi.fn(),
  },
  adjuntosCobranzaApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoCobranzaRef: (ref: string) => ref,
  anunciantesInfo: vi.fn().mockResolvedValue([
    {
      anunciante_id: "an-1",
      nombre_comercial: "Grupo Bimbo",
      rfc_anunciante: "GBI971120AB3",
      contacto_nombre: "Carlos Méndez",
      contacto_email: "c.mendez@bimbo.com.mx",
      contacto_telefono: "55 8765 4321",
      dias_credito_default: 60,
    },
  ]),
  metodosDePago: vi.fn().mockResolvedValue([{ id: "03", etiqueta: "03 · Transferencia" }]),
  facturaClienteResumen: vi.fn().mockResolvedValue({
    factura_id: "f-1",
    numero_factura: "A-001245",
    descripcion_factura: "Pan Bimbo Integral",
    razon_social_facturacion: "Bimbo SA de CV",
    agencia_id: null,
    total_factura: "1183200.00",
  }),
}));

const base: CobranzaFactura = {
  cobranza_id: "cb-1",
  factura_id: "f-1",
  anunciante_id: "an-1",
  metodo_pago_clave: "03",
  dias_credito: 60,
  fecha_estimada_cobro: "2099-01-01",
  fecha_cobro: null,
  estatus_cobro: "pendiente",
  comentarios_cobranza: null,
  created_by: "u-1",
  created_at: "2026-03-01T10:00:00",
  updated_at: null,
  importe_cobrado: "0.00",
  importe_pendiente_cobro: "1183200.00",
  vencida: false,
  numero_factura: "A-001245",
};

function renderCon(cobranza: CobranzaFactura) {
  listMock.mockResolvedValue({ items: [cobranza], total: 1, page: 1, size: 20, pages: 1 });
  getMock.mockResolvedValue(cobranza);
  pagosListMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 100, pages: 0 });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <CobranzaFacturasPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("CobranzaFacturasPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    getMock.mockReset();
    updateMock.mockReset();
    pagosListMock.mockReset();
  });

  it("lista las cobranzas con su total y estado legible", async () => {
    renderCon(base);
    expect(await screen.findByText("A-001245")).toBeInTheDocument();
    expect(screen.getAllByText("Pendiente").length).toBeGreaterThan(0);
    // Aparece tanto en el renglón de la lista como en la franja de KPIs ("Por cobrar").
    expect(screen.getAllByText(/\$1,183,200\.00/).length).toBeGreaterThan(0);
  });

  it("en 'pendiente' ofrece registrar pago y editar condiciones", async () => {
    renderCon(base);
    (await screen.findByText("A-001245")).click();
    await waitFor(() => expect(screen.getByText("Editar condiciones")).toBeInTheDocument());
    expect(screen.getAllByText(/Registrar pago/).length).toBeGreaterThan(0);
  });

  it("en 'cobrada' NO ofrece registrar pago ni editar — solo el badge de cerrada", async () => {
    const cobrada: CobranzaFactura = {
      ...base,
      estatus_cobro: "cobrada",
      importe_cobrado: "1183200.00",
      importe_pendiente_cobro: "0.00",
      fecha_cobro: "2026-03-05",
    };
    renderCon(cobrada);
    (await screen.findByText("A-001245")).click();
    await waitFor(() => expect(screen.getByText("Factura cobrada")).toBeInTheDocument());
    expect(screen.queryByText("Editar condiciones")).not.toBeInTheDocument();
    expect(screen.queryByText(/\+ Registrar pago/)).not.toBeInTheDocument();
  });

  it("una cobranza vencida muestra el badge 'Vencida' en vez de su estatus almacenado", async () => {
    const vencida: CobranzaFactura = {
      ...base,
      estatus_cobro: "pendiente",
      fecha_estimada_cobro: "2020-01-01",
      vencida: true,
    };
    renderCon(vencida);
    (await screen.findByText("A-001245")).click();
    await waitFor(() => expect(screen.getAllByText("Vencida").length).toBeGreaterThan(0));
  });

  it("una factura ya cobrada nunca se muestra vencida aunque su fecha estimada ya haya pasado", async () => {
    const cobradaVieja: CobranzaFactura = {
      ...base,
      estatus_cobro: "cobrada",
      fecha_estimada_cobro: "2020-01-01",
      fecha_cobro: "2020-01-05",
      importe_cobrado: "1183200.00",
      importe_pendiente_cobro: "0.00",
      vencida: false,
    };
    renderCon(cobradaVieja);
    (await screen.findByText("A-001245")).click();
    await waitFor(() => expect(screen.getByText("Factura cobrada")).toBeInTheDocument());
    expect(screen.queryByText("Vencida")).not.toBeInTheDocument();
  });
});
