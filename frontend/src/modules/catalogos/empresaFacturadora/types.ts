/** Tipos de EmpresaFacturadora, alineados al backend
 * (app/modules/catalogos/empresa_facturadora.py). `direccion_empresa` es texto largo. */

import type { CatalogoBase } from "@/shared/types";

export interface EmpresaFacturadora extends CatalogoBase {
  empresa_facturadora_id: string;
  nombre_empresa: string;
  rfc_empresa: string;
  direccion_empresa: string | null;
}

export interface EmpresaFacturadoraCreate {
  nombre_empresa: string;
  rfc_empresa: string;
  direccion_empresa?: string | null;
}

export type EmpresaFacturadoraUpdate = Partial<EmpresaFacturadoraCreate>;
