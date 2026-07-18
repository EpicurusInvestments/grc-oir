/** Tipos de Vendedor, alineados al backend (app/modules/catalogos/vendedor.py).
 *
 * `porcentaje_comision_default` es DECIMAL (string) y PARÁMETRO SENSIBLE (auditado), mismo
 * tratamiento que el % de comisión de Agencia en F0-03.
 */

import type { CatalogoBase } from "@/shared/types";

export interface Vendedor extends CatalogoBase {
  vendedor_id: string;
  nombre_vendedor: string;
  email_vendedor: string | null;
  /** DECIMAL como string (p.ej. "5.00"). Sensible: audit log al modificarlo. */
  porcentaje_comision_default: string;
}

export interface VendedorCreate {
  nombre_vendedor: string;
  email_vendedor?: string | null;
  porcentaje_comision_default: string;
}

export interface VendedorUpdate extends Partial<VendedorCreate> {
  /** Requerido por el backend si se modifica el % (parámetro sensible). */
  motivo_cambio?: string | null;
}
