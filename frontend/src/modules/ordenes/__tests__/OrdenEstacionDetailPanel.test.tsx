/** Tanda 3: resto de 1.4 — desglose económico OIR/emisora y desvío contra tarifa de
 * referencia, que viven inline en `OrdenEstacionDetailPanel.tsx` (no como selectores puros
 * en `state/selectors.ts`, a diferencia del resto de 1.4 ya cubierto en la Tanda 1).
 * Componente puramente presentacional: no necesita ningún Provider.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionDetailPanel } from "../ordenEstacion/components/OrdenEstacionDetailPanel";
import { estaciones, tarifas } from "../state/catalogosCache";
import { makeOC, makeOE, makeRow } from "./fixtures";

// `state/catalogosCache.ts` nace vacío; el componente resuelve `estacion`/`tarifaReferencia`
// contra él, así que sembramos aquí lo mínimo que las pruebas de desvío contra tarifa (abajo)
// necesitan: es6 = XHRC-FM (plaza pl1, fm), ta1 = pl1/fm/30s → tarifa_bruta 9500, descuento 10%.
estaciones.push({ id: "es6", afiliado_id: "af3", plaza_id: "pl1", nombre_estacion: "XHRC-FM", frecuencia: "100.9 FM", tipo_senal: "fm" });
tarifas.push({ id: "ta1", plaza_id: "pl1", tipo_senal: "fm", duracion_spot: "30s", tarifa_bruta: 9500, descuento_pct: 10 });

// Nota: SIN valor por defecto para `oc` a propósito — un parámetro con default no puede
// distinguir "no lo pasé" de "pasé undefined a propósito" (ambos casos activan el default),
// y la prueba de "sin OrdenCliente asociada" necesita que oc llegue como undefined de verdad.
function renderPanel(oe: ReturnType<typeof makeOE>, oc: ReturnType<typeof makeOC> | undefined) {
  return render(
    <OrdenEstacionDetailPanel
      oe={oe}
      oc={oc}
      incidencias={[]}
      onVerOC={vi.fn()}
      onCapturarProgramados={vi.fn()}
      onCapturarReales={vi.fn()}
      onVerVerificacion={vi.fn()}
    />,
  );
}

describe("Desglose económico OIR / emisora — 1.4", () => {
  it("calcula importe, % OIR, IVA y totales de cada lado correctamente (25 spots × $800, 20% OIR)", () => {
    const oe = makeOE({
      precio_spot: 800,
      porcentaje_participacion_oir: 20,
      periodo_transmision: [makeRow({ fecha: "2025-06-01", spots_diarios: 10 }), makeRow({ fecha: "2025-06-02", spots_diarios: 15 })],
    });
    renderPanel(oe, makeOC());

    // importe = 25 × 800 = 20,000; OIR = 20,000 × 20% = 4,000; emisora = 16,000
    expect(screen.getByText("$20,000.00")).toBeInTheDocument();
    expect(screen.getByText("$4,000.00")).toBeInTheDocument(); // importe OIR
    expect(screen.getByText("$640.00")).toBeInTheDocument(); // iva OIR = 4,000 × 16%
    expect(screen.getByText("$4,640.00")).toBeInTheDocument(); // total OIR
    expect(screen.getByText("$16,000.00")).toBeInTheDocument(); // importe emisora
    expect(screen.getByText("$2,560.00")).toBeInTheDocument(); // iva emisora = 16,000 × 16%
    expect(screen.getByText("$18,560.00")).toBeInTheDocument(); // total emisora
  });
});

describe("Desvío contra tarifa de referencia — 1.4", () => {
  it("muestra el % de desvío contra la tarifa de referencia vigente del catálogo", () => {
    // es6 = XHRC-FM, plaza pl1, tipo fm. ta1 = pl1/fm/30s: tarifa_bruta 9500, descuento 10%
    // → tarifaRefNeta = 8,550. precio_spot 9,405 = 8,550 × 1.10 → desvío exacto de +10.0%.
    const oe = makeOE({ estacion_id: "es6", plaza_id: "pl1", precio_spot: 9405 });
    const oc = makeOC({ duracion_spot: "30s" });
    renderPanel(oe, oc);

    expect(screen.getByText(/Tarifa de referencia \(catálogo, FM\): \$8,550\.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+10\.0% vs\. catálogo/)).toBeInTheDocument();
  });

  it("sin tarifa de referencia vigente para la combinación, no revienta — pero la línea se omite por completo (no muestra un '—' explícito)", () => {
    const oe = makeOE({ estacion_id: "es6", plaza_id: "pl1", precio_spot: 9000 });
    const oc = makeOC({ duracion_spot: "10s" }); // ninguna tarifa vigente tiene esta duración
    expect(() => renderPanel(oe, oc)).not.toThrow();
    expect(screen.queryByText(/Tarifa de referencia/)).toBeNull();
  });

  it("sin OrdenCliente asociada (oc undefined), tampoco revienta", () => {
    const oe = makeOE({ estacion_id: "es6", plaza_id: "pl1" });
    expect(() => renderPanel(oe, undefined)).not.toThrow();
    expect(screen.getByText("La orden del cliente ya no existe.")).toBeInTheDocument();
  });
});
