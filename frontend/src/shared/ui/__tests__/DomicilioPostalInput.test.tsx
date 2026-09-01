/** Pruebas del domicilio estructurado con autocompletado por CP (ADR-059).
 *
 * Cubre las 3 rutas de la búsqueda por código postal: una sola colonia (autocompleta
 * sola), varias colonias (lista para elegir) y CP sin resultados (aviso, captura
 * manual) — más que todos los campos, incluidos los autocompletados, quedan editables.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  DomicilioPostalInput,
  type DomicilioPostalValues,
} from "@/shared/ui/DomicilioPostalInput";

const buscarCodigoPostalMock = vi.fn();

vi.mock("@/modules/catalogos/codigoPostal/api", () => ({
  buscarCodigoPostal: (cp: string) => buscarCodigoPostalMock(cp),
}));

const VACIO: DomicilioPostalValues = {
  calle: "",
  numero_exterior: "",
  numero_interior: "",
  colonia: "",
  localidad: "",
  referencia_domicilio: "",
  municipio: "",
  estado: "",
  pais: "",
  codigo_postal: "",
};

function Wrapper() {
  const [values, setValues] = useState<DomicilioPostalValues>(VACIO);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <DomicilioPostalInput
        values={values}
        onChange={(patch) => setValues((v) => ({ ...v, ...patch }))}
      />
    </QueryClientProvider>
  );
}

const escribirCp = (cp: string) => {
  const input = screen.getByPlaceholderText("00000");
  fireEvent.change(input, { target: { value: cp } });
  return input;
};

describe("DomicilioPostalInput", () => {
  it("una sola colonia se autocompleta sola", async () => {
    buscarCodigoPostalMock.mockResolvedValue([
      {
        codigo_postal: "11950",
        asentamiento: "Lomas Altas",
        tipo_asentamiento: "Colonia",
        municipio: "Miguel Hidalgo",
        estado: "Ciudad de México",
        ciudad: "Ciudad de México",
        pais: "MEX",
      },
    ]);
    render(<Wrapper />);
    escribirCp("11950");

    await waitFor(() => expect(screen.getByDisplayValue("Lomas Altas")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Miguel Hidalgo")).toBeInTheDocument();
    // "Ciudad de México" llena TANTO Estado como Localidad/Ciudad en este ejemplo.
    expect(screen.getAllByDisplayValue("Ciudad de México")).toHaveLength(2);
  });

  it("varias colonias se ofrecen en una lista para elegir", async () => {
    buscarCodigoPostalMock.mockResolvedValue([
      {
        codigo_postal: "06700",
        asentamiento: "Roma Norte",
        tipo_asentamiento: "Colonia",
        municipio: "Cuauhtémoc",
        estado: "Ciudad de México",
        ciudad: "Ciudad de México",
        pais: "MEX",
      },
      {
        codigo_postal: "06700",
        asentamiento: "Roma Sur",
        tipo_asentamiento: "Colonia",
        municipio: "Cuauhtémoc",
        estado: "Ciudad de México",
        ciudad: "Ciudad de México",
        pais: "MEX",
      },
    ]);
    render(<Wrapper />);
    escribirCp("06700");

    const opcion = await screen.findByText("Roma Norte");
    // Todavía no se autocompleta nada (hay que elegir).
    expect(screen.queryByDisplayValue("Cuauhtémoc")).not.toBeInTheDocument();

    fireEvent.mouseDown(opcion);
    await waitFor(() => expect(screen.getByDisplayValue("Cuauhtémoc")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Roma Norte")).toBeInTheDocument();
  });

  it("un CP sin resultados avisa y deja la captura manual", async () => {
    buscarCodigoPostalMock.mockResolvedValue([]);
    render(<Wrapper />);
    escribirCp("00000");

    expect(
      await screen.findByText(/No encontramos ese CP en el catálogo/),
    ).toBeInTheDocument();

    // La captura sigue siendo manual: se puede escribir colonia a mano.
    const colonia = screen.getAllByRole("textbox")[1]; // CP es el primer input, Colonia el segundo
    fireEvent.change(colonia, { target: { value: "Colonia Capturada a Mano" } });
    expect(screen.getByDisplayValue("Colonia Capturada a Mano")).toBeInTheDocument();
  });

  it("un campo autocompletado se puede corregir a mano después", async () => {
    buscarCodigoPostalMock.mockResolvedValue([
      {
        codigo_postal: "11950",
        asentamiento: "Lomas Altas",
        tipo_asentamiento: "Colonia",
        municipio: "Miguel Hidalgo",
        estado: "Ciudad de México",
        ciudad: "Ciudad de México",
        pais: "MEX",
      },
    ]);
    render(<Wrapper />);
    escribirCp("11950");
    const colonia = await screen.findByDisplayValue("Lomas Altas");

    fireEvent.change(colonia, { target: { value: "Lomas Altas (corregido a mano)" } });
    expect(screen.getByDisplayValue("Lomas Altas (corregido a mano)")).toBeInTheDocument();
  });

  it("fix: al borrar el código postal se limpian colonia/municipio/estado/localidad/país", async () => {
    buscarCodigoPostalMock.mockResolvedValue([
      {
        codigo_postal: "11950",
        asentamiento: "Lomas Altas",
        tipo_asentamiento: "Colonia",
        municipio: "Miguel Hidalgo",
        estado: "Ciudad de México",
        ciudad: "Ciudad de México",
        pais: "MEX",
      },
    ]);
    render(<Wrapper />);
    const cpInput = escribirCp("11950");
    await screen.findByDisplayValue("Lomas Altas");

    fireEvent.change(cpInput, { target: { value: "" } });

    expect(screen.queryByDisplayValue("Lomas Altas")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("Miguel Hidalgo")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("Ciudad de México")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("MEX")).not.toBeInTheDocument();
  });
});
