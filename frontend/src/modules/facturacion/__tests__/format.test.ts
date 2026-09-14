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

  it("fix: truncar corta a 2 decimales sin redondear (columna Total de la tabla de afiliado)", () => {
    // Sin `truncar`, el default ya redondearía 388488.635 -> $388,488.64; con `truncar`,
    // se corta el string en 388488.63 antes de convertir a número.
    expect(fmtMoneda("388488.635", { truncar: true })).toBe("$388,488.63");
    expect(fmtMoneda("100.999", { truncar: true })).toBe("$100.99");
  });

  it("truncar en un valor que ya trae exactamente 2 decimales no lo altera", () => {
    expect(fmtMoneda("334904.00", { truncar: true })).toBe("$334,904.00");
  });
});
