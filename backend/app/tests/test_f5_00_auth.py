"""F5-00 — Login local, token de sesión y RBAC sobre el usuario autenticado.

Se ejercita el proveedor `local` de punta a punta con SQLite en memoria (sin RDS ni red):
login correcto y fallido, expiración/alteración del token, acceso sin sesión y el RBAC por
área resuelto desde el usuario autenticado en vez de un header.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import config
from app.core.auth import passwords
from app.core.auth.identity import Area
from app.core.auth.passwords import hash_password, verificar_password
from app.core.auth.tokens import emitir_token
from app.core.db import get_db
from app.core.errors import ConfiguracionError, register_error_handlers
from app.core.security import CurrentUser, requiere_permiso
from app.modules.auth.router import router as auth_router
from app.modules.usuarios.models import Usuario

PASSWORD = "Contrasena-Temporal-1"
EMAIL = "ana.lopez@grcoir.com"


@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch):  # type: ignore[no-untyped-def]
    """bcrypt con costo mínimo en pruebas: 12 rondas × N pruebas es lento sin aportar nada."""
    monkeypatch.setattr(passwords, "_ROUNDS", 4)
    passwords._hash_senuelo.cache_clear()


@pytest.fixture(autouse=True)
def _proveedor_local(monkeypatch):  # type: ignore[no-untyped-def]
    """Este módulo prueba el proveedor `local` (el conftest global fija `dev_headers`)."""
    monkeypatch.setattr(config.settings, "auth_provider", "local")


@pytest.fixture
def auth_client(session_local) -> TestClient:  # type: ignore[no-untyped-def]
    """App mínima con el router de auth + un endpoint protegido por RBAC."""
    application = FastAPI()
    register_error_handlers(application)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)

    @api.get("/protegido")
    def protegido(
        usuario: CurrentUser = Depends(requiere_permiso("catalogos:editar")),
    ) -> dict[str, str]:
        return {"area": usuario.area.value, "usuario": usuario.username}

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
    email: str = EMAIL,
    password: str | None = PASSWORD,
    area: str = "admin",
    activo: bool = True,
    nombre: str = "ana.lopez",
) -> Usuario:
    usuario = Usuario(
        nombre_usuario=nombre,
        email=email,
        area=area,
        activo=activo,
        password_hash=hash_password(password) if password is not None else None,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def _login(client: TestClient, *, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Login ─────────────────────────────────────────────────────────────────────
def test_login_correcto_emite_token_con_identidad_y_area(
    auth_client: TestClient, db_session: Session
) -> None:
    usuario = _crear_usuario(db_session)

    r = _login(auth_client)
    assert r.status_code == 200

    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["usuario"]["area"] == "admin"
    assert cuerpo["usuario"]["nombre_usuario"] == "ana.lopez"
    assert uuid.UUID(cuerpo["usuario"]["usuario_id"]) == usuario.usuario_id
    # El hash JAMÁS viaja al cliente.
    assert "password_hash" not in r.text

    claims = jwt.decode(
        cuerpo["access_token"],
        config.settings.secret_key,
        algorithms=[config.settings.jwt_algoritmo],
        issuer=config.settings.jwt_issuer,
    )
    assert claims["sub"] == str(usuario.usuario_id)
    assert claims["area"] == "admin"
    assert claims["exp"] - claims["iat"] == config.settings.jwt_expira_horas * 3600


def test_login_email_es_case_insensitive(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session)
    assert _login(auth_client, email="Ana.Lopez@GRCOIR.com").status_code == 200


def test_password_incorrecta_y_usuario_inexistente_dan_la_MISMA_respuesta(
    auth_client: TestClient, db_session: Session
) -> None:
    """El mensaje no debe permitir deducir si un correo está dado de alta."""
    _crear_usuario(db_session)

    mala_password = _login(auth_client, password="otra-cosa")
    sin_usuario = _login(auth_client, email="nadie@grcoir.com", password=PASSWORD)

    assert mala_password.status_code == sin_usuario.status_code == 401
    assert mala_password.json() == sin_usuario.json()
    assert mala_password.json()["error"]["codigo"] == "no_autenticado"


def test_usuario_inactivo_no_puede_entrar(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session, activo=False)

    r = _login(auth_client)
    assert r.status_code == 401
    # Mismo mensaje genérico: tampoco revelamos que la cuenta existe pero está dada de baja.
    assert r.json()["error"]["mensaje"] == "Usuario o contraseña incorrectos."


def test_usuario_sin_password_hash_no_puede_entrar(
    auth_client: TestClient, db_session: Session
) -> None:
    """Caso del seed antes de correr la migración con SEED_ADMIN_PASSWORD."""
    _crear_usuario(db_session, password=None)

    r = _login(auth_client, password="lo-que-sea")
    assert r.status_code == 401
    assert r.json()["error"]["mensaje"] == "Usuario o contraseña incorrectos."


# ── Sesión ────────────────────────────────────────────────────────────────────
def test_me_devuelve_la_identidad_del_token(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session, area="tesoreria")
    token = _login(auth_client).json()["access_token"]

    r = auth_client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {
        "usuario_id": r.json()["usuario_id"],
        "nombre_usuario": "ana.lopez",
        "email": EMAIL,
        "area": "tesoreria",
    }


def test_sin_header_authorization_es_401(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session)
    for ruta in ("/api/v1/auth/me", "/api/v1/protegido"):
        r = auth_client.get(ruta)
        assert r.status_code == 401, ruta
        assert r.json()["error"]["codigo"] == "no_autenticado"


def test_token_expirado_es_401_con_motivo(
    auth_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear_usuario(db_session)
    # Emitir el token ya vencido es más fiable que esperar 8 horas.
    monkeypatch.setattr(config.settings, "jwt_expira_horas", -1)
    token = _login(auth_client).json()["access_token"]
    monkeypatch.setattr(config.settings, "jwt_expira_horas", 8)

    r = auth_client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 401
    assert r.json()["error"]["detalles"]["motivo"] == "expirado"


def test_token_alterado_es_401(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session)
    token = _login(auth_client).json()["access_token"]
    alterado = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")

    r = auth_client.get("/api/v1/auth/me", headers=_auth(alterado))
    assert r.status_code == 401
    assert r.json()["error"]["detalles"]["motivo"] == "invalido"


def test_token_de_otro_emisor_es_401(
    auth_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    usuario = _crear_usuario(db_session)
    monkeypatch.setattr(config.settings, "jwt_issuer", "otro-sistema")
    token, _ = emitir_token(
        usuario_id=usuario.usuario_id,
        nombre_usuario=usuario.nombre_usuario,
        email=usuario.email,
        area=Area.ADMIN,
    )
    monkeypatch.setattr(config.settings, "jwt_issuer", "grc-oir")

    r = auth_client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 401


def test_desactivar_al_usuario_invalida_su_sesion_en_curso(
    auth_client: TestClient, db_session: Session
) -> None:
    """El estado se relee de la BD: no hay que esperar a que expire el token."""
    usuario = _crear_usuario(db_session)
    token = _login(auth_client).json()["access_token"]
    assert auth_client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 200

    usuario.activo = False
    db_session.commit()

    r = auth_client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 401
    assert r.json()["error"]["detalles"]["motivo"] == "revocado"


def test_logout_responde_204(auth_client: TestClient) -> None:
    assert auth_client.post("/api/v1/auth/logout").status_code == 204


# ── RBAC resuelto desde el usuario autenticado ────────────────────────────────
def test_rbac_admin_escribe_con_su_token(auth_client: TestClient, db_session: Session) -> None:
    _crear_usuario(db_session, area="admin")
    token = _login(auth_client).json()["access_token"]

    r = auth_client.get("/api/v1/protegido", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"area": "admin", "usuario": "ana.lopez"}


def test_rbac_ventas_no_escribe_aunque_tenga_sesion_valida(
    auth_client: TestClient, db_session: Session
) -> None:
    _crear_usuario(db_session, area="ventas")
    token = _login(auth_client).json()["access_token"]

    r = auth_client.get("/api/v1/protegido", headers=_auth(token))
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"


def test_el_area_del_header_dev_se_ignora_con_el_proveedor_local(
    auth_client: TestClient, db_session: Session
) -> None:
    """Regresión: el cliente NO puede elegir su área una vez que hay login real."""
    _crear_usuario(db_session, area="ventas")
    token = _login(auth_client).json()["access_token"]

    r = auth_client.get(
        "/api/v1/protegido",
        headers={**_auth(token), "X-Dev-Area": "admin", "X-Dev-User": "impostor"},
    )
    assert r.status_code == 403


# ── Documentación del esquema de seguridad (botón "Authorize" de /docs) ───────
def test_openapi_publica_el_esquema_bearer(auth_client: TestClient) -> None:
    """Sin esto, /docs no ofrece dónde pegar el token y los endpoints se ven vacíos."""
    esquema = auth_client.app.openapi()  # type: ignore[attr-defined]

    assert esquema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    # Los endpoints protegidos lo declaran...
    assert esquema["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert esquema["paths"]["/api/v1/protegido"]["get"]["security"] == [{"HTTPBearer": []}]
    # ...y el login NO: es público, es justo lo que entrega el token.
    assert "security" not in esquema["paths"]["/api/v1/auth/login"]["post"]


# ── Hash de contraseñas: el límite de 72 bytes de bcrypt ──────────────────────
def test_password_mas_larga_que_72_bytes_no_revienta() -> None:
    """bcrypt 5.x LANZA ValueError si la contraseña excede 72 bytes.

    `passwords._a_bytes` trunca antes de llamarlo: sin eso, una contraseña larga sería un
    500 en producción en vez de un login normal.
    """
    larga = "A" * 100
    assert verificar_password(larga, hash_password(larga)) is True


def test_el_limite_se_cuenta_en_BYTES_no_en_caracteres() -> None:
    """En UTF-8 'ñ' ocupa 2 bytes: 40 caracteres ya son 80 bytes y superan el límite."""
    con_acentos = "ñ" * 40
    assert len(con_acentos) == 40 < 72 < len(con_acentos.encode("utf-8")) == 80
    assert verificar_password(con_acentos, hash_password(con_acentos)) is True


def test_el_truncado_a_72_bytes_queda_fijado_no_es_una_sorpresa() -> None:
    """Consecuencia ACEPTADA del límite: los bytes 73+ no participan en el hash.

    Se fija aquí para que nadie lo descubra por accidente: dos contraseñas que comparten
    los primeros 72 bytes son la MISMA para efectos de login. Por eso el schema que
    ESTABLECE contraseña (gestión de usuarios) las rechaza con un mensaje claro en vez de
    aceptarlas y recortarlas en silencio.
    """
    base = "P" * 72
    hash_base = hash_password(base)

    assert verificar_password(base + "-sufijo-que-se-ignora", hash_base) is True
    # Diferir dentro de los primeros 72 bytes sí cambia el resultado.
    assert verificar_password("Q" + base[1:], hash_base) is False


def test_sin_hash_almacenado_nunca_autentica() -> None:
    """Usuario de Azure AD o seed sin contraseña: `None` no es una credencial válida."""
    assert verificar_password("lo-que-sea", None) is False
    assert verificar_password("lo-que-sea", "") is False


def test_hash_corrupto_no_revienta_devuelve_False() -> None:
    assert verificar_password("lo-que-sea", "esto-no-es-un-hash-bcrypt") is False


# ── Guardarraíl de la llave de firma ──────────────────────────────────────────
def test_secret_key_de_ejemplo_no_firma_fuera_de_development(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "secret_key", config.SECRET_KEY_INSEGURA)
    monkeypatch.setattr(config.settings, "app_env", "production")

    with pytest.raises(ConfiguracionError):
        emitir_token(
            usuario_id=uuid.uuid4(),
            nombre_usuario="x",
            email="x@grcoir.com",
            area=Area.ADMIN,
        )
