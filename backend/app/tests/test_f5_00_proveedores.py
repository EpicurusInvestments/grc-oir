"""F5-00 — Selección del proveedor de autenticación (`get_auth_provider`).

Un solo punto de decisión, como `get_almacenamiento()` de S3: se verifica que elige bien,
que falla ruidosamente ante configuraciones inválidas y —lo importante— que el modo de
desarrollo por headers sigue siendo fail-closed fuera de `development` (ADR-008).
"""

from __future__ import annotations

import pytest
from fastapi import Request

from app.core import config
from app.core.auth import get_auth_provider
from app.core.auth.adapter_dev_headers import AuthDevHeaders
from app.core.auth.adapter_local import AuthLocal
from app.core.errors import AuthenticationError, ConfiguracionError


def _request(headers: dict[str, str] | None = None) -> Request:
    """Request mínimo (scope ASGI) para probar un adaptador sin levantar la app."""
    crudos = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": crudos})


def test_default_es_login_real(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """El default del sistema es `local`: las demos siempre pasan por la pantalla de login."""
    assert config.Settings.model_fields["auth_provider"].default == "local"


def test_selecciona_local(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "auth_provider", "local")
    proveedor = get_auth_provider()
    assert isinstance(proveedor, AuthLocal)
    assert proveedor.soporta_login_local is True


def test_selecciona_dev_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "auth_provider", "DEV_HEADERS  ")  # se normaliza
    proveedor = get_auth_provider()
    assert isinstance(proveedor, AuthDevHeaders)
    assert proveedor.soporta_login_local is False


def test_dev_headers_falla_cerrado_fuera_de_development(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Regresión de ADR-008: nunca asume admin en qa/producción, y responde 401 (no 500)."""
    monkeypatch.setattr(config.settings, "auth_provider", "dev_headers")
    monkeypatch.setattr(config.settings, "app_env", "production")

    with pytest.raises(AuthenticationError):
        get_auth_provider().resolver_usuario(
            _request({"X-Dev-Area": "admin"}), db=None  # type: ignore[arg-type]
        )


def test_dev_headers_resuelve_el_area_del_header_en_development(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "auth_provider", "dev_headers")

    usuario = get_auth_provider().resolver_usuario(
        _request({"X-Dev-User": "pablo", "X-Dev-Area": "cxp"}), db=None  # type: ignore[arg-type]
    )
    assert (usuario.username, usuario.area.value) == ("pablo", "cxp")
    # Sin tabla detrás: en este modo no hay `usuario_id` (ver adapter_dev_headers).
    assert usuario.usuario_id is None


def test_dev_headers_no_ofrece_login(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "auth_provider", "dev_headers")

    with pytest.raises(ConfiguracionError):
        get_auth_provider().autenticar(identificador="x", secreto="y", db=None)  # type: ignore[arg-type]


def test_azure_ad_falla_con_mensaje_claro(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """El hueco está preparado, pero pedirlo NO cae en silencio a otro proveedor."""
    monkeypatch.setattr(config.settings, "auth_provider", "azure_ad")

    with pytest.raises(ConfiguracionError) as exc:
        get_auth_provider()
    assert "azure_ad" in str(exc.value)


def test_proveedor_desconocido_falla(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "auth_provider", "inventado")

    with pytest.raises(ConfiguracionError) as exc:
        get_auth_provider()
    assert "inventado" in str(exc.value)
