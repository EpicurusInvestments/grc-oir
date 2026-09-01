/** Tipos de EmpresaFacturadora, alineados al backend
 * (app/modules/catalogos/empresa_facturadora.py). `direccion_empresa` es texto largo,
 * legacy — desde ADR-059 la captura real es con el domicilio estructurado de abajo. */

import type { CatalogoBase } from "@/shared/types";

export interface EmpresaFacturadora extends CatalogoBase {
  empresa_facturadora_id: string;
  nombre_empresa: string;
  rfc_empresa: string;
  direccion_empresa: string | null;
  calle: string | null;
  numero_exterior: string | null;
  numero_interior: string | null;
  colonia: string | null;
  localidad: string | null;
  referencia_domicilio: string | null;
  municipio: string | null;
  estado: string | null;
  pais: string | null;
  codigo_postal: string | null;
}

export interface EmpresaFacturadoraCreate {
  nombre_empresa: string;
  rfc_empresa: string;
  direccion_empresa?: string | null;
  calle?: string | null;
  numero_exterior?: string | null;
  numero_interior?: string | null;
  colonia?: string | null;
  localidad?: string | null;
  referencia_domicilio?: string | null;
  municipio?: string | null;
  estado?: string | null;
  pais?: string | null;
  codigo_postal?: string | null;
}

export type EmpresaFacturadoraUpdate = Partial<EmpresaFacturadoraCreate>;
