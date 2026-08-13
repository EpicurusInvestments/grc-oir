"""Selección del proveedor de autenticación por configuración (ADR-028).

`get_auth_provider()` es el ÚNICO punto donde se decide qué proveedor se usa, según
`AUTH_PROVIDER`. Es el espejo exacto de `get_almacenamiento()` (ADR-027): el resto del
sistema depende solo de `AuthProviderPort`, nunca de un adaptador concreto.

- `local`       → `AuthLocal`. **Default**: las demos siempre pasan por login real.
- `dev_headers` → `AuthDevHeaders`. Modo desarrollo (ADR-008); el propio adaptador falla
                  cerrado con 401 fuera de `APP_ENV=development`.
- `azure_ad`    → `AuthAzureAD`. Interfaz preparada, implementación diferida: falla con un
                  error de configuración claro.

Un valor desconocido falla ruidosamente; nunca se cae en silencio a otro proveedor.

Los adaptadores se importan DIFERIDO (dentro de la función), igual que `adapter_s3`: así
`core.security` puede importar este módulo sin arrastrar `app.modules.usuarios` en la
carga inicial, y sin ciclos de importación.
"""

from __future__ import annotations

from app.core.auth.identity import Area, CurrentUser
from app.core.auth.port import AuthProviderPort, SesionEmitida
from app.core.config import settings
from app.core.errors import ConfiguracionError


def get_auth_provider() -> AuthProviderPort:
    """Devuelve el proveedor de autenticación configurado."""
    proveedor = settings.auth_provider.strip().lower()

    if proveedor == "local":
        from app.core.auth.adapter_local import AuthLocal

        return AuthLocal()

    if proveedor == "dev_headers":
        # Nota: la restricción a `development` la aplica el propio adaptador al resolver
        # el usuario (401 `no_autenticado`), no este factory. Así se preserva literal el
        # comportamiento fail-closed de ADR-008 que las pruebas de F0 verifican.
        from app.core.auth.adapter_dev_headers import AuthDevHeaders

        return AuthDevHeaders()

    if proveedor == "azure_ad":
        from app.core.auth.adapter_azure_ad import AuthAzureAD

        return AuthAzureAD()

    raise ConfiguracionError(
        f"AUTH_PROVIDER desconocido: '{settings.auth_provider}' "
        "(use 'local', 'dev_headers' o 'azure_ad').",
    )


__all__ = [
    "Area",
    "AuthProviderPort",
    "CurrentUser",
    "SesionEmitida",
    "get_auth_provider",
]
