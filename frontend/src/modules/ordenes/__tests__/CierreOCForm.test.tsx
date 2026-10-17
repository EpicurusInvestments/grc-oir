/** ADR-209 (petición del usuario): "Confirmo que la información de cierre es correcta."
 * se quita de la pantalla "Cerrar orden" — cargar los documentos (o aceptar cerrarla sin
 * ellos) y darle a "Cerrar orden → Estado 3" ya es suficiente, sin un paso de
 * confirmación aparte.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CierreOCForm } from "../cierre/components/CierreOCForm";
import { makeOC } from "./fixtures";

describe("CierreOCForm", () => {
  it("ya no muestra el checkbox de confirmación", () => {
    render(
      <CierreOCForm oc={makeOC()} oesDeLaOC={[]} incidencias={[]} onConfirmar={vi.fn()} onCancelar={vi.fn()} />,
    );
    expect(screen.queryByText("Confirmo que la información de cierre es correcta.")).not.toBeInTheDocument();
  });

  it("'Cerrar orden → Estado 3' está habilitado desde el inicio, sin documentos cargados", () => {
    const onConfirmar = vi.fn();
    render(
      <CierreOCForm oc={makeOC()} oesDeLaOC={[]} incidencias={[]} onConfirmar={onConfirmar} onCancelar={vi.fn()} />,
    );
    const boton = screen.getByRole("button", { name: "Cerrar orden → Estado 3" });
    expect(boton).toBeEnabled();

    boton.click();
    expect(onConfirmar).toHaveBeenCalledWith(
      expect.objectContaining({
        odcCerradaRef: null,
        cartaConciliacionRef: null,
        documentosFaltantes: ["odc_cerrada", "carta_conciliacion"],
      }),
    );
  });
});
