/** Tanda 3: cascada de selectores, snapshots de comisión y congelamiento del formulario de
 * OrdenCliente (1.5 parte de UI, 1.7, 1.8). `state/catalogosCache.ts` nace vacío, así que
 * `contratosVigentesDeAnunciante`/`marcasDeAnunciante` (cableadas a esos arreglos, no reciben
 * el catálogo como parámetro) no tienen nada que filtrar hasta que se siembra aquí abajo.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { ODC_REVIEW_CHECKLIST } from "../constants";
import { OrdenClienteForm } from "../ordenCliente/components/OrdenClienteForm";
import { agencias, anunciantes, contratos, marcas, vendedores } from "../state/catalogosCache";
import { fieldByLabelText } from "./domHelpers";
import { makeOCInput } from "./fixtures";

// Sembrado una sola vez, a nivel de módulo: an1/an3 sugieren ag1, an2 sugiere ag2 — cubre la
// cascada anunciante→agencia/contrato/marca y los defaults de comisión de vendedor/agencia.
agencias.push(
  { id: "ag1", nombre_agencia: "Agencia Uno", rfc_agencia: "AG1010101XX1", porcentaje_comision_agencia_default: 10 },
  { id: "ag2", nombre_agencia: "Agencia Dos", rfc_agencia: "AG2020202XX2", porcentaje_comision_agencia_default: 12 },
  { id: "ag3", nombre_agencia: "Agencia Tres", rfc_agencia: "AG3030303XX3", porcentaje_comision_agencia_default: 8 },
);
anunciantes.push(
  {
    id: "an1",
    agencia_id: "ag1",
    nombre_comercial: "Televisa Publicidad",
    nombre_fiscal: "Televisa Publicidad SA de CV",
    rfc_anunciante: "TPU900101XX1",
    dias_credito_default: 30,
    categoria_id: "",
  },
  {
    id: "an2",
    agencia_id: "ag2",
    nombre_comercial: "Grupo Bimbo",
    nombre_fiscal: "Grupo Bimbo SA de CV",
    rfc_anunciante: "GBI900101XX1",
    dias_credito_default: 30,
    categoria_id: "",
  },
  {
    id: "an3",
    agencia_id: "ag1",
    nombre_comercial: "Coca-Cola",
    nombre_fiscal: "Coca-Cola FEMSA SA de CV",
    rfc_anunciante: "CCF900101XX1",
    dias_credito_default: 30,
    categoria_id: "",
  },
);
contratos.push(
  { id: "co1", anunciante_id: "an1", numero_contrato: "CT-2025-001", nombre_contrato: "Campaña Verano 2025", estado_contrato: "vigente" },
  { id: "co1b", anunciante_id: "an1", numero_contrato: "CT-2024-098", nombre_contrato: "Anual 2024 (cerrado)", estado_contrato: "finalizado" },
  { id: "co2", anunciante_id: "an2", numero_contrato: "CT-2025-002", nombre_contrato: "Anual 2025 - Grupo Bimbo", estado_contrato: "vigente" },
);
marcas.push(
  { id: "mc1", anunciante_id: "an1", nombre_marca: "Televisa Deportes" },
  { id: "mc2", anunciante_id: "an1", nombre_marca: "Televisa Novelas" },
  { id: "mc3", anunciante_id: "an2", nombre_marca: "Pan Bimbo" },
);
vendedores.push(
  { id: "ve1", nombre_vendedor: "Renata Aguilar", porcentaje_comision_default: 5 },
  { id: "ve2", nombre_vendedor: "Roberto López", porcentaje_comision_default: 4 },
);

function renderForm(props: Partial<ComponentProps<typeof OrdenClienteForm>> = {}) {
  const onGuardar = vi.fn();
  const onCancelar = vi.fn();
  const utils = render(
    <OrdenClienteForm title="Nueva orden" onGuardar={onGuardar} onCancelar={onCancelar} {...props} />,
  );
  return { ...utils, onGuardar, onCancelar };
}

describe("Cascada anunciante → contrato / marca (1.7)", () => {
  it("elegir un anunciante filtra sus contratos vigentes y sus marcas", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Anunciante"), { target: { value: "an1" } });

    const opcionesContrato = Array.from(fieldByLabelText<HTMLSelectElement>(container, "Contrato").options).map((o) => o.textContent);
    expect(opcionesContrato).toContain("Campaña Verano 2025");
    expect(opcionesContrato).not.toContain("Anual 2025 - Grupo Bimbo");
    expect(opcionesContrato).not.toContain("Anual 2024 (cerrado)"); // co1b: finalizado, no vigente

    const opcionesMarca = Array.from(fieldByLabelText<HTMLSelectElement>(container, "Marca").options).map((o) => o.textContent);
    expect(opcionesMarca).toContain("Televisa Deportes");
    expect(opcionesMarca).toContain("Televisa Novelas");
    expect(opcionesMarca).not.toContain("Pan Bimbo");
  });

  it("cambiar de anunciante limpia el contrato y la marca ya seleccionados", () => {
    const { container } = renderForm();
    const anuncianteSelect = fieldByLabelText<HTMLSelectElement>(container, "Anunciante");
    fireEvent.change(anuncianteSelect, { target: { value: "an1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Contrato"), { target: { value: "co1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Marca"), { target: { value: "mc1" } });

    expect(fieldByLabelText<HTMLSelectElement>(container, "Contrato").value).toBe("co1");
    expect(fieldByLabelText<HTMLSelectElement>(container, "Marca").value).toBe("mc1");

    fireEvent.change(anuncianteSelect, { target: { value: "an2" } });

    expect(fieldByLabelText<HTMLSelectElement>(container, "Contrato").value).toBe("");
    expect(fieldByLabelText<HTMLSelectElement>(container, "Marca").value).toBe("");
  });

  it("elegir un anunciante con agencia asociada sugiere la agencia y hereda la dirección de facturación", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Anunciante"), { target: { value: "an1" } }); // agencia_id: ag1

    expect(fieldByLabelText<HTMLSelectElement>(container, "Agencia").value).toBe("ag1");
    expect(fieldByLabelText<HTMLInputElement>(container, "Dirección de facturación").value).toBe(
      "Televisa Publicidad SA de CV · RFC TPU900101XX1",
    );
  });

  it("si el usuario ya eligió una agencia a mano, cambiar de anunciante no la sobrescribe (sugiere, no fuerza)", () => {
    const { container } = renderForm();
    const anuncianteSelect = fieldByLabelText<HTMLSelectElement>(container, "Anunciante");
    fireEvent.change(anuncianteSelect, { target: { value: "an2" } }); // sugiere ag2
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Agencia"), { target: { value: "ag3" } }); // el usuario la cambia a mano

    fireEvent.change(anuncianteSelect, { target: { value: "an3" } }); // sugeriría ag1

    expect(fieldByLabelText<HTMLSelectElement>(container, "Agencia").value).toBe("ag3");
  });
});

describe("Snapshots de comisión — 1.8", () => {
  it("elegir un vendedor principal sugiere su % de comisión default del catálogo", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal"), { target: { value: "ve1" } }); // Renata Aguilar, default 5
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal").value).toBe("5");
  });

  it("elegir una agencia sugiere su % de comisión default del catálogo", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Agencia"), { target: { value: "ag1" } }); // default 10
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").value).toBe("10");
  });

  it("fix: cambiar de una agencia a otra SÍ actualiza el % (a diferencia de vendedor, no se respeta el valor anterior)", () => {
    const { container } = renderForm();
    const agenciaSelect = fieldByLabelText<HTMLSelectElement>(container, "Agencia");
    fireEvent.change(agenciaSelect, { target: { value: "ag1" } }); // default 10
    fireEvent.change(agenciaSelect, { target: { value: "ag2" } }); // default 12
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").value).toBe("12");
  });

  it("volver a 'Sin agencia' limpia el % de comisión agencia", () => {
    const { container } = renderForm();
    const agenciaSelect = fieldByLabelText<HTMLSelectElement>(container, "Agencia");
    fireEvent.change(agenciaSelect, { target: { value: "ag1" } });
    fireEvent.change(agenciaSelect, { target: { value: "" } });
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").value).toBe("");
  });

  it("si el % ya se capturó a mano, cambiar de vendedor no lo sobrescribe", () => {
    const { container } = renderForm();
    const vendedorSelect = fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal");
    fireEvent.change(vendedorSelect, { target: { value: "ve1" } }); // auto-llena 5
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal"), { target: { value: "8" } });

    fireEvent.change(vendedorSelect, { target: { value: "ve2" } }); // Roberto López, default 4

    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal").value).toBe("8");
  });

  it("el badge dice 'del catálogo' cuando coincide con el default, y 'sobrescrito' cuando se modifica a mano", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal"), { target: { value: "ve1" } });
    expect(screen.getByText("del catálogo")).toBeInTheDocument();

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal"), { target: { value: "8" } });
    expect(screen.getByText(/sobrescrito \(cat: 5%\)/)).toBeInTheDocument();
  });

  it("fix: el campo 'Motivo del cambio' es UNO SOLO, compartido entre los 3 % (antes solo existía junto al de agencia)", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna" });
    expect(screen.getAllByText("Motivo del cambio")).toHaveLength(1);
  });

  it("fix: cambiar un % de comisión sin capturar el motivo YA NO se guarda — bloquea el envío y marca el campo como obligatorio", async () => {
    const defaultValues = makeOCInput({ vendedor_principal_id: "ve1", porcentaje_comision_vendedor_principal_snap: 5 });
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(screen.getByText("El motivo es obligatorio al cambiar un % de comisión.")).toBeInTheDocument());
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("si sí se captura el motivo (compartido para los 3 %), se propaga con el cambio", async () => {
    const defaultValues = makeOCInput({ agencia_id: "ag1", porcentaje_comision_agencia_snap: 15 });
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia"), { target: { value: "20" } });
    fireEvent.change(screen.getByPlaceholderText("Requerido al modificar el valor…"), {
      target: { value: "Ajuste autorizado por dirección" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
    const [, opts] = onGuardar.mock.calls[0];
    expect(opts.motivoComision).toBe("Ajuste autorizado por dirección");
  });
});

describe("Checklist de Vo.Bo. — transición 1.1 → 1.2 (1.5)", () => {
  it("con 9 de 10 ítems marcados, 'Dar Vo.Bo.' permanece deshabilitado", () => {
    renderForm();
    for (const item of ODC_REVIEW_CHECKLIST.slice(0, 9)) {
      fireEvent.click(screen.getByRole("checkbox", { name: item.label }));
    }
    expect(screen.getByRole("button", { name: /Dar Vo\.Bo\./ })).toBeDisabled();
  });

  it("con los 10 ítems marcados, 'Dar Vo.Bo.' se habilita", () => {
    renderForm();
    for (const item of ODC_REVIEW_CHECKLIST) {
      fireEvent.click(screen.getByRole("checkbox", { name: item.label }));
    }
    expect(screen.getByRole("button", { name: /Dar Vo\.Bo\./ })).toBeEnabled();
  });

  it("al editar una OC que ya tiene Vo.Bo., el checklist ni el botón se muestran", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna" });
    expect(screen.queryByText("Checklist de revisión (PO §2)")).toBeNull();
    expect(screen.queryByRole("button", { name: /Dar Vo\.Bo\./ })).toBeNull();
  });
});

describe("Congelamiento (FROZEN_STATES) — 1.5", () => {
  it("congelada: los 3 campos de % de comisión siguen editables (la autorización real la valida el backend, canal dedicado)", () => {
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_cerrada" });
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal").disabled).toBe(false);
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor secundario").disabled).toBe(false);
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").disabled).toBe(false);
  });

  it("fix: una OC congelada deshabilita el RESTO del formulario también, no solo las comisiones (antes 'Total de spots' quedaba editable)", () => {
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_cerrada" });
    expect(fieldByLabelText<HTMLInputElement>(container, "Total de spots").disabled).toBe(true);
    expect(fieldByLabelText<HTMLInputElement>(container, "No. de orden del cliente").disabled).toBe(true);
    expect(fieldByLabelText<HTMLSelectElement>(container, "Anunciante").disabled).toBe(true);
  });
});

describe("Validación: fecha de inicio de campaña no puede ser pasada", () => {
  it("al crear, una fecha de inicio pasada muestra error y no llama a onGuardar", async () => {
    const { container, onGuardar } = renderForm();
    const ayer = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar como recibida/ }));

    expect(await screen.findByText("La fecha de inicio no puede ser una fecha pasada.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("al editar sin tocar la fecha, una OC cuya campaña ya inició/pasó no se bloquea", () => {
    const defaultValues = makeOCInput();
    renderForm({
      isEdit: true,
      estatusActual: "orden_interna",
      defaultValues,
    });
    // makeOCInput() usa fechas de 2025-06 (ya pasadas): al dejar la fecha intacta no debe
    // mostrarse el error, aunque el `min` del date-picker ya apunte a hoy.
    expect(screen.queryByText("La fecha de inicio no puede ser una fecha pasada.")).toBeNull();
  });

  it("al editar y CAMBIAR la fecha de inicio a una pasada, sí se bloquea", async () => {
    const defaultValues = makeOCInput();
    const { container, onGuardar } = renderForm({
      isEdit: true,
      estatusActual: "orden_interna",
      defaultValues,
    });
    const ayer = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    expect(await screen.findByText("La fecha de inicio no puede ser una fecha pasada.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });
});
