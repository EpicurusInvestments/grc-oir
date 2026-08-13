"""Adaptador Azure AD — INTERFAZ PREPARADA, IMPLEMENTACIÓN DIFERIDA.

F5-00 deja el hueco; la conexión OAuth 2.0 / OpenID Connect real llega cuando IT de GRC
registre la aplicación en Azure y confirme el SSO (`[[POR LLENAR]]` en CLAUDE.md §14).
Este archivo existe para que el hueco sea EXPLÍCITO y con forma, no un TODO suelto: quien
lo implemente ya sabe qué métodos debe cumplir y qué configuración va a necesitar.

Lo que falta cuando se retome (# TODO(SSO)):

1. Configuración: `SSO_TENANT_ID`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET` (ya declaradas en
   `.env.example` como `[[POR LLENAR]]`) + la URL de descubrimiento OIDC del tenant.
2. `resolver_usuario`: validar el JWT emitido por Azure contra las **JWKS públicas** del
   tenant (firma RS256, `iss`, `aud`, `exp`) — NO con `SECRET_KEY`, que es nuestra.
3. Mapeo identidad → dominio: del claim de Azure (`preferred_username` / `oid`) al
   registro `usuario`, y del grupo/rol de Azure al ENUM `Area`. Un usuario de Azure sin
   registro local debería rechazarse (o darse de alta con un área explícita), nunca
   asumir un área por omisión.
4. El cliente HTTP hacia Azure irá en `app/integrations/azure_ad/` (capa de integración);
   este adaptador solo lo consumirá, para no meter detalles de OIDC en `core/`.
5. `autenticar` probablemente quede sin uso: en OIDC el login ocurre en Azure y el
   frontend vuelve con un código/token, así que hará falta un endpoint de *callback* en
   lugar de un POST con contraseña.

Mientras tanto, pedir `AUTH_PROVIDER=azure_ad` falla de forma RUIDOSA y clara al construir
el proveedor (no en silencio, y sin caer de vuelta a `local`).
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth.identity import CurrentUser
from app.core.auth.port import SesionEmitida
from app.core.errors import ConfiguracionError

_NO_IMPLEMENTADO = (
    "AUTH_PROVIDER=azure_ad todavía no está implementado: F5-00 dejó preparada la "
    "interfaz del adaptador, pero la conexión OAuth/OIDC real está diferida hasta que se "
    "configure el registro de la aplicación en Azure. Use AUTH_PROVIDER=local "
    "(o dev_headers en desarrollo)."
)


class AuthAzureAD:
    """Adaptador Azure AD. Cumple `AuthProviderPort`; todavía no funciona."""

    nombre = "azure_ad"
    soporta_login_local = False

    def __init__(self) -> None:
        # Falla al CONSTRUIRSE, no al primer request: si alguien despliega con esta
        # variable, se entera de inmediato y no cuando un usuario intente entrar.
        raise ConfiguracionError(_NO_IMPLEMENTADO)

    def autenticar(  # pragma: no cover — inalcanzable mientras __init__ falle
        self,
        *,
        identificador: str,
        secreto: str,
        db: Session,
        ip: str | None = None,
    ) -> SesionEmitida:
        raise ConfiguracionError(_NO_IMPLEMENTADO)  # TODO(SSO)

    def resolver_usuario(  # pragma: no cover — inalcanzable mientras __init__ falle
        self, request: Request, db: Session
    ) -> CurrentUser:
        raise ConfiguracionError(_NO_IMPLEMENTADO)  # TODO(SSO)
