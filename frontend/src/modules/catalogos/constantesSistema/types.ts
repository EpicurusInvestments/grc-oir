/** Tipos de ConstantesSistema, alineados al backend (app/modules/catalogos/constantes_sistema.py
 * e importacion_csv.py). Los valores de `grupo` y los estados del reporte son EXACTOS a los
 * de la spec/backend; el front nunca los inventa.
 */

import type { CatalogoBase, ListParams } from "@/shared/types";

/** Los 9 grupos SAT/timbrador, en el orden de la pantalla aprobada. */
export const GRUPOS = [
  "TipoComprobante",
  "Serie",
  "RegimenFiscal",
  "ClaveProdServ",
  "ClaveUnidad",
  "UsoCFDI",
  "FormaPago",
  "MetodoPago",
  "MonedaSAT",
] as const;

export type GrupoConstante = (typeof GRUPOS)[number];

/** Etiqueta larga de cada grupo (encabezado del banner y tooltip de la pill). */
export const GRUPO_LABEL: Record<GrupoConstante, string> = {
  TipoComprobante: "Tipo de comprobante CFDI",
  Serie: "Serie de la factura",
  RegimenFiscal: "Régimen fiscal SAT",
  ClaveProdServ: "Clave de producto/servicio SAT",
  ClaveUnidad: "Clave de unidad SAT",
  UsoCFDI: "Uso del CFDI",
  FormaPago: "Forma de pago SAT",
  MetodoPago: "Método de pago SAT",
  MonedaSAT: "Moneda",
};

/** Descripción del grupo (banner al filtrar por un grupo). */
export const GRUPO_DESC: Record<GrupoConstante, string> = {
  TipoComprobante:
    'Tipo de CFDI emitido. "33" es el formato legacy del timbrador externo; "I/E/P" son los códigos CFDI 4.0.',
  Serie: "Cadena que identifica la serie de la factura emisora. Cada empresa facturadora usa una serie distinta.",
  RegimenFiscal: "Régimen fiscal del emisor según catálogo SAT c_RegimenFiscal.",
  ClaveProdServ:
    "Clave del producto/servicio según catálogo SAT c_ClaveProdServ. OIR factura típicamente servicios de publicidad.",
  ClaveUnidad: 'Unidad de medida del concepto facturado. Para servicios suele ser "E48".',
  UsoCFDI: "Catálogo SAT c_UsoCFDI. El receptor elige el uso que dará a la factura.",
  FormaPago: "Catálogo SAT c_FormaPago. Medio por el que se realiza el pago.",
  MetodoPago: "PUE (pago en una sola exhibición) o PPD (pago en parcialidades o diferido).",
  MonedaSAT: "Catálogo SAT c_Moneda. MXN es el default.",
};

export interface ConstanteSistema extends CatalogoBase {
  constante_sistema_id: string;
  grupo: GrupoConstante;
  clave: string;
  descripcion: string;
  valor: string | null;
}

export interface ConstanteSistemaCreate {
  grupo: GrupoConstante;
  clave: string;
  descripcion: string;
  valor?: string | null;
}

/** El backend solo permite editar descripción y valor (grupo/clave = identidad natural). */
export interface ConstanteSistemaUpdate {
  descripcion?: string | null;
  valor?: string | null;
}

/** `ListParams` + filtro por grupo. */
export interface ConstantesListParams extends ListParams {
  grupo?: GrupoConstante | null;
}

export interface ConteoGrupo {
  grupo: GrupoConstante;
  total: number;
}

// ── Importación masiva CSV (gemelos de importacion_csv.py) ────────────────────────
export type ModoDuplicados = "actualizar" | "omitir" | "rechazar";

export type EstadoFila = "creada" | "actualizada" | "omitida" | "rechazada";

export interface FilaResultado {
  numero: number;
  grupo: string | null;
  clave: string | null;
  estado: EstadoFila;
  motivo: string | null;
}

export interface ResultadoImportacion {
  commit: boolean;
  total_filas: number;
  creadas: number;
  actualizadas: number;
  omitidas: number;
  rechazadas: number;
  errores_estructura: string[];
  filas: FilaResultado[];
}
