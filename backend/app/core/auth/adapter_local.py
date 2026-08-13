"""Adaptador de autenticación LOCAL: email + contraseña contra la tabla `usuario`.

Es el proveedor por defecto (`AUTH_PROVIDER=local`) y el que se usa en las demos: el
sistema pide login real sin depender de que Azure AD esté configurado.

Dos garantías que no son negociables aquí:

1. **Mensaje de error único.** Usuario inexistente, contraseña incorrecta, usuario
   inactivo y usuario sin contraseña producen EXACTAMENTE la misma respuesta. Además se
   verifica siempre una contraseña (real o señuelo) para que el tiempo tampoco delate.
2. **El estado del usuario se relee de la BD en cada request.** El token dice quién dice
   ser; la tabla dice si sigue activo y en qué área está. Así, desactivar a alguien o
   cambiarle el área surte efecto de inmediato en lugar de esperar a que expire su token.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth.identity import Area, CurrentUser
from app.core.auth.passwords import verificar_password
from app.core.auth.port import SesionEmitida
from app.core.auth.tokens import emitir_token, leer_token
from app.core.errors import AuthenticationError
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository

_CREDENCIALES_INVALIDAS = "Usuario o contraseña incorrectos."
_SIN_SESION = "Se requiere iniciar sesión."
_SESION_REVOCADA = "La sesión ya no es válida. Vuelve a iniciar sesión."


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _token_del_header(request: Request) -> str:
    """Extrae el token de `Authorization: Bearer <token>`. 401 si no viene."""
    encabezado = request.headers.get("Authorization", "")
    esquema, _, token = encabezado.partition(" ")
    if esquema.strip().lower() != "bearer" or not token.strip():
        raise AuthenticationError(_SIN_SESION)
    return token.strip()


def _a_current_user(usuario: Usuario, ip: str | None) -> CurrentUser:
    try:
        area = Area(usuario.area)
    except ValueError as exc:
        # El CHECK `ck_usuario_area` lo impide en la BD; defensa en profundidad por si el
        # dato llegara de una carga manual. Falla cerrada: no se asume un área.
        raise AuthenticationError(
            f"El usuario tiene un área no reconocida: '{usuario.area}'.",
            detalles={"areas_validas": [a.value for a in Area]},
        ) from exc
    return CurrentUser(
        username=usuario.nombre_usuario,
        area=area,
        ip=ip,
        usuario_id=usuario.usuario_id,
        email=usuario.email,
    )


class AuthLocal:
    """Login local con usuario/contraseña. Implementa `AuthProviderPort`."""

    nombre = "local"
    soporta_login_local = True

    def autenticar(
        self,
        *,
        identificador: str,
        secreto: str,
        db: Session,
        ip: str | None = None,
    ) -> SesionEmitida:
        """`identificador` es el EMAIL del usuario (decisión H-2: único e indexado)."""
        usuario = UsuarioRepository(db).get_by_email(identificador)

        # Se verifica SIEMPRE, incluso sin usuario: si solo verificáramos cuando existe,
        # el tiempo de respuesta revelaría qué correos están dados de alta.
        password_ok = verificar_password(secreto, usuario.password_hash if usuario else None)

        if usuario is None or not password_ok or not usuario.activo:
            raise AuthenticationError(_CREDENCIALES_INVALIDAS)

        actual = _a_current_user(usuario, ip)
        token, expira = emitir_token(
            usuario_id=usuario.usuario_id,
            nombre_usuario=usuario.nombre_usuario,
            email=usuario.email,
            area=actual.area,
        )
        return SesionEmitida(token=token, expira_en=expira, usuario=actual)

    def resolver_usuario(self, request: Request, db: Session) -> CurrentUser:
        claims = leer_token(_token_del_header(request))

        usuario = UsuarioRepository(db).get(claims.usuario_id)
        if usuario is None or not usuario.activo:
            raise AuthenticationError(_SESION_REVOCADA, detalles={"motivo": "revocado"})

        return _a_current_user(usuario, _ip(request))
