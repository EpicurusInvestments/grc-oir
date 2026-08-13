/** Tipos del módulo de autenticación, alineados a `app/modules/auth/schemas.py`. */

/** Identidad del usuario en sesión (gemelo de `UsuarioSesion`).
 *  `usuario_id` y `email` van en null en modo dev_headers: ese proveedor no consulta la
 *  tabla `usuario`. */
export interface SesionUsuario {
  usuario_id: string | null;
  nombre_usuario: string;
  email: string | null;
  area: string;
}

/** Respuesta de POST /auth/login (gemelo de `SesionOut`). */
export interface SesionOut {
  access_token: string;
  token_type: string;
  expira_en: string;
  usuario: SesionUsuario;
}

export interface LoginIn {
  email: string;
  password: string;
}
