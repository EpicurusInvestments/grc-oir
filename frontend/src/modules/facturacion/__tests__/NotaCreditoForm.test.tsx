/** Notas de Crédito (petición del usuario, con captura): alta desde `NotaCreditoForm` —
 * sin orden de origen, monto capturado en POSITIVO (el payload lo manda igual, el
 * backend lo niega), `ordenes_ids` vacío, `facturas_relacionadas_ids` con la factura de
 * origen, `tipo_comprobante: "E"`, método de pago fijo `PUE` y forma de pago heredada.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotaCreditoForm } from "../facturaCliente/components/NotaCreditoForm";
import type { FacturaCliente, FacturaClienteCreate } from "../types";

vi.mock("@/modules/catalogos/constantesSistema/hooks", () => ({
  useConstantes: () => ({
    useList: ({ grupo }: { grupo: string }) => {
      const porGrupo: Record<string, { clave: string; descripcion: string }[]> = {
        ClaveProdServ: [{ clave: "82101601", descripcion: "Spots publicitarios" }],
        ClaveUnidad: [{ clave: "E48", descripcion: "Unidad de servicio" }],
        MonedaSAT: [{ clave: "MXN", descripcion: "Peso mexicano" }],
        TipoRelacion: [{ clave: "01", descripcion: "Nota de crédito de los documentos relacionados" }],
        UsoCFDI: [{ clave: "G02", descripcion: "Devoluciones, descuentos o bonificaciones" }],
      };
      return { data: { items: porGrupo[grupo] ?? [] } };
    },
  }),
}));

vi.mock("../hooks", () => ({
  useCuentasContables: () => ({ data: [{ id: "cc-1", etiqueta: "4100-001 · Ingresos" }] }),
}));

const origen: FacturaCliente = {
  factura_id: "f-origen",
  numero_factura: "FMEX-1246",
  numero_pedido: null,
  referencia_adicional: null,
  orden_id: "oc-1",
  ordenes: [],
  empresa_facturadora_id: "e-1",
  anunciante_id: "an-1",
  agencia_id: null,
  razon_social_facturacion: "Grupo Bimbo SA de CV",
  rfc_facturacion: "GBI900101AB1",
  direccion_facturacion: null,
  uso_cfdi: "G03",
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
  forma_pago_clave: "03",
  clave_prod_serv: "82101601",
  clave_unidad: "E48",
  moneda_sat: "MXN",
  tipo_comprobante: "I",
  motivo_nota_credito: null,
  tipo_relacion_sat: null,
  info_cuenta_pago: null,
  layout_factura: null,
  estado_facturacion: "timbrada",
  folio_fiscal_sat: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
  fecha_timbrado: "2026-03-02",
  serie_timbrado: null,
  xml_path: null,
  pdf_path: null,
  facturado_en_sistema_externo: false,
  created_by: "u-1",
  created_at: "2026-03-01T10:00:00",
  updated_at: null,
  empresa_facturadora: "OIR Comercial",
  folio_orden: "OC-2026-0041",
  facturas_relacionadas_ids: [],
};

function llenarMinimo(container: HTMLElement) {
  fireEvent.change(screen.getByPlaceholderText("Ej. NC-2026-11-0071"), {
    target: { value: "NC-2026-11-0071" },
  });
  fireEvent.change(screen.getByDisplayValue("Nota de crédito de la factura FMEX-1246"), {
    target: { value: "Nota de crédito de la factura FMEX-1246" },
  });
  const motivo = container.querySelector('select[name="motivo_nota_credito"]') as HTMLSelectElement;
  fireEvent.change(motivo, { target: { value: "descuento" } });
  fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "500" } });
  // Los 3 SearchableSelect (cuenta contable, clave prod/serv, clave unidad) y el
  // <select> de moneda ya traen una sola opción cada uno — basta con el default del
  // catálogo mockeado, no hace falta elegirlos a mano para que el form sea válido.
}

describe("NotaCreditoForm", () => {
  it("muestra la factura de origen fija (no editable) y precarga la descripción sugerida", () => {
    render(
      <NotaCreditoForm origen={origen} onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText("Factura de origen")).toBeInTheDocument();
    expect(screen.getByText("FMEX-1246")).toBeInTheDocument();
    expect(screen.getByText("Grupo Bimbo SA de CV")).toBeInTheDocument();
    // Forma de pago heredada, mostrada de solo lectura.
    expect(screen.getByText("03")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("Nota de crédito de la factura FMEX-1246"),
    ).toBeInTheDocument();
  });

  it("al guardar, manda el payload con ordenes_ids vacío, la factura de origen, tipo 'E', PUE fijo y la forma de pago heredada", async () => {
    const onSubmit = vi.fn();
    const { container } = render(
      <NotaCreditoForm origen={origen} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    llenarMinimo(container);

    fireEvent.click(screen.getByRole("button", { name: "Crear Nota de Crédito (preparada)" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0] as FacturaClienteCreate;
    expect(payload.numero_factura).toBe("NC-2026-11-0071");
    expect(payload.ordenes_ids).toEqual([]);
    expect(payload.facturas_relacionadas_ids).toEqual(["f-origen"]);
    expect(payload.tipo_comprobante).toBe("E");
    expect(payload.metodo_pago_clave).toBe("PUE");
    expect(payload.forma_pago_clave).toBe("03");
    expect(payload.motivo_nota_credito).toBe("descuento");
    expect(payload.monto_nota_credito).toBe("500");
  });

  it("'Cancelar' no manda nada y notifica al padre", () => {
    const onCancel = vi.fn();
    render(<NotaCreditoForm origen={origen} onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
