/** Tanda 3: alta de OrdenEstacion — balance de spots en vivo (incluyendo OI ya existentes de
 * la misma OC) y validaciones "antes de guardar" (1.2, 1.3).
 *
 * El formulario solo LEE `state.ordenesCliente`/`state.ordenesEstacion` (vía `useOrdenes()`);
 * `onGuardar` es un callback que la pantalla real conecta al backend, aquí un `vi.fn()`. Así
 * que cada prueba arma su propia OC (y, si hace falta, sus propias OE previas) como objetos
 * planos y los pasa directo como `initialState` de `OrdenesProvider` — no hace falta pasar por
 * `crearOC`/`crearOE` (que en Tanda 5b llaman al backend real vía HTTP).
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionForm } from "../ordenEstacion/components/OrdenEstacionForm";
import { OrdenesProvider } from "../state/OrdenesContext";
import { estaciones } from "../state/catalogosCache";
import type { OrdenCliente, OrdenEstacion } from "../types";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE } from "./fixtures";

// `es1` (plaza pl2): la estación que usan las pruebas de este archivo — el formulario la
// resuelve contra `state/catalogosCache.ts`, que nace vacío.
estaciones.push({ id: "es1", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-AM", frecuencia: "900 AM", tipo_senal: "am" });

function renderForm(opts: { oc?: Partial<OrdenCliente>; oesPrevias?: Partial<OrdenEstacion>[] } = {}) {
  const onGuardar = vi.fn();
  const onCancelar = vi.fn();
  const oc = makeOC(opts.oc);
  const oesPrevias = (opts.oesPrevias ?? []).map((oe) => makeOE({ ...oe, orden_id: oc.id }));
  const utils = render(
    <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion: oesPrevias, incidencias: [], historialComisiones: [] }}>
      <OrdenEstacionForm ocIdFijo={oc.id} onGuardar={onGuardar} onCancelar={onCancelar} />
    </OrdenesProvider>,
  );
  return { ...utils, onGuardar, onCancelar };
}

function agregarDia(container: HTMLElement, spots: number) {
  fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));
  const spotsInputs = container.querySelectorAll('input[type="number"]');
  const ultimo = spotsInputs[spotsInputs.length - 1] as HTMLInputElement;
  fireEvent.change(ultimo, { target: { value: String(spots) } });
}

describe("Balance de spots en vivo — 1.2", () => {
  it("agregar días refleja 'faltan N por asignar', luego 100%, luego sobre-asignación", () => {
    const { container } = renderForm({ oc: { total_spots: 120 } });

    agregarDia(container, 50);
    expect(screen.getByText("faltan 70 spots por asignar")).toBeInTheDocument();

    agregarDia(container, 70);
    expect(screen.getByText("✓ 100% asignado")).toBeInTheDocument();

    agregarDia(container, 1);
    expect(screen.getByText("⚠ excedente de 1 spots")).toBeInTheDocument();
  });

  it("las OE ya existentes de la misma OC cuentan como 'ya asignados' desde que se abre el formulario", () => {
    const { container } = renderForm({
      oc: { total_spots: 120 },
      oesPrevias: [{ periodo_transmision: [{ fecha: "2025-06-01", hora_inicio: "07:00", hora_termino: "08:00", spots_diarios: 50 }] }],
    });

    // Sin agregar nada en ESTA OI todavía, ya refleja los 50 de la OE previa.
    expect(screen.getByText("faltan 70 spots por asignar")).toBeInTheDocument();

    agregarDia(container, 70);
    expect(screen.getByText("✓ 100% asignado")).toBeInTheDocument();
  });
});

describe("Validaciones 'antes de guardar' — 1.3", () => {
  it("acumula errores (sin periodo, sin tarifa, tarifa mayor que la del cliente) y deshabilita 'Guardar'", () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });

    // "Captura al menos un día..." aparece dos veces (el estado vacío del propio grid, sin
    // viñeta, y el panel "Antes de guardar", con viñeta "• "): se matchea el del grid con
    // texto exacto. El de la tarifa solo vive en el panel con viñeta, así que se matchea
    // con regex (coincidencia parcial) en vez de texto exacto.
    expect(screen.getByText("Captura al menos un día de transmisión.")).toBeInTheDocument();
    expect(screen.getByText(/Captura una tarifa por spot mayor a 0\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar orden interna" })).toBeDisabled();

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    fireEvent.change(tarifaInput, { target: { value: "1500" } }); // > tarifa cliente (1000)
    // El mensaje aparece dos veces (error inline bajo el campo + resumen del panel "Antes de
    // guardar" con montos) — se usa el texto con montos, que es único, para no ambigüar.
    expect(screen.getByText(/La tarifa de la estación \(\$1,500\.00\) no puede ser mayor/)).toBeInTheDocument();

    agregarDia(container, 50);
    fireEvent.change(tarifaInput, { target: { value: "800" } });

    expect(screen.getByRole("button", { name: "Guardar orden interna" })).toBeEnabled();
  });

  it("una fecha fuera del rango de la campaña se reporta como error por día", () => {
    const { container } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, fecha_inicio_campania: "2025-06-01", fecha_fin_campania: "2025-06-30" },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    agregarDia(container, 50);

    const fechaInput = container.querySelector('input[type="date"]') as HTMLInputElement;
    fireEvent.change(fechaInput, { target: { value: "2025-07-15" } }); // fuera del rango

    expect(screen.getByText(/Día 1: La fecha cae fuera del rango de la campaña\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar orden interna" })).toBeDisabled();
  });

  it("al resolver todos los errores, 'Guardar' llama a onGuardar con el input correcto", () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    agregarDia(container, 50);

    fireEvent.click(screen.getByRole("button", { name: "Guardar orden interna" }));

    expect(onGuardar).toHaveBeenCalledTimes(1);
    const [ocIdArg, input] = onGuardar.mock.calls[0];
    expect(typeof ocIdArg).toBe("string");
    expect(input.estacion_id).toBe("es1");
    expect(input.plaza_id).toBe("pl2"); // heredada de la estación es1
    expect(input.precio_spot).toBe(800);
    expect(input.periodo_transmision).toHaveLength(1);
    expect(input.periodo_transmision[0].spots_diarios).toBe(50);
  });
});

describe("Selector de OC de origen con filtro de búsqueda — abierta suelta (sin ocIdFijo)", () => {
  function renderSuelto() {
    const oc1 = makeOC({ folio_orden: "OC-2026-0041", numero_orden_cliente: "PO-cliente-001", estatus_orden: "orden_interna" });
    const oc2 = makeOC({ folio_orden: "OC-2026-0043", numero_orden_cliente: "PO-CLIENTE-V02", estatus_orden: "orden_interna" });
    const onGuardar = vi.fn();
    const onCancelar = vi.fn();
    const utils = render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc1, oc2], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionForm onGuardar={onGuardar} onCancelar={onCancelar} />
      </OrdenesProvider>,
    );
    return { ...utils, oc1, oc2 };
  }

  it("escribir en el buscador filtra la lista por folio o número de orden", () => {
    const { container, oc1, oc2 } = renderSuelto();
    const buscador = fieldByLabelText<HTMLInputElement>(container, "Orden del cliente de origen");
    fireEvent.change(buscador, { target: { value: "0043" } });

    expect(screen.getByText(`${oc2.folio_orden} — ${oc2.numero_orden_cliente}`)).toBeInTheDocument();
    expect(screen.queryByText(`${oc1.folio_orden} — ${oc1.numero_orden_cliente}`)).toBeNull();
  });

  it("elegir una opción de la lista selecciona esa OC (aparece la sección 'Estación')", () => {
    const { container, oc2 } = renderSuelto();
    const buscador = fieldByLabelText<HTMLInputElement>(container, "Orden del cliente de origen");
    fireEvent.change(buscador, { target: { value: "V02" } });
    fireEvent.mouseDown(screen.getByText(`${oc2.folio_orden} — ${oc2.numero_orden_cliente}`));

    expect(screen.getByText("Estación")).toBeInTheDocument();
    expect((fieldByLabelText<HTMLInputElement>(container, "Orden del cliente de origen")).value).toBe(
      `${oc2.folio_orden} — ${oc2.numero_orden_cliente}`,
    );
  });
});
