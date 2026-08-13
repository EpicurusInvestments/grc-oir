"""Capa de negocio de la autenticación (F5-00).

Delgada a propósito: la mecánica de credenciales y tokens vive en el adaptador
(`core/auth/adapter_*`), porque es lo que cambia al cambiar de proveedor. Lo que se queda
aquí es la regla de negocio que NO depende del proveedor: si el proveedor configurado no
ofrece login local, `/auth/login` es un error de configuración del servidor, no un intento
fallido del usuario.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth.identity import CurrentUser
from app.core.auth.port import AuthProviderPort
from app.core.errors import ConfiguracionError
from app.modules.auth.schemas import LoginIn, SesionOut, UsuarioSesion


def _a_usuario_sesion(usuario: CurrentUser) -> UsuarioSesion:
    return UsuarioSesion(
        usuario_id=usuario.usuario_id,
        nombre_usuario=usuario.username,
        email=usuario.email,
        area=usuario.area.value,
    )


class AuthService:
    def __init__(self, proveedor: AuthProviderPort, db: Session) -> None:
        self._proveedor = proveedor
        self._db = db

    def login(self, datos: LoginIn, ip: str | None) -> SesionOut:
        if not self._proveedor.soporta_login_local:
            raise ConfiguracionError(
                f"El proveedor de autenticación configurado ('{self._proveedor.nombre}') "
                "no ofrece login con usuario y contraseña.",
            )

        sesion = self._proveedor.autenticar(
            identificador=datos.email,
            secreto=datos.password,
            db=self._db,
            ip=ip,
        )
        return SesionOut(
            access_token=sesion.token,
            expira_en=sesion.expira_en,
            usuario=_a_usuario_sesion(sesion.usuario),
        )

    @staticmethod
    def sesion_actual(usuario: CurrentUser) -> UsuarioSesion:
        return _a_usuario_sesion(usuario)
