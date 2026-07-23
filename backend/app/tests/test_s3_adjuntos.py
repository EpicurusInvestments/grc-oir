"""Pruebas de la integración de adjuntos de contrato (almacenamiento local + S3 + endpoints).

Se prueba SIN credenciales ni red:
- `documentos`: saneo de nombre (traversal, fuerza .pdf, vacío) y validación PDF/tamaño.
- Adaptador LOCAL (filesystem en `tmp_path`): round-trip subir→listar→obtener→borrar.
- Adaptador S3: con un cliente boto3 FALSO en memoria (put/list/get/delete) + mapeo de
  errores de S3 a `AlmacenamientoError`.
- Endpoints del contrato: RBAC (lectura vs escritura), validación (no-PDF 400, exceso 413),
  round-trip HTTP y saneo de traversal — usando el adaptador local por override.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import date, datetime

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.core.security import Area, CurrentUser
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.adapter_s3 import AlmacenamientoS3
from app.integrations.almacenamiento.documentos import (
    AlmacenamientoError,
    ArchivoNoPdfError,
    DocumentoAlmacenado,
    sanear_nombre_archivo,
)
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import (
    Anunciante,
    AnuncianteCreate,
    AnuncianteRepository,
    AnuncianteService,
    Marca,
    MarcaRepository,
)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.contrato import (
    Contrato,
    ContratoCreate,
    ContratoRepository,
    ContratoService,
    get_contrato_service,
)
from app.modules.catalogos.contrato import (
    router as contrato_router,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")


# ══════════════════════════════════════════════════════════════════════════════════
# documentos: saneo de nombre + validación
# ══════════════════════════════════════════════════════════════════════════════════
def test_sanear_bloquea_traversal() -> None:
    assert sanear_nombre_archivo("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanear_nombre_archivo("carpeta/sub/contrato.pdf") == "contrato.pdf"
    assert sanear_nombre_archivo("C:\\temp\\x.pdf") == "x.pdf"


def test_sanear_fuerza_pdf_y_charset() -> None:
    assert sanear_nombre_archivo("mi contrato firmado.pdf") == "mi-contrato-firmado.pdf"
    assert sanear_nombre_archivo("acta 2026 #1.PDF") == "acta-2026-1.pdf"
    # sin extensión reconocible → se le agrega .pdf
    assert sanear_nombre_archivo("documento").endswith(".pdf")


def test_sanear_nombre_vacio_rechazado() -> None:
    with pytest.raises(ArchivoNoPdfError):
        sanear_nombre_archivo("../../")


# ══════════════════════════════════════════════════════════════════════════════════
# Adaptador local (filesystem)
# ══════════════════════════════════════════════════════════════════════════════════
def test_local_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    alm = AlmacenamientoLocal(tmp_path)
    prefijo = alm.prefijo_contrato("C-2026-001")
    assert prefijo == "contratos/C-2026-001/"

    clave = alm.subir(prefijo=prefijo, nombre_archivo="acta.pdf", contenido=PDF_BYTES)
    assert clave == "contratos/C-2026-001/acta.pdf"

    docs = alm.listar(prefijo)
    assert [d.nombre for d in docs] == ["acta.pdf"]
    assert docs[0].tamano_bytes == len(PDF_BYTES)

    assert alm.obtener(clave) == PDF_BYTES

    alm.borrar(clave)
    assert alm.listar(prefijo) == []
    # borrar es idempotente
    alm.borrar(clave)


def test_local_listar_prefijo_inexistente(tmp_path) -> None:  # type: ignore[no-untyped-def]
    alm = AlmacenamientoLocal(tmp_path)
    assert alm.listar("contratos/nada/") == []


def test_local_obtener_inexistente(tmp_path) -> None:  # type: ignore[no-untyped-def]
    alm = AlmacenamientoLocal(tmp_path)
    with pytest.raises(AlmacenamientoError):
        alm.obtener("contratos/x/no-existe.pdf")


# ══════════════════════════════════════════════════════════════════════════════════
# Adaptador S3 con cliente boto3 FALSO (sin red ni credenciales)
# ══════════════════════════════════════════════════════════════════════════════════
class _FakePaginator:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store

    def paginate(self, *, Bucket: str, Prefix: str):  # type: ignore[no-untyped-def]  # noqa: N803
        contents = [
            {"Key": k, "Size": len(v), "LastModified": datetime(2026, 7, 23, 12, 0, 0)}
            for k, v in self._store.items()
            if k.startswith(Prefix)
        ]
        yield {"Contents": contents}


class FakeS3Client:
    """Cliente S3 en memoria que imita la parte de boto3 que usa el adaptador."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType=None):  # type: ignore[no-untyped-def]  # noqa: N803
        self.store[Key] = Body

    def get_object(self, *, Bucket, Key):  # type: ignore[no-untyped-def]  # noqa: N803
        return {"Body": io.BytesIO(self.store[Key])}

    def delete_object(self, *, Bucket, Key):  # type: ignore[no-untyped-def]  # noqa: N803
        self.store.pop(Key, None)

    def get_paginator(self, nombre):  # type: ignore[no-untyped-def]
        return _FakePaginator(self.store)


class BrokenS3Client:
    """Cliente que falla en todo, para probar el mapeo a AlmacenamientoError."""

    def _boom(self, *a, **k):  # type: ignore[no-untyped-def]
        raise RuntimeError("s3 caído")

    put_object = get_object = delete_object = get_paginator = _boom


def _s3(client) -> AlmacenamientoS3:  # type: ignore[no-untyped-def]
    return AlmacenamientoS3(bucket="s3-grc-oir-dev", region="us-west-2", client=client)


def test_s3_round_trip_con_cliente_falso() -> None:
    alm = _s3(FakeS3Client())
    prefijo = alm.prefijo_contrato("C-2026-001")
    clave = alm.subir(prefijo=prefijo, nombre_archivo="acta.pdf", contenido=PDF_BYTES)
    assert clave == "contratos/C-2026-001/acta.pdf"

    docs = alm.listar(prefijo)
    assert len(docs) == 1
    assert isinstance(docs[0], DocumentoAlmacenado)
    assert docs[0].nombre == "acta.pdf"
    assert docs[0].tamano_bytes == len(PDF_BYTES)

    assert alm.obtener(clave) == PDF_BYTES
    alm.borrar(clave)
    assert alm.listar(prefijo) == []


def test_s3_config_incompleta_falla() -> None:
    with pytest.raises(AlmacenamientoError):
        AlmacenamientoS3(bucket="", region="us-west-2", client=FakeS3Client())


def test_s3_errores_se_mapean_a_dominio() -> None:
    alm = _s3(BrokenS3Client())
    with pytest.raises(AlmacenamientoError):
        alm.subir(prefijo="contratos/x/", nombre_archivo="a.pdf", contenido=PDF_BYTES)
    with pytest.raises(AlmacenamientoError):
        alm.listar("contratos/x/")
    with pytest.raises(AlmacenamientoError):
        alm.obtener("contratos/x/a.pdf")


# ══════════════════════════════════════════════════════════════════════════════════
# Endpoints (RBAC + validaciones), adaptador local por override
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Semilla: un anunciante + un contrato (con la MISMA sesión que usará la app).
    seed = SessionLocal()
    anunciante = AnuncianteService(
        AnuncianteRepository(seed, Anunciante),
        agencia_repo=BaseRepository(seed, Agencia),
        marca_repo=MarcaRepository(seed, Marca),
        contrato_repo=ContratoRepository(seed, Contrato),
    ).create(
        AnuncianteCreate(
            nombre_comercial="Refrescos",
            nombre_fiscal="Refrescos SA de CV",
            rfc_anunciante="RSA950101AB1",
        ),
        ADMIN,
    )
    contrato = ContratoService(
        ContratoRepository(seed, Contrato),
        anunciante_repo=BaseRepository(seed, Anunciante),
        almacenamiento=AlmacenamientoLocal(tmp_path),
    ).create(
        ContratoCreate(
            anunciante_id=anunciante.anunciante_id,
            numero_contrato="C-2026-001",
            nombre_contrato="Campaña anual",
            fecha_inicio_contrato=date(2026, 1, 1),
            fecha_fin_contrato=date(2026, 12, 31),
        ),
        ADMIN,
    )
    seed.close()

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(contrato_router, prefix="/api/v1/catalogos")

    def override_get_db() -> Iterator[Session]:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_service(db: Session = Depends(get_db)) -> ContratoService:
        repo = ContratoRepository(
            db, Contrato, search_columns=[Contrato.numero_contrato, Contrato.nombre_contrato]
        )
        return ContratoService(
            repo,
            anunciante_repo=BaseRepository(db, Anunciante),
            almacenamiento=AlmacenamientoLocal(tmp_path),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_contrato_service] = override_service

    yield TestClient(app), str(contrato.contrato_id)
    Base.metadata.drop_all(engine)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def _base(cid: str) -> str:
    return f"/api/v1/catalogos/contratos/{cid}/adjuntos"


def test_subir_listar_descargar_borrar(api) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    files = {"archivo": ("acta.pdf", PDF_BYTES, "application/pdf")}

    r = client.post(_base(cid), files=files, headers=_hdr("admin"))
    assert r.status_code == 201, r.text
    assert r.json()["nombre"] == "acta.pdf"
    assert r.json()["tamano_bytes"] == len(PDF_BYTES)

    r = client.get(_base(cid), headers=_hdr("admin"))
    assert r.status_code == 200
    assert [a["nombre"] for a in r.json()] == ["acta.pdf"]

    r = client.get(f"{_base(cid)}/acta.pdf", headers=_hdr("admin"))
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"] == "application/pdf"

    r = client.delete(f"{_base(cid)}/acta.pdf", headers=_hdr("admin"))
    assert r.status_code == 204

    r = client.get(_base(cid), headers=_hdr("admin"))
    assert r.json() == []


def test_rbac_lectura_vs_escritura(api) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    files = {"archivo": ("acta.pdf", PDF_BYTES, "application/pdf")}

    # ventas: puede LEER (listar) pero no ESCRIBIR (subir/borrar).
    assert client.get(_base(cid), headers=_hdr("ventas")).status_code == 200
    assert client.post(_base(cid), files=files, headers=_hdr("ventas")).status_code == 403
    assert client.delete(f"{_base(cid)}/acta.pdf", headers=_hdr("ventas")).status_code == 403


def test_subir_no_pdf_rechazado(api) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    files = {"archivo": ("notas.txt", b"hola", "text/plain")}
    r = client.post(_base(cid), files=files, headers=_hdr("admin"))
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_pdf"


def test_subir_contenido_no_pdf_rechazado(api) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    # extensión .pdf pero contenido que no empieza con %PDF-
    files = {"archivo": ("falso.pdf", b"esto no es un pdf", "application/pdf")}
    r = client.post(_base(cid), files=files, headers=_hdr("admin"))
    assert r.status_code == 400


def test_subir_excede_tamano(api, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    from app.core import config

    monkeypatch.setattr(config.settings, "s3_max_pdf_bytes", 16)
    files = {"archivo": ("grande.pdf", PDF_BYTES, "application/pdf")}  # > 16 bytes
    r = client.post(_base(cid), files=files, headers=_hdr("admin"))
    assert r.status_code == 413
    assert r.json()["error"]["codigo"] == "archivo_muy_grande"


def test_nombre_repetido_sobrescribe(api) -> None:  # type: ignore[no-untyped-def]
    client, cid = api
    v1 = {"archivo": ("acta.pdf", PDF_BYTES, "application/pdf")}
    v2 = {"archivo": ("acta.pdf", PDF_BYTES + b"v2", "application/pdf")}
    client.post(_base(cid), files=v1, headers=_hdr("admin"))
    client.post(_base(cid), files=v2, headers=_hdr("admin"))
    # sigue habiendo UN solo adjunto (mismo nombre), con el contenido nuevo.
    r = client.get(_base(cid), headers=_hdr("admin"))
    assert len(r.json()) == 1
    r = client.get(f"{_base(cid)}/acta.pdf", headers=_hdr("admin"))
    assert r.content == PDF_BYTES + b"v2"


def test_contrato_inexistente_404(api) -> None:  # type: ignore[no-untyped-def]
    client, _ = api
    otro = str(uuid.uuid4())
    r = client.get(_base(otro), headers=_hdr("admin"))
    assert r.status_code == 404
