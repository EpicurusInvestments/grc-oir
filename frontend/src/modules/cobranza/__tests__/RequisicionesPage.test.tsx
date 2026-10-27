/** Pruebas de "Requisiciones de pago" (F3): qué botones de la máquina de estados ofrece
 * la UI en cada estatus — no lo que el backend ya valida (mismo criterio que F2).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequisicionesPage } from "../requisicion/pages/RequisicionesPage";
import type { Requisicion } from "../types";

const listMock = vi.fn();
const cambiarEstatusMock = vi.fn();
const autorizarMock = vi.fn();
const facturasAfiliadoInfoMock = vi.fn().mockResolvedValue([]);
const facturasAfiliadoPagablesMock = vi.fn().mockResolvedValue([]);
const asignacionesFacturaAfiliadoMock = vi.fn().mockResolvedValue([]);

// El badge "Orden de servicio" de `pago_afiliado` reusa el endpoint de asignaciones de
// F2 (`facturaAfiliadoApi`, de otro módulo) — se mockea aparte para que la prueba no
// dependa de una llamada HTTP real no interceptada.
vi.mock("@/modules/facturacion/api", () => ({
  facturaAfiliadoApi: { asignaciones: (id: string) => asignacionesFacturaAfiliadoMock(id) },
}));

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
  facturasAfiliadoPagables: () => facturasAfiliadoPagablesMock(),
  facturasAgenciaPagables: vi.fn().mockResolvedValue([]),
  facturasAfiliadoInfo: () => facturasAfiliadoInfoMock(),
  facturasAgenciaInfo: vi.fn().mockResolvedValue([]),
  facturasVendedorInfo: vi.fn().mockResolvedValue([]),
  facturasVendedorPagables: vi.fn().mockResolvedValue([]),
  ordenesInfo: vi.fn().mockResolvedValue([]),
}));

const base: Requisicion = {
  requisicion_id: "rq-1",
  numero_requisicion: "REQ-2026-0001",
  numero_oc_sap: "OC-SAP-100",
  tipo_requisicion: "pago_afiliado",
  factura_afiliado_id: null,
  factura_agencia_id: null,
  factura_vendedor_id: null,
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
    facturasAfiliadoInfoMock.mockReset().mockResolvedValue([]);
    facturasAfiliadoPagablesMock.mockReset().mockResolvedValue([]);
    asignacionesFacturaAfiliadoMock.mockReset().mockResolvedValue([]);
  });

  it("lista las requisiciones con su monto y beneficiario", async () => {
    renderCon(base);
    expect(await screen.findByText("REQ-2026-0001")).toBeInTheDocument();
    expect(screen.getAllByText("Multimedios Estrellas de Oro SA de CV").length).toBeGreaterThan(0);
    // Aparece tanto en el renglón de la lista como en la franja de KPIs ("Por autorizar").
    expect(screen.getAllByText(/\$526,176\.00/).length).toBeGreaterThan(0);
  });

  it("fix (reportado por el usuario, con captura): la columna 'Origen' resuelve la factura aunque ya no esté en el combo de 'disponibles' del alta", async () => {
    // La requisición YA tiene esta factura ligada (así se creó) — el combo del alta
    // (`facturasAfiliadoPagables`, ADR-217) la EXCLUYE porque ya está usada, pero el
    // "Origen" de la lista debe seguir resolviéndola con `facturasAfiliadoInfo`
    // (sin ese filtro) en vez de mostrar "—".
    facturasAfiliadoPagablesMock.mockResolvedValue([]);
    facturasAfiliadoInfoMock.mockResolvedValue([
      { factura_afiliado_id: "fa-1", afiliado_id: "af-1", factura_emisora: "AFLI-003", total_factura_afiliado: "10317.00" },
    ]);
    renderCon({ ...base, factura_afiliado_id: "fa-1" });
    expect(await screen.findByText("AFLI-003")).toBeInTheDocument();
  });

  it("petición del usuario, con captura: despliega la orden de servicio relacionada como badge junto al tipo", async () => {
    asignacionesFacturaAfiliadoMock.mockResolvedValue([
      { id: "asig-1", factura_afiliado_id: "fa-1", orden_estacion_id: "oe-1", monto_asignado: "100.00", notas_asignacion: null, folio_orden_estacion: "OE-1", nombre_estacion: "XHTEST-FM", folio_orden: "OC-2026-0041" },
    ]);
    renderCon({ ...base, factura_afiliado_id: "fa-1" });
    (await screen.findByText("REQ-2026-0001")).click();
    expect(await screen.findByText("OC-2026-0041")).toBeInTheDocument();
  });

  it("pago_afiliado con la factura repartida en varias Órdenes de Servicio (parcialidades): el badge muestra la primera y un contador", async () => {
    asignacionesFacturaAfiliadoMock.mockResolvedValue([
      { id: "asig-1", factura_afiliado_id: "fa-1", orden_estacion_id: "oe-1", monto_asignado: "100.00", notas_asignacion: null, folio_orden_estacion: "OE-1", nombre_estacion: "XHTEST-FM", folio_orden: "OC-2026-0041A" },
      { id: "asig-2", factura_afiliado_id: "fa-1", orden_estacion_id: "oe-2", monto_asignado: "100.00", notas_asignacion: null, folio_orden_estacion: "OE-2", nombre_estacion: "XHTEST-FM", folio_orden: "OC-2026-0041B" },
    ]);
    renderCon({ ...base, factura_afiliado_id: "fa-1" });
    (await screen.findByText("REQ-2026-0001")).click();
    expect(await screen.findByText("OC-2026-0041A +1")).toBeInTheDocument();
  });

  it("sin factura ligada (campo opcional): no aparece ningún badge de orden de servicio", async () => {
    renderCon(base);
    (await screen.findByText("REQ-2026-0001")).click();
    await waitFor(() => expect(screen.getByText("Origen del pago")).toBeInTheDocument());
    expect(asignacionesFacturaAfiliadoMock).not.toHaveBeenCalled();
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

  describe("bug reportado por el usuario: los pills de 'Estado' no filtraban la tabla", () => {
    // A diferencia de `renderCon` (arriba, `mockResolvedValue` fijo), aquí `listMock`
    // SÍ filtra según `params.estatus_requisicion` — igual que el backend real — para
    // poder detectar si el componente de verdad vuelve a pedir la lista filtrada al
    // cambiar de pill, en vez de quedarse mostrando todo.
    function renderConVariasRequisiciones() {
      const pendiente = { ...base, requisicion_id: "rq-1", numero_requisicion: "REQ-PENDIENTE", estatus_requisicion: "pendiente" as const };
      const autorizada = { ...base, requisicion_id: "rq-2", numero_requisicion: "REQ-AUTORIZADA", estatus_requisicion: "autorizada" as const };
      const pagada = { ...base, requisicion_id: "rq-3", numero_requisicion: "REQ-PAGADA", estatus_requisicion: "pagada" as const };
      const todas = [pendiente, autorizada, pagada];
      listMock.mockImplementation((params: { estatus_requisicion?: string }) => {
        const items = params.estatus_requisicion
          ? todas.filter((r) => r.estatus_requisicion === params.estatus_requisicion)
          : todas;
        return Promise.resolve({ items, total: items.length, page: 1, size: 20, pages: 1 });
      });
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(
        <QueryClientProvider client={qc}>
          <RequisicionesPage />
        </QueryClientProvider>,
      );
    }

    it("clic en 'Por autorizar' vuelve a pedir la lista con `estatus_requisicion: 'pendiente'` y solo muestra esa fila", async () => {
      renderConVariasRequisiciones();
      await screen.findByText("REQ-PENDIENTE");
      expect(screen.getByText("REQ-AUTORIZADA")).toBeInTheDocument();
      expect(screen.getByText("REQ-PAGADA")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Por autorizar" }));

      await waitFor(() =>
        expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: "pendiente" })),
      );
      await waitFor(() => expect(screen.queryByText("REQ-AUTORIZADA")).not.toBeInTheDocument());
      expect(screen.getByText("REQ-PENDIENTE")).toBeInTheDocument();
      expect(screen.queryByText("REQ-PAGADA")).not.toBeInTheDocument();
    });

    it("clic en 'Por pagar' y luego 'Pagadas' cambia la lista cada vez (no se queda pegado en un filtro)", async () => {
      renderConVariasRequisiciones();
      await screen.findByText("REQ-PENDIENTE");

      fireEvent.click(screen.getByRole("button", { name: "Por pagar" }));
      await waitFor(() =>
        expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: "autorizada" })),
      );
      await waitFor(() => expect(screen.queryByText("REQ-PENDIENTE")).not.toBeInTheDocument());
      expect(screen.getByText("REQ-AUTORIZADA")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Pagadas" }));
      await waitFor(() =>
        expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: "pagada" })),
      );
      await waitFor(() => expect(screen.queryByText("REQ-AUTORIZADA")).not.toBeInTheDocument());
      expect(screen.getByText("REQ-PAGADA")).toBeInTheDocument();

      // "Todas" existe en los 2 grupos de pills (Estado y Tipo) — el de Estado es el
      // primero en el DOM (`filters` se renderiza antes que `filters2`).
      fireEvent.click(screen.getAllByRole("button", { name: "Todas" })[0]);
      await waitFor(() =>
        expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: undefined })),
      );
      await screen.findByText("REQ-PENDIENTE");
      expect(screen.getByText("REQ-AUTORIZADA")).toBeInTheDocument();
      expect(screen.getByText("REQ-PAGADA")).toBeInTheDocument();
    });
  });
});
