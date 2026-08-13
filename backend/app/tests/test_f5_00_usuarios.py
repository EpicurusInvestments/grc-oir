"""F5-00 — Gestión de usuarios (solo Admin) sobre el usuario autenticado.

Todo se ejercita con **tokens reales** (no headers de desarrollo): es la forma de
comprobar que el RBAC se resuelve del usuario de la base y no de algo que el cliente pueda
elegir. Cubre unicidad de email, política de contraseñas, auditoría de `area`/`activo` en
`LogCambioParametro` y el guardarraíl anti-auto-bloqueo.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config
from app.core.audit import LogCambioParametro
from app.core.auth import passwords
from app.core.auth.passwords import hash_password, verificar_password
from app.core.db import get_db
from app.core.errors import register_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.router import router as usuarios_router

PASSWORD = "Contrasena-Admin-1"
ADMIN_EMAIL = "admin@grcoir.com"


@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "_ROUNDS", 4)
    passwords._hash_senuelo.cache_clear()


@pytest.fixture(autouse=True)
def _proveedor_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "auth_provider", "local")


@pytest.fixture
def client(session_local) -> TestClient:  # type: ignore[no-untyped-def]
    application = FastAPI()
    register_error_handlers(application)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)
    api.include_router(usuarios_router)
    application.include_router(api)

    def override_get_db() -> Iterator[Session]:
        session = session_local()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application)


def _crear_usuario(
    db: Session,
    *,
    email: str,
    area: str,
    password: str | None = PASSWORD,
    nombre: str = "usuario.prueba",
    activo: bool = True,
) -> Usuario:
    usuario = Usuario(
        nombre_usuario=nombre,
        email=email,
        area=area,
        activo=activo,
        password_hash=hash_password(password) if password else None,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _token(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(db_session: Session) -> Usuario:
    return _crear_usuario(db_session, email=ADMIN_EMAIL, area="admin", nombre="ada.admin")


@pytest.fixture
def admin_auth(client: TestClient, admin: Usuario) -> dict[str, str]:
    return _token(client, ADMIN_EMAIL)


# ── RBAC: solo Admin ──────────────────────────────────────────────────────────
def test_area_no_admin_no_puede_ni_listar_usuarios(
    client: TestClient, db_session: Session
) -> None:
    """El padrón de usuarios no es un catálogo: ni siquiera lectura para otras áreas."""
    _crear_usuario(db_session, email="vera@grcoir.com", area="ventas", nombre="vera.ventas")
    auth = _token(client, "vera@grcoir.com")

    listar = client.get("/api/v1/usuarios", headers=auth)
    crear = client.post(
        "/api/v1/usuarios",
        headers=auth,
        json={"nombre_usuario": "x", "email": "x@grcoir.com", "area": "ventas"},
    )

    for r in (listar, crear):
        assert r.status_code == 403
        assert r.json()["error"]["codigo"] == "sin_permiso"


def test_sin_sesion_no_se_llega_a_usuarios(client: TestClient) -> None:
    assert client.get("/api/v1/usuarios").status_code == 401


# ── Alta ──────────────────────────────────────────────────────────────────────
def test_admin_crea_usuario_con_area_y_contrasena(
    client: TestClient, admin_auth: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={
            "nombre_usuario": "  Beto   Cobranza ",
            "email": "  BETO@GRCOIR.com ",
            "area": "cxc",
            "password": "Contrasena-Beto-1",
        },
    )
    assert r.status_code == 201, r.text

    cuerpo = r.json()
    assert cuerpo["nombre_usuario"] == "Beto Cobranza"  # espacios normalizados
    assert cuerpo["email"] == "beto@grcoir.com"  # normalizado a minúsculas
    assert cuerpo["area"] == "cxc"
    assert cuerpo["tiene_password"] is True
    # El hash NUNCA sale en la respuesta.
    assert "password" not in cuerpo and "password_hash" not in r.text


def test_usuario_creado_puede_iniciar_sesion(
    client: TestClient, admin_auth: dict[str, str]
) -> None:
    client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={
            "nombre_usuario": "carla.tesoreria",
            "email": "carla@grcoir.com",
            "area": "tesoreria",
            "password": "Contrasena-Carla-1",
        },
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "carla@grcoir.com", "password": "Contrasena-Carla-1"},
    )
    assert r.status_code == 200
    assert r.json()["usuario"]["area"] == "tesoreria"


def test_alta_sin_contrasena_crea_usuario_que_no_puede_entrar(
    client: TestClient, admin_auth: dict[str, str]
) -> None:
    """Se puede dar de alta primero y establecer la contraseña después (fail-closed)."""
    r = client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={"nombre_usuario": "dani.cxp", "email": "dani@grcoir.com", "area": "cxp"},
    )
    assert r.status_code == 201
    assert r.json()["tiene_password"] is False

    login = client.post(
        "/api/v1/auth/login", json={"email": "dani@grcoir.com", "password": "lo-que-sea"}
    )
    assert login.status_code == 401


def test_email_duplicado_es_409(client: TestClient, admin_auth: dict[str, str]) -> None:
    base = {"nombre_usuario": "eva", "email": "eva@grcoir.com", "area": "ventas"}
    assert client.post("/api/v1/usuarios", headers=admin_auth, json=base).status_code == 201

    # Mismo correo con otra capitalización: sigue siendo el mismo usuario.
    r = client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={**base, "nombre_usuario": "eva.2", "email": "EVA@grcoir.com"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "conflicto"


def test_area_invalida_es_422(client: TestClient, admin_auth: dict[str, str]) -> None:
    r = client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={"nombre_usuario": "f", "email": "f@grcoir.com", "area": "marketing"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "validacion"


# ── Política de contraseñas ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("password", "motivo"),
    [
        ("corta1", "menos de 10 caracteres"),
        ("ñ" * 40, "40 caracteres pero 80 bytes: excede el límite de bcrypt"),
    ],
)
def test_contrasena_invalida_es_422(
    client: TestClient, admin_auth: dict[str, str], password: str, motivo: str
) -> None:
    r = client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={
            "nombre_usuario": "g",
            "email": "g@grcoir.com",
            "area": "ventas",
            "password": password,
        },
    )
    assert r.status_code == 422, motivo


# ── Edición ───────────────────────────────────────────────────────────────────
def test_editar_email_valida_unicidad_pero_permite_conservar_el_propio(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    uno = _crear_usuario(db_session, email="uno@grcoir.com", area="ventas", nombre="uno")
    _crear_usuario(db_session, email="dos@grcoir.com", area="ventas", nombre="dos")

    # Conservar su propio email al editar otro campo: permitido.
    r_ok = client.put(
        f"/api/v1/usuarios/{uno.usuario_id}",
        headers=admin_auth,
        json={"email": "uno@grcoir.com", "nombre_usuario": "uno.editado"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["nombre_usuario"] == "uno.editado"

    # Tomar el de otro: 409.
    r_dup = client.put(
        f"/api/v1/usuarios/{uno.usuario_id}",
        headers=admin_auth,
        json={"email": "dos@grcoir.com"},
    )
    assert r_dup.status_code == 409


def test_usuario_inexistente_es_404(client: TestClient, admin_auth: dict[str, str]) -> None:
    import uuid as _uuid

    r = client.get(f"/api/v1/usuarios/{_uuid.uuid4()}", headers=admin_auth)
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "no_encontrado"


# ── Auditoría de área y activo ────────────────────────────────────────────────
def _bitacora(db: Session, campo: str) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro).where(
        LogCambioParametro.entidad == "Usuario", LogCambioParametro.campo == campo
    )
    return list(db.scalars(stmt).all())


def test_cambio_de_area_queda_en_la_bitacora(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    objetivo = _crear_usuario(db_session, email="hugo@grcoir.com", area="ventas", nombre="hugo")

    r = client.put(
        f"/api/v1/usuarios/{objetivo.usuario_id}", headers=admin_auth, json={"area": "direccion"}
    )
    assert r.status_code == 200
    assert r.json()["area"] == "direccion"

    registros = _bitacora(db_session, "area")
    assert len(registros) == 1
    assert (registros[0].valor_anterior, registros[0].valor_nuevo) == ("ventas", "direccion")
    assert registros[0].entidad_id == str(objetivo.usuario_id)
    assert registros[0].usuario == "ada.admin"  # quién lo hizo


def test_editar_sin_cambiar_area_no_ensucia_la_bitacora(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    objetivo = _crear_usuario(db_session, email="ivan@grcoir.com", area="ventas", nombre="ivan")

    client.put(
        f"/api/v1/usuarios/{objetivo.usuario_id}",
        headers=admin_auth,
        json={"area": "ventas", "nombre_usuario": "ivan.editado"},
    )
    assert _bitacora(db_session, "area") == []


def test_activar_y_desactivar_quedan_en_la_bitacora(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    objetivo = _crear_usuario(db_session, email="jose@grcoir.com", area="cxp", nombre="jose")
    ruta = f"/api/v1/usuarios/{objetivo.usuario_id}/estado"

    assert client.post(ruta, headers=admin_auth, json={"activo": False}).status_code == 200
    assert client.post(ruta, headers=admin_auth, json={"activo": True}).status_code == 200

    registros = _bitacora(db_session, "activo")
    assert len(registros) == 2, "se auditan AMBOS sentidos, no solo la baja"
    assert [(r.valor_anterior, r.valor_nuevo) for r in registros] == [
        ("True", "False"),
        ("False", "True"),
    ]


def test_desactivar_impide_el_login_del_usuario(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    objetivo = _crear_usuario(db_session, email="lia@grcoir.com", area="ventas", nombre="lia")
    assert client.post("/api/v1/auth/login",
                       json={"email": "lia@grcoir.com", "password": PASSWORD}).status_code == 200

    client.post(
        f"/api/v1/usuarios/{objetivo.usuario_id}/estado", headers=admin_auth, json={"activo": False}
    )

    r = client.post("/api/v1/auth/login", json={"email": "lia@grcoir.com", "password": PASSWORD})
    assert r.status_code == 401


# ── Guardarraíl anti-auto-bloqueo ─────────────────────────────────────────────
def test_admin_no_puede_desactivarse_a_si_mismo(
    client: TestClient, admin: Usuario, admin_auth: dict[str, str]
) -> None:
    r = client.post(
        f"/api/v1/usuarios/{admin.usuario_id}/estado", headers=admin_auth, json={"activo": False}
    )
    assert r.status_code == 400
    assert "perderías el acceso" in r.json()["error"]["mensaje"]


def test_admin_no_puede_cambiarse_su_propia_area(
    client: TestClient, admin: Usuario, admin_auth: dict[str, str]
) -> None:
    """Mismo modo de fallo que desactivarse: quedarse sin quien administre el sistema."""
    r = client.put(
        f"/api/v1/usuarios/{admin.usuario_id}", headers=admin_auth, json={"area": "ventas"}
    )
    assert r.status_code == 400


def test_admin_si_puede_desactivar_a_otro_admin(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    otro = _crear_usuario(db_session, email="otro@grcoir.com", area="admin", nombre="otro.admin")

    r = client.post(
        f"/api/v1/usuarios/{otro.usuario_id}/estado", headers=admin_auth, json={"activo": False}
    )
    assert r.status_code == 200


# ── Establecer contraseña ─────────────────────────────────────────────────────
def test_establecer_contrasena_invalida_la_anterior(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    objetivo = _crear_usuario(db_session, email="mara@grcoir.com", area="cxc", nombre="mara")
    nueva = "Contrasena-Nueva-9"

    r = client.post(
        f"/api/v1/usuarios/{objetivo.usuario_id}/password",
        headers=admin_auth,
        json={"password": nueva},
    )
    assert r.status_code == 200
    assert r.json()["tiene_password"] is True
    assert "password_hash" not in r.text

    entra = client.post("/api/v1/auth/login", json={"email": "mara@grcoir.com", "password": nueva})
    assert entra.status_code == 200

    ya_no = client.post(
        "/api/v1/auth/login", json={"email": "mara@grcoir.com", "password": PASSWORD}
    )
    assert ya_no.status_code == 401


def test_establecer_contrasena_a_usuario_sin_contrasena_lo_habilita(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    """El caso del seed `dev.admin` si la migración corrió sin SEED_ADMIN_PASSWORD."""
    objetivo = _crear_usuario(
        db_session, email="nilo@grcoir.com", area="nominas", password=None, nombre="nilo"
    )

    client.post(
        f"/api/v1/usuarios/{objetivo.usuario_id}/password",
        headers=admin_auth,
        json={"password": "Contrasena-Nilo-1"},
    )
    r = client.post(
        "/api/v1/auth/login", json={"email": "nilo@grcoir.com", "password": "Contrasena-Nilo-1"}
    )
    assert r.status_code == 200


def test_el_reseteo_queda_en_el_log_de_seguridad_sin_la_contrasena(
    client: TestClient,
    db_session: Session,
    admin_auth: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Quién reseteó a quién y cuándo. La contraseña y el hash NUNCA se registran."""
    objetivo = _crear_usuario(db_session, email="pepe@grcoir.com", area="cxp", nombre="pepe")
    nueva = "Contrasena-Pepe-42"

    with caplog.at_level(logging.INFO, logger="grcoir.seguridad"):
        r = client.post(
            f"/api/v1/usuarios/{objetivo.usuario_id}/password",
            headers=admin_auth,
            json={"password": nueva},
        )
    assert r.status_code == 200

    eventos = [x for x in caplog.records if x.name == "grcoir.seguridad"]
    assert len(eventos) == 1
    mensaje = eventos[0].getMessage()

    assert "evento_seguridad=password_establecida" in mensaje
    assert "actor=ada.admin" in mensaje  # quién lo hizo
    assert str(objetivo.usuario_id) in mensaje  # a quién
    assert "objetivo=pepe" in mensaje

    # Lo que NO puede aparecer jamás.
    assert nueva not in mensaje
    assert "$2b$" not in mensaje


def test_el_reseteo_no_ensucia_LogCambioParametro(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    """Decisión explícita: el reseteo va al log de seguridad, no a la bitácora de parámetros."""
    objetivo = _crear_usuario(db_session, email="rosa@grcoir.com", area="cxc", nombre="rosa")

    client.post(
        f"/api/v1/usuarios/{objetivo.usuario_id}/password",
        headers=admin_auth,
        json={"password": "Contrasena-Rosa-1"},
    )

    stmt = select(LogCambioParametro).where(LogCambioParametro.entidad == "Usuario")
    assert list(db_session.scalars(stmt).all()) == []


def test_la_contrasena_se_guarda_hasheada_nunca_en_claro(
    client: TestClient, db_session: Session, admin_auth: dict[str, str]
) -> None:
    en_claro = "Contrasena-Secreta-7"
    client.post(
        "/api/v1/usuarios",
        headers=admin_auth,
        json={
            "nombre_usuario": "olga",
            "email": "olga@grcoir.com",
            "area": "facturacion",
            "password": en_claro,
        },
    )

    guardado = db_session.scalars(
        select(Usuario).where(Usuario.email == "olga@grcoir.com")
    ).one()
    assert guardado.password_hash is not None
    assert en_claro not in guardado.password_hash
    assert guardado.password_hash.startswith("$2b$")
    assert verificar_password(en_claro, guardado.password_hash) is True
