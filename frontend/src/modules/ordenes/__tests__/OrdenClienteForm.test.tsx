/** Tanda 3: cascada de selectores, snapshots de comisión y congelamiento del formulario de
 * OrdenCliente (1.5 parte de UI, 1.7, 1.8). `state/catalogosCache.ts` nace vacío, así que
 * `contratosVigentesDeAnunciante`/`marcasDeAnunciante` (cableadas a esos arreglos, no reciben
 * el catálogo como parámetro) no tienen nada que filtrar hasta que se siembra aquí abajo.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { OrdenClienteForm } from "../ordenCliente/components/OrdenClienteForm";
import { agencias, anunciantes, contratos, marcas, vendedores } from "../state/catalogosCache";
import { fieldByLabelText } from "./domHelpers";
import { makeOCInput } from "./fixtures";

// ADR-238: misma fórmula local (no UTC) que `hoyLocal()` del formulario — evita que estas
// pruebas se vuelvan flaky por el desfase de huso horario, y los offsets relativos a "hoy"
// (en vez de fechas fijas) evitan que se vuelvan obsoletas conforme pasan los días.
function fechaLocalConOffset(diasOffset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + diasOffset);
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}

// ADR-246: los combos "Motivo del cambio" dejaron de ser `<select>` nativos — ahora son
// `SearchableSelect` (escribir filtra, click en la opción confirma). Reemplaza el viejo
// `fireEvent.change(select, { target: { value } })` para elegir una opción YA existente.
async function elegirEnBuscable(input: HTMLElement, texto: string) {
  fireEvent.change(input, { target: { value: texto } });
  fireEvent.mouseDown(await screen.findByText(texto));
}

// ADR-167: "Producto"/"Duración" se llenan desde el catálogo "Producto Duración" —
// mock del catálogo (sin pegarle a la red real desde jsdom), 2 productos: uno con
// duraciones reales (Spot) y uno cuyo único registro es "sin resultado" (Mención).
vi.mock("@/modules/catalogos/duracionSpot/api", () => ({
  duracionSpotCatalogoApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        { duracion_spot_catalogo_id: "d1", producto: "Spot", descripcion_duracion: "20", activo: true },
        { duracion_spot_catalogo_id: "d2", producto: "Spot", descripcion_duracion: "30", activo: true },
        { duracion_spot_catalogo_id: "d3", producto: "Mención", descripcion_duracion: "sin resultado", activo: true },
      ],
      total: 3,
      page: 1,
      size: 100,
      pages: 1,
    }),
  },
}));

// ADR-180: catálogo Constantes del Sistema (grupo MotivoCambio, clave CambioFecha) para
// el select de "Motivo del cambio" de inicio/fin de campaña.
// ADR-246 (petición del usuario): `crearMotivoCambio` mockeado aparte — el combo ahora es
// "creatable" (ver `SearchableSelect`), así que escribir un motivo que no está en el
// catálogo dispara esta mutación.
const crearMotivoCambioMock = vi.fn();
vi.mock("@/modules/catalogos/constantesSistema/api", () => ({
  constanteApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        { constante_sistema_id: "mc1", grupo: "MotivoCambio", clave: "CambioFecha_1", descripcion: "Se cancelaron spots", valor: null, activo: true },
        { constante_sistema_id: "mc2", grupo: "MotivoCambio", clave: "CambioFecha_2", descripcion: "Se redujo el periodo", valor: null, activo: true },
      ],
      total: 2,
      page: 1,
      size: 100,
      pages: 1,
    }),
    crearMotivoCambio: (payload: unknown) => crearMotivoCambioMock(payload),
  },
}));

// Sembrado una sola vez, a nivel de módulo: an1/an3 sugieren ag1, an2 sugiere ag2 — cubre la
// cascada anunciante→agencia/contrato/marca y los defaults de comisión de vendedor/agencia.
agencias.push(
  // ADR-181: ag1 trae domicilio estructurado (usado por las pruebas de autocompletado);
  // ag2/ag3 se quedan SIN domicilio a propósito (cubren el caso "no lo tiene capturado").
  {
    id: "ag1",
    nombre_agencia: "Agencia Uno",
    rfc_agencia: "AG1010101XX1",
    porcentaje_comision_agencia_default: 10,
    calle: "Calle Agencia 123",
    colonia: "Col. Centro",
    municipio: "CDMX",
    codigo_postal: "06000",
  },
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

// Sembrado aparte (fix: catálogos inactivos no deben aparecer en el formulario de alta):
// una agencia, un anunciante y un vendedor con `activo: false`, además de un anunciante
// EXPLÍCITAMENTE `activo: true` para probar que el default `undefined = activo` de los
// demás fixtures no es lo único que hace pasar la prueba.
agencias.push({ id: "ag-inactiva", nombre_agencia: "Agencia Dada de Baja", rfc_agencia: "AGB900101XX1", porcentaje_comision_agencia_default: 5, activo: false });
anunciantes.push({
  id: "an-inactivo",
  agencia_id: null,
  nombre_comercial: "Anunciante Dado de Baja",
  nombre_fiscal: "Anunciante Dado de Baja SA de CV",
  rfc_anunciante: "ADB900101XX1",
  dias_credito_default: 30,
  categoria_id: "",
  activo: false,
});
vendedores.push({ id: "ve-inactivo", nombre_vendedor: "Vendedor Dado de Baja", porcentaje_comision_default: 3, activo: false });

function renderForm(props: Partial<ComponentProps<typeof OrdenClienteForm>> = {}) {
  const onGuardar = vi.fn();
  const onCancelar = vi.fn();
  // ADR-167: el formulario ahora lee el catálogo "Producto Duración" vía react-query.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <OrdenClienteForm title="Nueva orden" onGuardar={onGuardar} onCancelar={onCancelar} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, onGuardar, onCancelar };
}

describe("ADR-141: 'Facturación directa'/'Facturación a la Agencia' es un radio group mutuamente excluyente", () => {
  it("arranca con 'Facturación directa al cliente' seleccionada por default, y elegir la otra la desmarca", () => {
    const { container } = renderForm();
    // ADR-242: "Facturación a la Agencia" exige tener una agencia seleccionada.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Agencia"), { target: { value: "ag1" } });

    // ADR-181: la etiqueta visible cambió a "Facturación a la Agencia" — el campo real
    // (`afiliado_factura_directo_al_cliente`) sigue siendo el mismo.
    const directa = screen.getByLabelText(/Facturación directa al cliente/) as HTMLInputElement;
    const agencia = screen.getByLabelText(/Facturación a la Agencia/) as HTMLInputElement;
    expect(directa.checked).toBe(true);
    expect(agencia.checked).toBe(false);

    fireEvent.click(agencia);
    expect(agencia.checked).toBe(true);
    expect(directa.checked).toBe(false);

    fireEvent.click(directa);
    expect(directa.checked).toBe(true);
    expect(agencia.checked).toBe(false);
  });
});

describe("ADR-242 (bug reportado por el usuario, con captura): no se puede facturar a la agencia sin una agencia seleccionada", () => {
  it("el radio 'Facturación a la Agencia' está deshabilitado mientras no haya agencia", () => {
    const { container } = renderForm();
    // Nota: no se simula un click sobre el radio deshabilitado — un `disabled` real en el
    // navegador ya impide que el usuario lo seleccione; lo que prueba el bug es que el
    // `disabled` esté puesto, no reimplementar el comportamiento nativo del DOM.
    expect(screen.getByLabelText(/Facturación a la Agencia/)).toBeDisabled();

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Agencia"), { target: { value: "ag1" } });
    expect(screen.getByLabelText(/Facturación a la Agencia/)).toBeEnabled();
  });

  it("si se quita la agencia mientras 'Facturación a la Agencia' está activa, regresa a 'Facturación directa al cliente'", () => {
    const defaultValues = makeOCInput({
      anunciante_id: "an1",
      agencia_id: "ag1",
      afiliado_factura_directo_al_cliente: true,
      facturacion_directa_cliente: false,
    });
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    const directa = screen.getByLabelText(/Facturación directa al cliente/) as HTMLInputElement;
    const agencia = screen.getByLabelText(/Facturación a la Agencia/) as HTMLInputElement;
    expect(agencia.checked).toBe(true);

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Agencia"), { target: { value: "" } });

    expect(agencia.checked).toBe(false);
    expect(directa.checked).toBe(true);
    expect(fieldByLabelText<HTMLTextAreaElement>(container, "Dirección de facturación").value).toBe(
      "Televisa Publicidad SA de CV · RFC TPU900101XX1",
    );
  });

  it("al guardar una orden ya existente sin agencia pero con 'Facturación a la Agencia' (estado inconsistente heredado), muestra el error bajo Agencia", async () => {
    const defaultValues = makeOCInput({
      anunciante_id: "an1",
      agencia_id: null,
      afiliado_factura_directo_al_cliente: true,
      facturacion_directa_cliente: false,
    });
    const { onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.click(screen.getByRole("button", { name: /Guardar/ }));

    expect(await screen.findByText(/Selecciona una agencia para poder facturar a la agencia/)).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe("ADR-181: 'Facturación a la Agencia' autocompleta la dirección con el domicilio de la Agencia", () => {
  it("al elegir 'Facturación a la Agencia', usa el domicilio de la agencia ya ligada a la OC", () => {
    const defaultValues = makeOCInput({ anunciante_id: "an1", agencia_id: "ag1" });
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.click(screen.getByLabelText(/Facturación a la Agencia/));

    expect(fieldByLabelText<HTMLTextAreaElement>(container, "Dirección de facturación").value).toBe(
      "Calle Agencia 123, Col. Centro, CDMX, C.P. 06000",
    );
  });

  it("al volver a 'Facturación directa al cliente', regresa a los datos del anunciante", () => {
    const defaultValues = makeOCInput({ anunciante_id: "an1", agencia_id: "ag1" });
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.click(screen.getByLabelText(/Facturación a la Agencia/));
    fireEvent.click(screen.getByLabelText(/Facturación directa al cliente/));

    expect(fieldByLabelText<HTMLTextAreaElement>(container, "Dirección de facturación").value).toBe(
      "Televisa Publicidad SA de CV · RFC TPU900101XX1",
    );
  });

  it("si la agencia no tiene domicilio capturado, VACÍA el campo para capturarlo a mano", () => {
    const defaultValues = makeOCInput({
      anunciante_id: "an1",
      agencia_id: "ag3",
      direccion_facturacion: "Dirección capturada a mano",
    });
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.click(screen.getByLabelText(/Facturación a la Agencia/));

    expect(fieldByLabelText<HTMLTextAreaElement>(container, "Dirección de facturación").value).toBe("");
  });
});

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

  it("elegir un anunciante con agencia asociada sugiere la agencia, su % de comisión y hereda la dirección de facturación", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Anunciante"), { target: { value: "an1" } }); // agencia_id: ag1

    expect(fieldByLabelText<HTMLSelectElement>(container, "Agencia").value).toBe("ag1");
    // Bug corregido (petición del usuario): la agencia sugerida por el anunciante
    // también debe traer su % de comisión default (ag1 → 10), no dejarlo vacío.
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").value).toBe("10");
    expect(fieldByLabelText<HTMLInputElement>(container, "Dirección de facturación").value).toBe(
      "Televisa Publicidad SA de CV · RFC TPU900101XX1",
    );
  });

  it("si el % de comisión ya se había capturado a mano, sugerir la agencia del anunciante no lo sobrescribe", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia"), {
      target: { value: "20" },
    });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Anunciante"), { target: { value: "an1" } }); // sugeriría ag1 → 10

    expect(fieldByLabelText<HTMLSelectElement>(container, "Agencia").value).toBe("ag1");
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").value).toBe("20");
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

  it("ADR-142 (corrige un bug real): volver a 'Sin vendedor secundario' limpia el % de comisión", () => {
    const { container } = renderForm();
    const vendedorSecundarioSelect = fieldByLabelText<HTMLSelectElement>(container, "Vendedor secundario");
    fireEvent.change(vendedorSecundarioSelect, { target: { value: "ve1" } }); // auto-llena 5
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor secundario").value).toBe("5");

    fireEvent.change(vendedorSecundarioSelect, { target: { value: "" } }); // Sin vendedor secundario

    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor secundario").value).toBe("");
  });

  it("el badge dice 'del catálogo' cuando coincide con el default, y 'sobrescrito' cuando se modifica a mano", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal"), { target: { value: "ve1" } });
    expect(screen.getByText("del catálogo")).toBeInTheDocument();

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal"), { target: { value: "8" } });
    expect(screen.getByText(/sobrescrito \(cat: 5%\)/)).toBeInTheDocument();
  });

  // ADR-249 (petición del usuario): "también debe aplicar cuando es una nueva orden" —
  // en alta no hay un valor guardado contra qué comparar, así que el criterio es
  // "diverge del % sugerido del catálogo" (mismo que el badge "sobrescrito" de arriba).
  it("ADR-249: en alta, si el % diverge del catálogo, exige motivo y bloquea el guardado", async () => {
    const defaultValues = makeOCInput({
      vendedor_principal_id: "ve1", // default 5
      porcentaje_comision_vendedor_principal_snap: 8,
    });
    const { onGuardar } = renderForm({ defaultValues });
    // En alta no existe el combo de fecha (solo aplica en edición, ADR-180) — se
    // espera directo a que resuelva la consulta compartida del catálogo MotivoCambio,
    // usando el propio placeholder del combo de comisión como señal.
    const motivoInput = (await screen.findByPlaceholderText(
      "Requerido al modificar el valor…",
    )) as HTMLInputElement;
    expect(motivoInput.disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(screen.getByText("El motivo es obligatorio al cambiar un % de comisión.")).toBeInTheDocument(),
    );
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("ADR-249: en alta, si el % coincide con el catálogo, NO exige motivo y permite guardar", async () => {
    const defaultValues = makeOCInput({
      vendedor_principal_id: "ve1",
      porcentaje_comision_vendedor_principal_snap: 5, // = default de ve1
    });
    const { onGuardar } = renderForm({ defaultValues });
    const motivoInput = (await screen.findByPlaceholderText(
      "Requerido al modificar el valor…",
    )) as HTMLInputElement;
    expect(motivoInput.disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
  });

  it("ADR-249: en alta, capturando el motivo cuando diverge, sí permite guardar", async () => {
    const defaultValues = makeOCInput({
      vendedor_principal_id: "ve1", // default 5
      porcentaje_comision_vendedor_principal_snap: 8,
    });
    const { onGuardar } = renderForm({ defaultValues });
    const motivoInput = await screen.findByPlaceholderText("Requerido al modificar el valor…");

    // ADR-246: el combo es "creatable" — no hay "CambioComision" en el catálogo
    // mockeado, así que escribir el motivo ofrece "+ Crear" (da de alta y confirma).
    crearMotivoCambioMock.mockResolvedValue({
      constante_sistema_id: "mc-nuevo",
      grupo: "MotivoCambio",
      clave: "CambioComision_1",
      descripcion: "Negociación comercial con el cliente",
      valor: null,
      activo: true,
    });
    fireEvent.change(motivoInput, { target: { value: "Negociación comercial con el cliente" } });
    fireEvent.mouseDown(await screen.findByText('+ Crear "Negociación comercial con el cliente"'));
    await waitFor(() => expect(crearMotivoCambioMock).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
    const [, opts] = onGuardar.mock.calls[0];
    expect(opts.motivoComision).toBe("Negociación comercial con el cliente");
  });

  it("fix: el campo 'Motivo del cambio' de comisión es UNO SOLO, compartido entre los 3 % (antes solo existía junto al de agencia)", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna" });
    // ADR-180: ahora hay 2 — el de comisión (uno solo para los 3 %, lo que prueba este
    // caso) y el nuevo de fechas de campaña (uno solo para inicio/fin) — nunca 3 ni más.
    expect(screen.getAllByText("Motivo del cambio")).toHaveLength(2);
  });

  it("fix: cambiar un % de comisión sin capturar el motivo YA NO se guarda — bloquea el envío y marca el campo como obligatorio", async () => {
    const defaultValues = makeOCInput({ vendedor_principal_id: "ve1", porcentaje_comision_vendedor_principal_snap: 5 });
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(screen.getByText("El motivo es obligatorio al cambiar un % de comisión.")).toBeInTheDocument());
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("si sí se captura el motivo (compartido para los 3 %), se propaga con el cambio — y lo da de alta en el catálogo (ADR-246)", async () => {
    const defaultValues = makeOCInput({ agencia_id: "ag1", porcentaje_comision_agencia_snap: 15 });
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    // ADR-246: el catálogo mockeado no tiene ninguna clave "CambioComision" (solo
    // "CambioFecha_*"), así que escribir ese motivo ofrece "+ Crear" — pero hay que
    // esperar a que la consulta (compartida en caché con la de fecha) resuelva antes de
    // interactuar, o todavía se ve el combo con "Cargando…".
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");
    crearMotivoCambioMock.mockResolvedValue({
      constante_sistema_id: "mc-nuevo",
      grupo: "MotivoCambio",
      clave: "CambioComision_1",
      descripcion: "Ajuste autorizado por dirección",
      valor: null,
      activo: true,
    });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia"), { target: { value: "20" } });
    fireEvent.change(screen.getByPlaceholderText("Requerido al modificar el valor…"), {
      target: { value: "Ajuste autorizado por dirección" },
    });
    fireEvent.mouseDown(await screen.findByText('+ Crear "Ajuste autorizado por dirección"'));

    await waitFor(() =>
      expect(crearMotivoCambioMock).toHaveBeenCalledWith({
        clave_base: "CambioComision",
        descripcion: "Ajuste autorizado por dirección",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
    const [, opts] = onGuardar.mock.calls[0];
    expect(opts.motivoComision).toBe("Ajuste autorizado por dirección");
  });

  // ADR-244 (petición del usuario): antes el campo no tenía esta lógica — vivía siempre
  // habilitado, igual estuviera editado un % o no (mismo bug que ADR-180 ya había
  // corregido para fechas, pero nunca se replicó aquí).
  it("ADR-244: el campo de motivo arranca deshabilitado y se habilita solo al cambiar un % de comisión", async () => {
    // ag1 → catálogo 10: arranca SIN divergencia, para aislar el criterio "cambió en esta
    // sesión" del de "ya diverge del catálogo" (ver siguiente test, bug corregido).
    const defaultValues = makeOCInput({ agencia_id: "ag1", porcentaje_comision_agencia_snap: 10 });
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    const motivoInput = screen.getByPlaceholderText("Requerido al modificar el valor…") as HTMLInputElement;
    expect(motivoInput.disabled).toBe(true);

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia"), { target: { value: "20" } });
    expect(motivoInput.disabled).toBe(false);

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia"), { target: { value: "10" } });
    expect(motivoInput.disabled).toBe(true); // de vuelta al valor original: ya no "cambió"
  });

  it("Bug corregido (petición del usuario, con captura): si el % ya diverge del catálogo desde una edición previa, el combo arranca habilitado aunque no lo toques en esta sesión", async () => {
    // ag1 → catálogo 10; defaultValues trae 15 (ya sobrescrito antes). Antes de este fix,
    // el combo quedaba deshabilitado (inerte, sin poder abrirse) hasta retocar el %, lo
    // que hacía parecer que un motivo recién creado en el catálogo "no salía".
    const defaultValues = makeOCInput({ agencia_id: "ag1", porcentaje_comision_agencia_snap: 15 });
    const { onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    const motivoInput = screen.getByPlaceholderText("Requerido al modificar el valor…") as HTMLInputElement;
    expect(motivoInput.disabled).toBe(false);

    // Nada cambió en esta sesión: guardar sin motivo sigue sin bloquearse.
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
  });

  it("Bug corregido (petición del usuario, con captura — ADR-250): el combo se precarga con el motivo más reciente del historial, no arranca vacío", async () => {
    const defaultValues = makeOCInput({ agencia_id: "ag1", porcentaje_comision_agencia_snap: 15 });
    const historialComisiones = [
      {
        log_cambio_parametro_id: "log-viejo",
        entidad: "OrdenCliente",
        entidad_id: "oc-1",
        campo: "porcentaje_comision_agencia_snap",
        valor_anterior: "10.00",
        valor_nuevo: "15.00",
        usuario: "ventas1",
        ip: null,
        motivo_cambio: "Negociación comercial distinta al % default del catálogo",
        fecha_cambio: "2026-10-01T10:00:00",
      },
      {
        log_cambio_parametro_id: "log-reciente",
        entidad: "OrdenCliente",
        entidad_id: "oc-1",
        campo: "porcentaje_comision_agencia_snap",
        valor_anterior: "15.00",
        valor_nuevo: "15.00",
        usuario: "ventas1",
        ip: null,
        motivo_cambio: "Ajuste en la comisión",
        fecha_cambio: "2026-11-10T09:00:00",
      },
    ];
    renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues, historialComisiones });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    // El más reciente por `fecha_cambio` gana, no el primero del arreglo ni el más viejo.
    expect(screen.getByDisplayValue("Ajuste en la comisión")).toBeInTheDocument();
  });
});

describe("ADR-180: motivo de cambio al editar fechas de campaña", () => {
  it("el select de motivo arranca deshabilitado y se habilita solo al tocar una fecha", async () => {
    const defaultValues = makeOCInput();
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });

    // "Motivo del cambio" de fecha es el PRIMERO en el DOM (sección "Campaña y montos",
    // antes que "Equipo comercial y comisiones") — por eso `fieldByLabelText` (toma el
    // primer match) ya apunta al correcto sin necesitar desambiguar.
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");
    const motivoSelect = fieldByLabelText<HTMLInputElement>(container, "Motivo del cambio");
    expect(motivoSelect.disabled).toBe(true);

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), { target: { value: "2026-11-01" } });
    expect(motivoSelect.disabled).toBe(false);
  });

  it("cambiar una fecha sin elegir motivo bloquea el envío y marca el campo obligatorio", async () => {
    const defaultValues = makeOCInput();
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Fin de campaña"), { target: { value: "2026-12-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() =>
      expect(
        screen.getByText("El motivo es obligatorio al cambiar la fecha de inicio o fin de campaña."),
      ).toBeInTheDocument(),
    );
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("al elegir un motivo del catálogo, se guarda y se manda en el input", async () => {
    const defaultValues = makeOCInput();
    const { container, onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    // Hay que mover también Fin de campaña: el default (2025-06-30) quedaría antes que
    // el nuevo Inicio, lo que violaría "fin >= inicio" y bloquearía el envío por esa
    // razón (no por el motivo, que es lo que esta prueba quiere aislar). Offsets relativos
    // a "hoy" (no fechas fijas) para que la prueba no caduque con el paso del tiempo.
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Fin de campaña"), {
      target: { value: fechaLocalConOffset(45) },
    });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), {
      target: { value: fechaLocalConOffset(10) },
    });
    await elegirEnBuscable(
      fieldByLabelText<HTMLInputElement>(container, "Motivo del cambio"),
      "Se redujo el periodo",
    );
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
    const [input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_fecha).toBe("Se redujo el periodo");
  });

  it("guardar sin tocar las fechas no manda motivo_cambio_fecha", async () => {
    const defaultValues = makeOCInput();
    const { onGuardar } = renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues });
    await screen.findByPlaceholderText("Requerido al modificar la fecha…");

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledTimes(1));
    const [input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_fecha).toBeUndefined();
  });
});

describe("Congelamiento (FROZEN_STATES) — 1.5", () => {
  it("fix: congelada deshabilita también los 3 campos de % de comisión (antes seguían editables)", () => {
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_cerrada" });
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor principal").disabled).toBe(true);
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión vendedor secundario").disabled).toBe(true);
    expect(fieldByLabelText<HTMLInputElement>(container, "% comisión agencia").disabled).toBe(true);
  });

  it("fix: una OC congelada deshabilita el RESTO del formulario también, no solo las comisiones (antes 'Total de spots' quedaba editable)", () => {
    const { container } = renderForm({ isEdit: true, estatusActual: "orden_cerrada" });
    expect(fieldByLabelText<HTMLInputElement>(container, "Total de spots").disabled).toBe(true);
    expect(fieldByLabelText<HTMLInputElement>(container, "No. de orden del cliente").disabled).toBe(true);
    expect(fieldByLabelText<HTMLSelectElement>(container, "Anunciante").disabled).toBe(true);
  });
});

describe("Aviso de tarifa cuando la OC ya tiene OE creadas", () => {
  it("con OE ya creadas, avisa que las existentes quedan con la tarifa anterior", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues: makeOCInput(), oeCount: 2 });
    expect(
      screen.getByText(/Esta orden ya tiene 2 Órdenes de Transmisión creadas con la tarifa anterior/),
    ).toBeInTheDocument();
  });

  it("con una sola OE, usa singular en vez de '1 órdenes'", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues: makeOCInput(), oeCount: 1 });
    expect(
      screen.getByText(/Esta orden ya tiene 1 Orden de Transmisión creada con la tarifa anterior/),
    ).toBeInTheDocument();
  });

  it("sin OE creadas, no muestra ningún aviso", () => {
    renderForm({ isEdit: true, estatusActual: "orden_interna", defaultValues: makeOCInput(), oeCount: 0 });
    expect(screen.queryByText(/tarifa anterior/)).toBeNull();
  });

  it("al crear (no editar) tampoco muestra el aviso, aunque venga un oeCount", () => {
    renderForm({ oeCount: 3 });
    expect(screen.queryByText(/tarifa anterior/)).toBeNull();
  });

  it("con la OC congelada, no muestra el aviso: el formulario ya es de solo lectura", () => {
    renderForm({ isEdit: true, estatusActual: "orden_cerrada", defaultValues: makeOCInput(), oeCount: 2 });
    expect(screen.queryByText(/tarifa anterior/)).toBeNull();
  });
});

describe("Spots bonificables (ADR-067)", () => {
  it("calcula el desglose facturable en vivo: 25 spots a $1,000, 10 bonificables → 15 facturables", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Total de spots"), { target: { value: "25" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables"), { target: { value: "10" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Precio unitario (MXN, por spot)"), {
      target: { value: "1000" },
    });

    // Las 5 tarjetas del bloque "Calculado": subtotal bruto, bonificables, facturable, IVA, total.
    expect(screen.getAllByText("$25,000.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$10,000.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$15,000.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$2,400.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$17,400.00").length).toBeGreaterThan(0);
  });

  it("sin capturar spots bonificables, el desglose facturable coincide con el subtotal bruto (default 0)", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Total de spots"), { target: { value: "100" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Precio unitario (MXN, por spot)"), {
      target: { value: "1000" },
    });

    expect(screen.getAllByText("$100,000.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
  });

  it("rechaza spots bonificables mayores al total de spots y no llama a onGuardar", async () => {
    const { container, onGuardar } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Total de spots"), { target: { value: "10" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("No puede exceder el total de spots.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe("Validación: fecha de inicio de campaña no puede ser pasada", () => {
  it("al crear, una fecha de inicio pasada muestra error y no llama a onGuardar", async () => {
    const { container, onGuardar } = renderForm();
    const ayer = fechaLocalConOffset(-1);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

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
    const ayer = fechaLocalConOffset(-1);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Inicio de campaña"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    expect(await screen.findByText("La fecha de inicio no puede ser una fecha pasada.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe("Validación: fecha de venta no puede ser pasada", () => {
  it("al crear, una fecha de venta pasada muestra error y no llama a onGuardar", async () => {
    const { container, onGuardar } = renderForm();
    const ayer = fechaLocalConOffset(-1);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Fecha de venta"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("La fecha de venta no puede ser una fecha pasada.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("al editar sin tocar la fecha, una OC cuya venta ya se registró en el pasado no se bloquea", () => {
    const defaultValues = makeOCInput();
    renderForm({
      isEdit: true,
      estatusActual: "orden_interna",
      defaultValues,
    });
    // makeOCInput() usa fecha_venta de 2025-05 (ya pasada): al dejarla intacta no debe
    // mostrarse el error, aunque el `min` del date-picker ya apunte a hoy.
    expect(screen.queryByText("La fecha de venta no puede ser una fecha pasada.")).toBeNull();
  });

  it("al editar y CAMBIAR la fecha de venta a una pasada, sí se bloquea", async () => {
    const defaultValues = makeOCInput();
    const { container, onGuardar } = renderForm({
      isEdit: true,
      estatusActual: "orden_interna",
      defaultValues,
    });
    const ayer = fechaLocalConOffset(-1);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Fecha de venta"), {
      target: { value: ayer },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    expect(await screen.findByText("La fecha de venta no puede ser una fecha pasada.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe("Fix: catálogos inactivos no aparecen en el formulario de alta/edición", () => {
  it("agencia inactiva no aparece en el select, la activa sí", () => {
    const { container } = renderForm();
    const select = fieldByLabelText<HTMLSelectElement>(container, "Agencia");
    expect(within(select).getByText("Agencia Uno")).toBeInTheDocument();
    expect(within(select).queryByText("Agencia Dada de Baja")).toBeNull();
  });

  it("anunciante inactivo no aparece en el select, el activo sí", () => {
    const { container } = renderForm();
    const select = fieldByLabelText<HTMLSelectElement>(container, "Anunciante");
    expect(within(select).getByText("Televisa Publicidad")).toBeInTheDocument();
    expect(within(select).queryByText("Anunciante Dado de Baja")).toBeNull();
  });

  it("vendedor inactivo no aparece en el select de vendedor principal ni secundario, el activo sí", () => {
    const { container } = renderForm();
    const selectPrincipal = fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal");
    const selectSecundario = fieldByLabelText<HTMLSelectElement>(container, "Vendedor secundario");
    expect(within(selectPrincipal).getByText("Renata Aguilar")).toBeInTheDocument();
    expect(within(selectPrincipal).queryByText("Vendedor Dado de Baja")).toBeNull();
    expect(within(selectSecundario).getByText("Renata Aguilar")).toBeInTheDocument();
    expect(within(selectSecundario).queryByText("Vendedor Dado de Baja")).toBeNull();
  });
});

// ADR-263 (petición del usuario, con captura): no se debe poder elegir el mismo
// vendedor como principal y secundario a la vez — cada select excluye al que ya está
// seleccionado en el otro.
describe("Fix: no se puede repetir el mismo vendedor como principal y secundario", () => {
  it("elegir un vendedor como principal lo quita de las opciones de secundario", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal"), {
      target: { value: "ve1" },
    });
    const selectSecundario = fieldByLabelText<HTMLSelectElement>(container, "Vendedor secundario");
    expect(within(selectSecundario).queryByText("Renata Aguilar")).toBeNull();
  });

  it("elegir un vendedor como secundario lo quita de las opciones de principal", () => {
    const { container } = renderForm();
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Vendedor secundario"), {
      target: { value: "ve1" },
    });
    const selectPrincipal = fieldByLabelText<HTMLSelectElement>(container, "Vendedor principal");
    expect(within(selectPrincipal).queryByText("Renata Aguilar")).toBeNull();
  });
});

describe("Producto/Duración desde el catálogo Producto Duración — ADR-167/168", () => {
  it("al elegir un producto con duraciones reales, el combo de Duración se llena (sin 'sin resultado')", async () => {
    const { container } = renderForm();
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo")).getByText("Spot")).toBeInTheDocument(),
    );

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo"), { target: { value: "Spot" } });

    const selectDuracion = fieldByLabelText<HTMLSelectElement>(container, "Duración");
    expect(within(selectDuracion).getByText("20")).toBeInTheDocument();
    expect(within(selectDuracion).getByText("30")).toBeInTheDocument();
    expect(within(selectDuracion).queryByText("sin resultado")).toBeNull();
  });

  it("al elegir un producto cuyo único registro es 'sin resultado', Duración queda vacía/deshabilitada y NO bloquea el guardado", async () => {
    // El resto de campos obligatorios ya viene prellenado (makeOCInput) — así se aísla la
    // prueba al comportamiento de Producto/Duración, que es lo que importa aquí.
    const { container, onGuardar } = renderForm({ defaultValues: makeOCInput() });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo")).getByText("Mención")).toBeInTheDocument(),
    );

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo"), { target: { value: "Mención" } });

    const selectDuracion = fieldByLabelText<HTMLSelectElement>(container, "Duración");
    expect(selectDuracion).toBeDisabled();
    expect(within(selectDuracion).queryByText("sin resultado")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    const [input] = onGuardar.mock.calls[0];
    expect(input.producto_tarifa).toBe("Mención");
    expect(input.duracion_spot).toBeNull();
  });

  it("cambiar de producto limpia la duración ya elegida", async () => {
    const { container } = renderForm();
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo")).getByText("Spot")).toBeInTheDocument(),
    );

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo"), { target: { value: "Spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30" } });
    expect(fieldByLabelText<HTMLSelectElement>(container, "Duración").value).toBe("30");

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo"), { target: { value: "Mención" } });
    expect(fieldByLabelText<HTMLSelectElement>(container, "Duración").value).toBe("");
  });

  it("ADR-168: sin elegir Producto, Total de spots/Spots bonificables/Precio unitario quedan deshabilitados y no se puede guardar", async () => {
    const { container, onGuardar } = renderForm({ defaultValues: { ...makeOCInput(), producto_tarifa: null } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo")).getByText("Spot")).toBeInTheDocument(),
    );

    expect(fieldByLabelText<HTMLInputElement>(container, "Total de spots")).toBeDisabled();
    expect(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables")).toBeDisabled();
    expect(fieldByLabelText<HTMLInputElement>(container, "Precio unitario")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Selecciona un producto.")).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it("ADR-168: al elegir un producto, Total de spots/Spots bonificables/Precio unitario se habilitan", async () => {
    const { container } = renderForm({ defaultValues: { ...makeOCInput(), producto_tarifa: null } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo")).getByText("Spot")).toBeInTheDocument(),
    );

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto Catálogo"), { target: { value: "Spot" } });

    expect(fieldByLabelText<HTMLInputElement>(container, "Total de spots")).toBeEnabled();
    expect(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables")).toBeEnabled();
    expect(fieldByLabelText<HTMLInputElement>(container, "Precio unitario")).toBeEnabled();
  });
});
