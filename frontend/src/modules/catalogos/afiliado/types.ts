/** Tipos de Afiliado y ContactoAfiliado, alineados a los schemas del backend
 * (app/modules/catalogos/afiliado.py).
 *
 * La Estación tiene pantalla propia desde ADR-094 (`modules/catalogos/estacion/`) — ya
 * no vive en este módulo. Desde ADR-096, el Afiliado tampoco tiene `plaza_id` propio: la
 * plaza es una propiedad de la Estación, no del Afiliado.
 */

import type { CatalogoBase } from "@/shared/types";

export interface Afiliado extends CatalogoBase {
  afiliado_id: string;
  nombre_afiliado: string;
  razon_social_afiliado: string;
  rfc_afiliado: string;
  contacto_nombre: string | null;
  contacto_email: string | null;
  contacto_telefono: string | null;
  /** Derivado (solo lectura): nº de estaciones del afiliado. */
  estaciones_count: number;
}

export interface AfiliadoCreate {
  nombre_afiliado: string;
  razon_social_afiliado: string;
  rfc_afiliado: string;
  contacto_nombre?: string | null;
  contacto_email?: string | null;
  contacto_telefono?: string | null;
}

export type AfiliadoUpdate = Partial<AfiliadoCreate>;

// ── ContactoAfiliado (anidado en Afiliado — entidad nueva, ADR-094) ───────────────
// El Afiliado ya trae un solo contacto plano (`contacto_nombre`/`contacto_email`/
// `contacto_telefono`, arriba) — queda como LEGADO, sin tocar. Este es el nuevo
// "varios contactos", mismo patrón anidado que `ContactoAnunciante`/`ContactoAgencia`.
export interface ContactoAfiliado extends CatalogoBase {
  contacto_afiliado_id: string;
  afiliado_id: string;
  nombre_contacto: string;
  puesto_contacto: string | null;
  telefono_contacto: string | null;
  email_contacto: string | null;
}

export interface ContactoAfiliadoCreate {
  afiliado_id: string;
  nombre_contacto: string;
  puesto_contacto?: string | null;
  telefono_contacto?: string | null;
  email_contacto?: string | null;
}

export type ContactoAfiliadoUpdate = Partial<Omit<ContactoAfiliadoCreate, "afiliado_id">> & {
  afiliado_id?: string;
};
