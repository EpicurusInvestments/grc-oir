/** Tipos de Usuario, alineados a `app/modules/usuarios/schemas.py`. */

/** Áreas de la propuesta. Mismos valores que el ENUM `Area` del backend (y que el CHECK
 *  `ck_usuario_area` de la tabla): el front NUNCA inventa áreas. */
export const AREAS = [
  "ventas",
  "facturacion",
  "tesoreria",
  "cxc",
  "cxp",
  "direccion",
  "nominas",
  "admin",
] as const;

export type Area = (typeof AREAS)[number];

/** Etiquetas legibles para la UI (los valores que viajan a la API son los de arriba). */
export const AREA_LABEL: Record<Area, string> = {
  ventas: "Ventas",
  facturacion: "Facturación",
  tesoreria: "Tesorería",
  cxc: "Cuentas por cobrar",
  cxp: "Cuentas por pagar",
  direccion: "Dirección / Finanzas",
  nominas: "Nóminas",
  admin: "Administración",
};

export const etiquetaArea = (area: string): string =>
  AREA_LABEL[area as Area] ?? area;

/** Gemelo de `UsuarioRead`. NO existe `password_hash`: el backend nunca lo expone; solo
 *  informa con `tiene_password` si el usuario ya puede iniciar sesión. */
export interface Usuario {
  usuario_id: string;
  nombre_usuario: string;
  email: string;
  area: string;
  roles_adicionales: string | null;
  activo: boolean;
  created_at: string;
  tiene_password: boolean;
}

export interface UsuarioCreate {
  nombre_usuario: string;
  email: string;
  area: Area;
  roles_adicionales?: string | null;
  /** Opcional: sin ella el usuario queda dado de alta pero no puede entrar. */
  password?: string | null;
}

export type UsuarioUpdate = Partial<Omit<UsuarioCreate, "password">>;
