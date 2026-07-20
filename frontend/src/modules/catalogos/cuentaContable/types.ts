/** Tipos de CuentaContable, alineados al backend (app/modules/catalogos/cuenta_contable.py). */

import type { CatalogoBase } from "@/shared/types";

/** ENUM `tipo_cuenta` de la spec (VARCHAR + CHECK en la BD). */
export type TipoCuenta = "ingreso" | "costo" | "gasto" | "activo" | "pasivo";

export const TIPO_CUENTA_OPCIONES: { value: TipoCuenta; label: string }[] = [
  { value: "ingreso", label: "Ingreso" },
  { value: "costo", label: "Costo" },
  { value: "gasto", label: "Gasto" },
  { value: "activo", label: "Activo" },
  { value: "pasivo", label: "Pasivo" },
];

export const TIPO_CUENTA_LABEL: Record<TipoCuenta, string> = Object.fromEntries(
  TIPO_CUENTA_OPCIONES.map((o) => [o.value, o.label]),
) as Record<TipoCuenta, string>;

export interface CuentaContable extends CatalogoBase {
  cuenta_contable_id: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta;
}

export interface CuentaContableCreate {
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta;
}

export type CuentaContableUpdate = Partial<CuentaContableCreate>;
