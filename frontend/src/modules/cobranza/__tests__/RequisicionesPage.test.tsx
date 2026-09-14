/** Pruebas de "Requisiciones de pago" (F3): qué botones de la máquina de estados ofrece
 * la UI en cada estatus — no lo que el backend ya valida (mismo criterio que F2).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequisicionesPage } from "../requisicion/pages/RequisicionesPage";
import type { Requisicion } from "../types";

const listMock = vi.fn();
const cambiarEstatusMock = vi.fn();
const autorizarMock = vi.fn();

vi.mock("../api", () => ({
  requisicionApi: {
    list: (params: unknown) => listMock(params),
    create: vi.fn(),
    update: vi.fn(),
    cambiarEstatus: (id: string, estatus: string, fecha?: string | null) =>
      cambiarEstatusMock(id, estatus, fecha),
    autorizar: (id: string) => autorizarMock(id),
  },
  afiliadosInfo: vi.fn().mockResolvedValue([]),
  agenciasInfo: vi.fn().mockResolvedValue([]),
  vendedoresInfo: vi.fn().mockResolvedValue([]),
  facturasAfiliadoPagables: vi.fn().mockResolvedValue([]),
  facturasAgenciaPagables: vi.fn().mockResolvedValue([]),
  ordenesInfo: vi.fn().mockResolvedValue([]),
}));

const base: Requisicion = {
  requisicion_id: "rq-1",
  numero_requisicion: "REQ-2026-0001",
  numero_oc_sap: "OC-SAP-100",
  tipo_requisicion: "pago_afiliado",
  factura_afiliado_id: null,
  factura_agencia_id: null,
  orden_id: null,
  afiliado_id: "af-1",
  agencia_id: null,
  vendedor_comision_id: null,
  razon_social_afiliada: "Multimedios Estrellas de Oro SA de CV",
  monto_requisicion: "526176.00",
  porcentaje_comision_vendedor: null,
  requisicion_comision_vendedor: null,
  porcentaje_comision_agencia_req: null,
  requisicion_comision_agencia: null,
  diferencia_afiliada: "1200.00",
  estatus_requisicion: "pendiente",
  fecha_pago_requisicion: null,
  observaciones_cuentas_por_pagar: null,
  created_by: "u-1",
  created_at: "2026-03-01T10:00:00",
  updated_at: null,
};

function renderCon(r: Requisicion) {
  listMock.mockResolvedValue({ items: [r], total: 1, page: 1, size: 20, pages: 1 });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequisicionesPage />
    </QueryClientProvider>,
  );
}

describe("RequisicionesPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    cambiarEstatusMock.mockReset();
    autorizarMock.mockReset();
  });

  it("lista las requisiciones con su monto y beneficiario", async () => {
    renderCon(base);
    expect(await screen.findByText("REQ-2026-0001")).toBeInTheDocument();
    expect(screen.getAllByText("Multimedios Estrellas de Oro SA de CV").length).toBeGreaterThan(0);
    // Aparece tanto en el renglón de la lista como en la franja de KPIs ("Por autorizar").
    expect(screen.getAllByText(/\$526,176\.00/).length).toBeGreaterThan(0);
  });

  it("en 'pendiente' ofrece cancelar y autorizar, pero NO marcar pagada", async () => {
    renderCon(base);
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText("Autorizar →")).toBeInTheDocument());
    expect(screen.getByText("Cancelar")).toBeInTheDocument();
    expect(screen.queryByText("Marcar pagada →")).not.toBeInTheDocument();
  });

  it("en 'autorizada' ofrece marcar pagada, pero NO autorizar de nuevo", async () => {
    renderCon({ ...base, estatus_requisicion: "autorizada" });
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText("Marcar pagada →")).toBeInTheDocument());
    expect(screen.queryByText("Autorizar →")).not.toBeInTheDocument();
  });

  it("en 'pagada' no ofrece ninguna transición, solo la fecha de pago", async () => {
    renderCon({ ...base, estatus_requisicion: "pagada", fecha_pago_requisicion: "2026-03-10" });
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText(/✓ Pagada el/)).toBeInTheDocument());
    expect(screen.queryByText("Autorizar →")).not.toBeInTheDocument();
    expect(screen.queryByText("Marcar pagada →")).not.toBeInTheDocument();
    expect(screen.queryByText("Cancelar")).not.toBeInTheDocument();
  });

  it("en 'cancelada' no ofrece ninguna transición", async () => {
    renderCon({ ...base, estatus_requisicion: "cancelada" });
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText("Cancelada")).toBeInTheDocument());
    expect(screen.queryByText("Autorizar →")).not.toBeInTheDocument();
    expect(screen.queryByText("Marcar pagada →")).not.toBeInTheDocument();
  });

  it("la diferencia contra la factura del afiliado se muestra aunque sea negativa", async () => {
    renderCon({ ...base, diferencia_afiliada: "-500.00" });
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText(/-\$500\.00/)).toBeInTheDocument());
  });
});
