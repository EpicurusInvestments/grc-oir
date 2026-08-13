"""Adaptador de DESARROLLO: identidad por headers `X-Dev-User` / `X-Dev-Area`.

Conserva **exactamente** el comportamiento de ADR-008 (F0-00), que antes vivía dentro de
`core/security.get_current_user`: sirve para que el equipo pruebe cualquier área en local
sin loguearse en cada arranque, y para que el trabajo en curso de F1 no se frene mientras
se integra el login real.

Reglas que se mantienen tal cual:

- **Fail-closed**: fuera de `APP_ENV=development` rechaza con 401 (nunca asume admin). La
  comprobación vive AQUÍ, y no en el factory, para que el error siga siendo 401
  `no_autenticado` — que es lo que la matriz de pruebas de F0 verifica.
- No consulta la tabla `usuario`: el header puede nombrar a alguien que no está dado de
  alta. Por eso `CurrentUser.usuario_id` queda en `None` en este modo.

NO es el proveedor por defecto: `AUTH_PROVIDER=local` lo es, para que las demos al cliente
siempre pasen por la pantalla de login. Cada quien pone `AUTH_PROVIDER=dev_headers` en su
`.env` local si lo quiere.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth.identity import Area, CurrentUser
from app.core.auth.port import SesionEmitida
from app.core.config import settings
from app.core.errors import AuthenticationError, ConfiguracionError


class AuthDevHeaders:
    """Identidad por headers de desarrollo. Implementa `AuthProviderPort`."""

    nombre = "dev_headers"
    soporta_login_local = False

    def autenticar(
        self,
        *,
        identificador: str,
        secreto: str,
        db: Session,
        ip: str | None = None,
    ) -> SesionEmitida:
        raise ConfiguracionError(
            "El proveedor 'dev_headers' no ofrece login: la identidad se toma de los "
            "headers X-Dev-User / X-Dev-Area. Use AUTH_PROVIDER=local para iniciar sesión."
        )

    def resolver_usuario(self, request: Request, db: Session) -> CurrentUser:
        # Lo PRIMERO, antes de mirar nada del request: si no estamos en desarrollo, este
        # proveedor no atiende a nadie.
        if not settings.is_development:
            raise AuthenticationError(
                "Autenticación no configurada: el acceso de desarrollo por headers solo "
                "se permite con APP_ENV=development."
            )

        ip = request.client.host if request.client else None
        username = request.headers.get("X-Dev-User", settings.dev_user)
        area_raw = request.headers.get("X-Dev-Area", settings.dev_area)
        try:
            area = Area(area_raw.strip().lower())
        except ValueError as exc:
            raise AuthenticationError(
                f"Área de desarrollo inválida: '{area_raw}'.",
                detalles={"areas_validas": [a.value for a in Area]},
            ) from exc
        return CurrentUser(username=username, area=area, ip=ip)
