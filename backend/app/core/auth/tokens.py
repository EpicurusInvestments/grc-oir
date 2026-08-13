"""Emisión y verificación del token de sesión (JWT).

ÚNICO lugar del sistema que conoce JWT. Firma **HS256** con `SECRET_KEY` (que ya existía
en `.env.example` documentada justo para esto) y expiración configurable
(`JWT_EXPIRA_HORAS`, por defecto 8 h = una jornada laboral).

Guardarraíl: fuera de `APP_ENV=development` se rechaza firmar o validar con la
`SECRET_KEY` de ejemplo del repositorio. Un token firmado con una llave pública no es
autenticación, es decoración.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.auth.identity import Area
from app.core.config import SECRET_KEY_INSEGURA, settings
from app.core.errors import AuthenticationError, ConfiguracionError

# Mensaje ÚNICO para todo token inválido (expirado, alterado, de otro emisor, ilegible):
# el cliente solo necesita saber que debe volver a iniciar sesión. El motivo va en
# `detalles` para que el frontend distinga "expiró" de "nunca hubo sesión".
_SESION_INVALIDA = "Sesión inválida o expirada. Vuelve a iniciar sesión."


@dataclass(frozen=True)
class ClaimsSesion:
    """Contenido útil de un token ya validado."""

    usuario_id: uuid.UUID
    nombre_usuario: str
    email: str
    area: Area


def _secreto() -> str:
    """Llave de firma, validada. Solo del entorno; nunca del código."""
    secreto = settings.secret_key
    if not secreto or (secreto == SECRET_KEY_INSEGURA and not settings.is_development):
        raise ConfiguracionError(
            "SECRET_KEY no configurada: fuera de desarrollo no se pueden firmar ni "
            "validar sesiones con la llave de ejemplo del repositorio. Defina SECRET_KEY "
            "en el entorno (o en AWS Secrets Manager en qa/producción)."
        )
    return secreto


def emitir_token(
    *,
    usuario_id: uuid.UUID,
    nombre_usuario: str,
    email: str,
    area: Area,
) -> tuple[str, datetime]:
    """Emite el token de sesión. Devuelve `(token, momento de expiración)`."""
    emitido = datetime.now(UTC)
    expira = emitido + timedelta(hours=settings.jwt_expira_horas)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(usuario_id),
        "nombre_usuario": nombre_usuario,
        "email": email,
        "area": area.value,
        "iat": emitido,
        "exp": expira,
    }
    return jwt.encode(payload, _secreto(), algorithm=settings.jwt_algoritmo), expira


def leer_token(token: str) -> ClaimsSesion:
    """Valida firma, expiración y emisor; devuelve los claims. 401 si algo falla.

    OJO: esto valida el TOKEN, no al usuario. Quien llame debe releer el registro
    `usuario` para conocer su estado actual (`activo`, `area`) — ver `adapter_local`.
    """
    try:
        payload = jwt.decode(
            token,
            _secreto(),
            algorithms=[settings.jwt_algoritmo],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(_SESION_INVALIDA, detalles={"motivo": "expirado"}) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(_SESION_INVALIDA, detalles={"motivo": "invalido"}) from exc

    try:
        return ClaimsSesion(
            usuario_id=uuid.UUID(str(payload["sub"])),
            nombre_usuario=str(payload.get("nombre_usuario", "")),
            email=str(payload.get("email", "")),
            area=Area(str(payload["area"])),
        )
    except (KeyError, ValueError) as exc:
        # Token bien firmado pero con claims que no entendemos (versión vieja, área
        # eliminada del ENUM...): se trata como sesión inválida, no como error 500.
        raise AuthenticationError(_SESION_INVALIDA, detalles={"motivo": "invalido"}) from exc
