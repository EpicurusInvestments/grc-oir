/** ADR-246 (petición del usuario): `SearchableSelect` gana capacidad "creatable" — si lo
 * escrito no coincide con ninguna opción, ofrece un renglón "+ Crear "..."" al final de la
 * lista. El componente NO sabe cómo se crea (eso lo resuelve quien lo use vía `onCreate`);
 * aquí solo se prueba el contrato del combo en sí, no ninguna mutación real.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { SearchableSelect } from "@/shared/ui/SearchableSelect";

const OPCIONES = [
  { value: "a", label: "Opción A" },
  { value: "b", label: "Opción B" },
];

function Controlado(props: {
  onCreate?: (texto: string) => void;
  creando?: boolean;
  valorInicial?: string;
}) {
  const [value, setValue] = useState(props.valorInicial ?? "");
  return (
    <SearchableSelect
      value={value}
      onChange={setValue}
      options={OPCIONES}
      onCreate={props.onCreate}
      creando={props.creando}
    />
  );
}

describe("SearchableSelect", () => {
  it("filtra opciones por substring y elegir una la selecciona", () => {
    render(<Controlado />);
    const input = screen.getByRole("textbox") as HTMLInputElement;

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "B" } });
    expect(screen.queryByText("Opción A")).toBeNull();
    fireEvent.mouseDown(screen.getByText("Opción B"));

    expect(input.value).toBe("Opción B");
  });

  it("sin onCreate, nunca ofrece crear aunque el texto no coincida con nada", () => {
    render(<Controlado />);
    const input = screen.getByRole("textbox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Motivo que no existe" } });
    expect(screen.queryByText(/\+ Crear/)).toBeNull();
    expect(screen.getByText("Sin resultados.")).toBeInTheDocument();
  });

  it("con onCreate, ofrece '+ Crear \"texto\"' solo si no coincide con ninguna opción existente", () => {
    render(<Controlado onCreate={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.focus(input);

    fireEvent.change(input, { target: { value: "Opción A" } }); // coincide EXACTO
    expect(screen.queryByText('+ Crear "Opción A"')).toBeNull();

    fireEvent.change(input, { target: { value: "Motivo nuevo" } });
    expect(screen.getByText('+ Crear "Motivo nuevo"')).toBeInTheDocument();
  });

  it("elegir '+ Crear' llama a onCreate con el texto (recortado) y cierra la lista", () => {
    const onCreate = vi.fn();
    render(<Controlado onCreate={onCreate} />);
    const input = screen.getByRole("textbox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "  Motivo nuevo  " } });

    fireEvent.mouseDown(screen.getByText('+ Crear "Motivo nuevo"'));

    expect(onCreate).toHaveBeenCalledWith("Motivo nuevo");
    expect(screen.queryByText('+ Crear "Motivo nuevo"')).toBeNull(); // la lista se cerró
  });

  it("mientras creando=true, el renglón dice 'Creando…' y un segundo click no vuelve a llamar a onCreate", () => {
    const onCreate = vi.fn();
    render(<Controlado onCreate={onCreate} creando />);
    const input = screen.getByRole("textbox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Motivo nuevo" } });

    const renglon = screen.getByText("Creando…");
    fireEvent.mouseDown(renglon);

    expect(onCreate).not.toHaveBeenCalled();
  });

  it("si el valor seleccionado no está en las opciones (p.ej. recién creado), lo muestra tal cual en vez de dejarlo vacío", () => {
    render(<Controlado valorInicial="Un motivo que ya no está en el catálogo" />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    expect(input.value).toBe("Un motivo que ya no está en el catálogo");
  });
});
