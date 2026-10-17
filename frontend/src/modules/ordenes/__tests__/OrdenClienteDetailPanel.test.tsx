/** Corrección del hallazgo #12: el historial de cambios de comisión se auditaba en memoria
 * pero ninguna pantalla lo mostraba. Cubre el bloque "Historial de cambios" en
 * `OrdenClienteDetailPanel.tsx` (mismo patrón que `ContratoDetailPanel` en F0) — desde
 * ADR-180 el título ya no dice "... de comisión" porque el mismo bloque también muestra
 * los cambios de fecha de campaña (comparten `entidad_id`, no se pueden separar).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { verAdjuntoOrden } from "../adapters/adjuntosApi";
import { OrdenClienteDetailPanel } from "../ordenCliente/components/OrdenClienteDetailPanel";
import type { HistorialComision } from "../state/OrdenesContext";
import { makeOC } from "./fixtures";

vi.mock("../adapters/adjuntosApi", () => ({
  nombreDeAdjuntoRef: (ref: string) => ref.split("/").pop()!.split("_").slice(1).join("_"),
  verAdjuntoOrden: vi.fn().mockResolvedValue(undefined),
}));

// ADR-208: el panel ahora pide la FacturaCliente de la orden (solo si ya está
// "facturada" o más — `enabled`), vía React Query.
const listFacturaMock = vi.fn();
const verMock = vi.fn();
const verEnVisorMock = vi.fn();
vi.mock("@/modules/facturacion/api", () => ({
  facturaClienteApi: { list: (p: unknown) => listFacturaMock(p) },
  adjuntosFacturacionApi: { ver: (ref: string) => verMock(ref), verEnVisor: (ref: string) => verEnVisorMock(ref) },
}));

beforeEach(() => {
  listFacturaMock.mockReset();
  listFacturaMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 10, pages: 0 });
  verMock.mockReset();
  verEnVisorMock.mockReset();
});

function renderPanel(oc: ReturnType<typeof makeOC>, historialComisiones: HistorialComision[] = []) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrdenClienteDetailPanel
        oc={oc}
        ordenesEstacion={[]}
        incidencias={[]}
        historialComisiones={historialComisiones}
        onSeleccionarOE={vi.fn()}
        onEditar={vi.fn()}
        onAsignarEstaciones={vi.fn()}
        onCerrar={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("Historial de cambios — comisión (fix del hallazgo #12) + fecha (ADR-180)", () => {
  it("sin cambios registrados, muestra el estado vacío explícito", () => {
    renderPanel(makeOC());
    expect(screen.getByText("Sin cambios registrados.")).toBeInTheDocument();
  });

  it("muestra solo los cambios de ESTA OC (filtra por entidad_id), con campo, valores, usuario y motivo", () => {
    const oc = makeOC();
    const historial: HistorialComision[] = [
      {
        log_cambio_parametro_id: "h1",
        entidad: "OrdenCliente",
        entidad_id: oc.id,
        campo: "porcentaje_comision_agencia_snap",
        valor_anterior: "15",
        valor_nuevo: "13.5",
        usuario: "dev.admin",
        ip: null,
        motivo_cambio: "Renegociación posterior al cierre.",
        fecha_cambio: "2025-01-10T09:45:00",
      },
      {
        log_cambio_parametro_id: "h2",
        entidad: "OrdenCliente",
        entidad_id: "otra-oc-distinta",
        campo: "porcentaje_comision_vendedor_principal_snap",
        valor_anterior: "4",
        valor_nuevo: "5",
        usuario: "alguien.mas",
        ip: null,
        motivo_cambio: null,
        fecha_cambio: "2025-01-01T00:00:00",
      },
    ];
    renderPanel(oc, historial);

    expect(screen.getByText(/% comisión agencia/)).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("13.5")).toBeInTheDocument();
    expect(screen.getByText(/dev\.admin/)).toBeInTheDocument();
    expect(screen.getByText(/Renegociación posterior al cierre\./)).toBeInTheDocument();

    // El de la otra OC no debe aparecer.
    expect(screen.queryByText(/alguien\.mas/)).toBeNull();
  });

  it("ADR-180: un cambio de fecha de campaña aparece en el mismo bloque, con su propia etiqueta", () => {
    const oc = makeOC();
    const historial: HistorialComision[] = [
      {
        log_cambio_parametro_id: "h3",
        entidad: "OrdenCliente",
        entidad_id: oc.id,
        campo: "fecha_inicio_campania",
        valor_anterior: "2026-06-01",
        valor_nuevo: "2026-07-01",
        usuario: "dev.ventas",
        ip: null,
        motivo_cambio: "Se redujo el periodo",
        fecha_cambio: "2026-10-09T09:45:00",
      },
    ];
    renderPanel(oc, historial);

    expect(screen.getByText(/Inicio de campaña/)).toBeInTheDocument();
    expect(screen.getByText(/Se redujo el periodo/)).toBeInTheDocument();
  });
});

describe("Fix: sección Documentos muestra el nombre original, sin el UUID de la clave", () => {
  it("sin documentos de cierre, muestra el estado vacío", () => {
    renderPanel(makeOC());
    expect(screen.getByText("Sin documentos de cierre todavía.")).toBeInTheDocument();
  });

  it("con documentos, muestra el nombre original (no la clave completa con el UUID) y al hacer clic descarga esa ref", () => {
    const oc = makeOC({
      odc_cerrada_ref: "ordenes/cierre/odc/fc25aecb3cac48a7af3ee656d3228522_PRUEBA-DE-ARCHIVO.docx",
      carta_conciliacion_ref: "ordenes/cierre/carta/9a750cdfba0945f2a82faf3fe1ee2e49_PRUEBA-DE-ARCHIVO_PDF.pdf",
    });
    renderPanel(oc);

    expect(screen.getByText(/PRUEBA-DE-ARCHIVO\.docx/)).toBeInTheDocument();
    expect(screen.getByText(/PRUEBA-DE-ARCHIVO_PDF\.pdf/)).toBeInTheDocument();
    expect(screen.queryByText(/fc25aecb3cac48a7af3ee656d3228522/)).toBeNull();

    fireEvent.click(screen.getByText(/PRUEBA-DE-ARCHIVO\.docx/));
    expect(verAdjuntoOrden).toHaveBeenCalledWith(oc.odc_cerrada_ref);
  });
});

// ── ADR-208 (petición del usuario): sección "Factura" con Ver/Descargar ──────────────
describe('Sección "Factura": Ver/Descargar PDF/XML cuando la orden ya está facturada', () => {
  it("antes de 'facturada' no muestra la sección ni pide la factura", () => {
    renderPanel(makeOC({ estatus_orden: "orden_cerrada" }));
    expect(screen.queryByText("Factura")).not.toBeInTheDocument();
    expect(listFacturaMock).not.toHaveBeenCalled();
  });

  it("'facturada_timbrada' con pdf_path Y xml_path ofrece 'Ver factura', 'Descargar PDF' y 'Descargar XML'", async () => {
    listFacturaMock.mockResolvedValue({
      items: [
        {
          factura_id: "f-1",
          estado_facturacion: "timbrada",
          pdf_path: "facturacion/clientes/pdf/abc_factura.pdf",
          xml_path: "facturacion/clientes/xml/abc_factura.xml",
        },
      ],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    });
    renderPanel(makeOC({ estatus_orden: "facturada_timbrada" }));

    expect(await screen.findByText("Ver factura")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Ver factura"));
    await waitFor(() =>
      expect(verEnVisorMock).toHaveBeenCalledWith("facturacion/clientes/pdf/abc_factura.pdf"),
    );

    fireEvent.click(screen.getByText("Descargar PDF"));
    await waitFor(() => expect(verMock).toHaveBeenCalledWith("facturacion/clientes/pdf/abc_factura.pdf"));

    fireEvent.click(screen.getByText("Descargar XML"));
    await waitFor(() => expect(verMock).toHaveBeenCalledWith("facturacion/clientes/xml/abc_factura.xml"));
  });

  it("'facturada_archivo_plano' sin pdf_path ni xml_path explica que aún no hay nada que descargar", async () => {
    listFacturaMock.mockResolvedValue({
      items: [{ factura_id: "f-1", estado_facturacion: "preparada", pdf_path: null, xml_path: null }],
      total: 1,
      page: 1,
      size: 10,
      pages: 1,
    });
    renderPanel(makeOC({ estatus_orden: "facturada_archivo_plano" }));

    expect(await screen.findByText("Factura generada, sin PDF ni XML cargados todavía.")).toBeInTheDocument();
    expect(screen.queryByText("Ver factura")).not.toBeInTheDocument();
  });

  it("ignora una factura CANCELADA y usa la vigente (ADR-047: se puede refacturar)", async () => {
    listFacturaMock.mockResolvedValue({
      items: [
        { factura_id: "f-vieja", estado_facturacion: "cancelada", pdf_path: "facturacion/clientes/pdf/VIEJA.pdf", xml_path: null },
        { factura_id: "f-nueva", estado_facturacion: "timbrada", pdf_path: "facturacion/clientes/pdf/NUEVA.pdf", xml_path: null },
      ],
      total: 2,
      page: 1,
      size: 10,
      pages: 1,
    });
    renderPanel(makeOC({ estatus_orden: "cobrada" }));

    fireEvent.click(await screen.findByText("Descargar PDF"));
    await waitFor(() => expect(verMock).toHaveBeenCalledWith("facturacion/clientes/pdf/NUEVA.pdf"));
    expect(verMock).not.toHaveBeenCalledWith("facturacion/clientes/pdf/VIEJA.pdf");
  });
});
