/** Bug reportado por el usuario: al navegar del menú "Requisiciones" a la vista
 * operativa "Por autorizar" (o "Por pagar"), la pantalla se quedaba mostrando TODAS las
 * requisiciones en vez de solo las del filtro esperado.
 *
 * Causa real: `CobranzaExplorerPage.tsx` renderizaba `entry.render()` sin ninguna `key`
 * — como "Requisiciones" y "Por autorizar" usan el MISMO componente
 * (`RequisicionesPage`, solo con `filtroInicial` distinto), React no lo remontaba al
 * cambiar de sección, así que el `useState(filtroInicial ?? "all")` interno (que solo
 * corre al montar) se quedaba con el valor de la PRIMERA vez que se montó. Nada tenía
 * que ver con los pills de "Estado" en sí (ver `RequisicionesPage.test.tsx`, que ya
 * confirma que SÍ filtran correctamente una vez montado con el `filtroInicial` correcto).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CobranzaExplorerPage } from "../pages/CobranzaExplorerPage";
import type { Requisicion } from "../types";

const listMock = vi.fn();

vi.mock("../api", () => ({
  cobranzaFacturaApi: { list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }) },
  pagoClienteApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
    crear: vi.fn(),
    eliminar: vi.fn(),
    listarAgrupado: vi.fn().mockResolvedValue([]),
  },
  requisicionApi: {
    list: (params: { estatus_requisicion?: string }) => listMock(params),
    create: vi.fn(),
    update: vi.fn(),
    cambiarEstatus: vi.fn(),
    autorizar: vi.fn(),
  },
  movimientoBancarioApi: { list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }) },
  adjuntosCobranzaApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoCobranzaRef: (ref: string) => ref,
  anunciantesInfo: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  afiliadosInfo: vi.fn().mockResolvedValue([]),
  agenciasInfo: vi.fn().mockResolvedValue([]),
  vendedoresInfo: vi.fn().mockResolvedValue([]),
  facturasAfiliadoPagables: vi.fn().mockResolvedValue([]),
  facturasAgenciaPagables: vi.fn().mockResolvedValue([]),
  facturasAfiliadoInfo: vi.fn().mockResolvedValue([]),
  facturasAgenciaInfo: vi.fn().mockResolvedValue([]),
  facturasVendedorInfo: vi.fn().mockResolvedValue([]),
  facturasVendedorPagables: vi.fn().mockResolvedValue([]),
  ordenesInfo: vi.fn().mockResolvedValue([]),
  facturaClienteResumen: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/modules/catalogos/anunciante/api", () => ({
  contactoAnuncianteApi: {
    listPorAnunciante: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 }),
  },
}));

const pendiente: Requisicion = {
  requisicion_id: "rq-1",
  numero_requisicion: "REQ-PENDIENTE",
  numero_oc_sap: null,
  tipo_requisicion: "pago_afiliado",
  factura_afiliado_id: null,
  factura_agencia_id: null,
  factura_vendedor_id: null,
  orden_id: null,
  afiliado_id: "af-1",
  agencia_id: null,
  vendedor_comision_id: null,
  razon_social_afiliada: "Afiliado Uno",
  monto_requisicion: "1000.00",
  porcentaje_comision_vendedor: null,
  requisicion_comision_vendedor: null,
  porcentaje_comision_agencia_req: null,
  requisicion_comision_agencia: null,
  diferencia_afiliada: "0.00",
  estatus_requisicion: "pendiente",
  fecha_pago_requisicion: null,
  observaciones_cuentas_por_pagar: null,
  motivo_cancelacion: null,
  created_by: "u-1",
  created_at: "2026-03-01T10:00:00",
  updated_at: null,
  folio_factura_origen: null,
  ordenes_folios: null,
};
const autorizada: Requisicion = { ...pendiente, requisicion_id: "rq-2", numero_requisicion: "REQ-AUTORIZADA", estatus_requisicion: "autorizada" };
const todas = [pendiente, autorizada];

function renderExplorer() {
  listMock.mockImplementation((params: { estatus_requisicion?: string; size?: number }) => {
    const items = params.estatus_requisicion
      ? todas.filter((r) => r.estatus_requisicion === params.estatus_requisicion)
      : todas;
    return Promise.resolve({ items, total: items.length, page: 1, size: params.size ?? 20, pages: 1 });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <CobranzaExplorerPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Fix (reportado por el usuario): navegar a una 'vista operativa' SÍ aplica su filtro, aunque reuse el mismo componente", () => {
  beforeEach(() => {
    listMock.mockReset();
  });

  // "Por autorizar"/"Por pagar" son, a la vez, un ítem del SIDEBAR y un pill de filtro
  // DENTRO de `RequisicionesPage` (`FILTROS_ESTATUS`) — se desambigua acotando al
  // `<aside className="sidebar">`.
  const clickSidebar = (label: string) => {
    const sidebar = document.querySelector(".sidebar") as HTMLElement;
    within(sidebar).getByText(label).click();
  };

  it("de 'Requisiciones' (todas) a 'Por autorizar' solo muestra las pendientes", async () => {
    renderExplorer();
    clickSidebar("Requisiciones");
    await screen.findByText("REQ-PENDIENTE");
    expect(screen.getByText("REQ-AUTORIZADA")).toBeInTheDocument();

    clickSidebar("Por autorizar");

    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: "pendiente" })),
    );
    await waitFor(() => expect(screen.queryByText("REQ-AUTORIZADA")).not.toBeInTheDocument());
    expect(screen.getByText("REQ-PENDIENTE")).toBeInTheDocument();
  });

  it("de 'Por autorizar' a 'Por pagar' cambia de filtro correctamente (no se queda en 'pendiente')", async () => {
    renderExplorer();
    clickSidebar("Por autorizar");
    await screen.findByText("REQ-PENDIENTE");
    expect(screen.queryByText("REQ-AUTORIZADA")).not.toBeInTheDocument();

    clickSidebar("Por pagar");

    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ estatus_requisicion: "autorizada" })),
    );
    await waitFor(() => expect(screen.queryByText("REQ-PENDIENTE")).not.toBeInTheDocument());
    expect(screen.getByText("REQ-AUTORIZADA")).toBeInTheDocument();
  });
});

// Bug corregido (reportado por el usuario, con captura): la liga "Ver en Cobranza de
// facturas →" desde "Pagos recibidos" solo cambiaba la URL (`?cobranza_id=...`), la
// pantalla se quedaba igual. Causa real: las secciones de esta fase no son rutas de
// verdad, son un `activeKey` interno — navegar DENTRO de la misma ruta "/cobranza" no
// remonta `CobranzaExplorerPage` ni mueve ese estado por sí solo.
describe("Fix (reportado por el usuario, con captura): el deep-link ?cobranza_id=/?factura_id= SÍ mueve a 'Cobranza de facturas'", () => {
  beforeEach(() => {
    listMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 20, pages: 0 });
  });

  const clickSidebar = (label: string) => {
    const sidebar = document.querySelector(".sidebar") as HTMLElement;
    within(sidebar).getByText(label).click();
  };

  function BotonSimularLiga() {
    const navigate = useNavigate();
    return (
      <button type="button" onClick={() => navigate("/cobranza?cobranza_id=cb-1")}>
        Simular liga
      </button>
    );
  }

  it("estando en 'Pagos recibidos', simular la liga cambia la sección a 'Cobranza de facturas'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <CobranzaExplorerPage />
          <BotonSimularLiga />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const main = () => document.querySelector(".main") as HTMLElement;

    clickSidebar("Pagos recibidos");
    await screen.findByText("No asignados");
    expect(within(main()).queryByText("Cobranza de facturas")).not.toBeInTheDocument();

    screen.getByText("Simular liga").click();

    expect(await within(main()).findByText("Cobranza de facturas")).toBeInTheDocument();
    expect(within(main()).queryByText("No asignados")).not.toBeInTheDocument();
  });
});
