import { describe, expect, it } from "vitest";

import { fmtMoneda } from "../format";

describe("fmtMoneda", () => {
  it("formatea un string decimal como moneda MXN con 2 decimales", () => {
    expect(fmtMoneda("11600.00")).toBe("$11,600.00");
  });

  it("regresa — para null, undefined o vacío", () => {
    expect(fmtMoneda(null)).toBe("—");
    expect(fmtMoneda(undefined)).toBe("—");
    expect(fmtMoneda("")).toBe("—");
  });

  it("regresa — para un string no numérico", () => {
    expect(fmtMoneda("no-es-un-numero")).toBe("—");
  });

  it("fix: siempre trunca a 2 decimales sin redondear (columna Total de la tabla de afiliado)", () => {
    // `toLocaleString` por sí solo redondearía 388488.635 -> $388,488.64; `fmtMoneda`
    // corta el string en 388488.63 antes de convertir a número, para no redondear.
    expect(fmtMoneda("388488.635")).toBe("$388,488.63");
    expect(fmtMoneda("100.999")).toBe("$100.99");
  });

  it("un valor que ya trae exactamente 2 decimales no se altera", () => {
    expect(fmtMoneda("334904.00")).toBe("$334,904.00");
  });
});
