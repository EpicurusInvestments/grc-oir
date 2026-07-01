"""RBAC y costura de autenticación, vía el router CRUD genérico montado en la app de test.

- Admin escribe; áreas operativas solo leen (matriz de catálogos).
- La auth de desarrollo solo aplica con APP_ENV=development; en otro entorno sin SSO la
  autenticación falla cerrada (nunca asume admin).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import config


def _hdr(area: str, user: str = "tester") -> dict[str, str]:
    return {"X-Dev-User": user, "X-Dev-Area": area}


def test_admin_puede_crear(client: TestClient) -> None:
    r = client.post("/api/v1/demo", json={"nombre": "Nuevo"}, headers=_hdr("admin"))
    assert r.status_code == 201
    assert r.json()["nombre"] == "Nuevo"


def test_ventas_puede_leer_pero_no_crear(client: TestClient) -> None:
    # lectura permitida
    r_list = client.get("/api/v1/demo", headers=_hdr("ventas"))
    assert r_list.status_code == 200

    # escritura denegada (403, sobre uniforme)
    r_post = client.post("/api/v1/demo", json={"nombre": "X"}, headers=_hdr("ventas"))
    assert r_post.status_code == 403
    assert r_post.json()["error"]["codigo"] == "sin_permiso"


def test_area_invalida_rechazada(client: TestClient) -> None:
    r = client.get("/api/v1/demo", headers=_hdr("inexistente"))
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


def test_falla_cerrada_fuera_de_development(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Sin SSO y APP_ENV != development → rechazar, nunca asumir admin.
    # `settings` es un único objeto compartido; security.py referencia el mismo.
    monkeypatch.setattr(config.settings, "app_env", "production")

    r = client.get("/api/v1/demo", headers=_hdr("admin"))
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"
