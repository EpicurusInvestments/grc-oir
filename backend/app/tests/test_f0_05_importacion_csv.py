"""Pruebas F0-05 · carga masiva CSV de ConstantesSistema (SQLite).

Cubre los casos del plan (sección E):
- archivo válido: dry-run (no escribe) + commit (persiste);
- filas inválidas (grupo malo, clave vacía): rechazadas con motivo, las válidas entran;
- duplicados: upsert (default) / omitir / rechazar, y duplicado DENTRO del archivo;
- columnas faltantes → 400; archivo/filas excedidos → 413; BOM manejado;
- RBAC: no-admin → 403.

La lógica de servicio se ejercita directa (bytes → reporte) y la costura HTTP con TestClient
(multipart, RBAC, límites). El DDL real se valida contra RDS por separado.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import config
from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.core.security import Area, CurrentUser
from app.modules.catalogos.constantes_sistema import (
    ConstanteSistema,
    ConstanteSistemaRepository,
    ConstanteSistemaService,
)
from app.modules.catalogos.constantes_sistema import router as constantes_router
from app.modules.catalogos.importacion_csv import ModoDuplicados

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")

CABECERA = "grupo,clave,descripcion,valor,activo"


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def svc(db: Session) -> ConstanteSistemaService:
    repo = ConstanteSistemaRepository(db, ConstanteSistema)
    return ConstanteSistemaService(repo)


def _csv(*lineas: str, cabecera: str = CABECERA) -> bytes:
    return ("\n".join([cabecera, *lineas]) + "\n").encode("utf-8")


def _total(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(ConstanteSistema)) or 0)


# ══════════════════════════════════════════════════════════════════════════════
# Servicio: dry-run vs commit
# ══════════════════════════════════════════════════════════════════════════════
def test_archivo_valido_dry_run_no_escribe(svc: ConstanteSistemaService, db: Session) -> None:
    contenido = _csv(
        "UsoCFDI,G03,Gastos en general,,true",
        "MonedaSAT,MXN,Peso mexicano,,true",
    )
    rep = svc.importar_csv(contenido, commit=False, modo=ModoDuplicados.ACTUALIZAR)
    assert rep.commit is False
    assert (rep.total_filas, rep.creadas, rep.rechazadas) == (2, 2, 0)
    assert all(f.estado == "creada" for f in rep.filas)
    assert _total(db) == 0  # dry-run NO escribe


def test_archivo_valido_commit_persiste(svc: ConstanteSistemaService, db: Session) -> None:
    contenido = _csv("UsoCFDI,G03,Gastos en general,,true", "MonedaSAT,MXN,Peso,,true")
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert (rep.commit, rep.creadas) == (True, 2)
    assert _total(db) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Filas inválidas: import parcial + motivo
# ══════════════════════════════════════════════════════════════════════════════
def test_filas_invalidas_se_rechazan_las_validas_entran(
    svc: ConstanteSistemaService, db: Session
) -> None:
    contenido = _csv(
        "UsoCFDI,G03,Gastos en general,,true",  # válida
        "NoEsGrupo,X,desc,,true",  # grupo inválido
        "UsoCFDI,,sin clave,,true",  # clave vacía
        "MonedaSAT,MXN,Peso,,true",  # válida
    )
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert (rep.total_filas, rep.creadas, rep.rechazadas) == (4, 2, 2)
    rechazadas = {f.numero: (f.motivo or "") for f in rep.filas if f.estado == "rechazada"}
    assert "Grupo inválido" in rechazadas[2]
    assert "clave es obligatoria" in rechazadas[3]
    assert _total(db) == 2  # solo las válidas


# ══════════════════════════════════════════════════════════════════════════════
# Duplicados: upsert / omitir / rechazar + duplicado dentro del archivo
# ══════════════════════════════════════════════════════════════════════════════
def _sembrar(svc: ConstanteSistemaService, *lineas: str) -> None:
    svc.importar_csv(_csv(*lineas), commit=True, modo=ModoDuplicados.ACTUALIZAR)


def test_duplicado_upsert_actualiza(svc: ConstanteSistemaService, db: Session) -> None:
    _sembrar(svc, "UsoCFDI,G03,Vieja descripción,,true")
    rep = svc.importar_csv(
        _csv("UsoCFDI,G03,Gastos en general,V2,false"),
        commit=True,
        modo=ModoDuplicados.ACTUALIZAR,
    )
    assert (rep.creadas, rep.actualizadas) == (0, 1)
    assert _total(db) == 1  # idempotente: no duplica
    obj = db.scalars(select(ConstanteSistema)).one()
    assert obj.descripcion == "Gastos en general"
    assert obj.valor == "V2"
    assert obj.activo is False


def test_duplicado_omitir(svc: ConstanteSistemaService, db: Session) -> None:
    _sembrar(svc, "UsoCFDI,G03,Original,,true")
    rep = svc.importar_csv(
        _csv("UsoCFDI,G03,Otra descripción,,true"), commit=True, modo=ModoDuplicados.OMITIR
    )
    assert (rep.omitidas, rep.actualizadas, rep.creadas) == (1, 0, 0)
    obj = db.scalars(select(ConstanteSistema)).one()
    assert obj.descripcion == "Original"  # no cambió


def test_duplicado_rechazar(svc: ConstanteSistemaService, db: Session) -> None:
    _sembrar(svc, "UsoCFDI,G03,Original,,true")
    rep = svc.importar_csv(
        _csv("UsoCFDI,G03,Otra,,true"), commit=True, modo=ModoDuplicados.RECHAZAR
    )
    assert rep.rechazadas == 1
    motivo = next(f.motivo or "" for f in rep.filas if f.estado == "rechazada")
    assert "Ya existe en la BD" in motivo


def test_duplicado_dentro_del_archivo(svc: ConstanteSistemaService, db: Session) -> None:
    contenido = _csv(
        "UsoCFDI,G03,Gastos,,true",
        "UsoCFDI,g03,Gastos duplicada (CI),,true",  # misma clave (CI) en el mismo archivo
    )
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert (rep.creadas, rep.rechazadas) == (1, 1)
    motivo = next(f.motivo or "" for f in rep.filas if f.estado == "rechazada")
    assert "duplicada dentro del archivo" in motivo
    assert _total(db) == 1


def test_misma_clave_distinto_grupo_ambas_entran(svc: ConstanteSistemaService, db: Session) -> None:
    contenido = _csv("FormaPago,01,Efectivo,,true", "MonedaSAT,01,Prueba,,true")
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert rep.creadas == 2
    assert _total(db) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Estructura: columnas, tamaño/filas, BOM
# ══════════════════════════════════════════════════════════════════════════════
def test_columnas_faltantes_aborta(svc: ConstanteSistemaService) -> None:
    from app.modules.catalogos.importacion_csv import ImportacionArchivoError

    contenido = _csv("UsoCFDI,G03", cabecera="grupo,clave")  # falta 'descripcion'
    with pytest.raises(ImportacionArchivoError):
        svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)


def test_filas_excedidas_aborta(svc: ConstanteSistemaService, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.modules.catalogos.importacion_csv import ArchivoDemasiadoGrandeError

    monkeypatch.setattr(config.settings, "import_csv_max_rows", 2)
    contenido = _csv(
        "UsoCFDI,G01,A,,true", "UsoCFDI,G02,B,,true", "UsoCFDI,G03,C,,true"
    )
    with pytest.raises(ArchivoDemasiadoGrandeError):
        svc.importar_csv(contenido, commit=False, modo=ModoDuplicados.ACTUALIZAR)


def test_bom_se_maneja(svc: ConstanteSistemaService, db: Session) -> None:
    # Excel suele exportar UTF-8 con BOM; utf-8-sig lo descarta y el encabezado se reconoce.
    contenido = ("﻿" + CABECERA + "\nUsoCFDI,G03,Gastos,,true\n").encode("utf-8")
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert rep.creadas == 1
    assert _total(db) == 1


def test_delimitador_punto_y_coma(svc: ConstanteSistemaService, db: Session) -> None:
    contenido = b"grupo;clave;descripcion;valor;activo\nUsoCFDI;G03;Gastos;;true\n"
    rep = svc.importar_csv(contenido, commit=True, modo=ModoDuplicados.ACTUALIZAR)
    assert rep.creadas == 1
    assert _total(db) == 1


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: multipart, RBAC, límites, extensión
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(constantes_router, prefix="/api/v1/catalogos")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def _files(contenido: bytes, nombre: str = "constantes.csv") -> dict[str, tuple[str, bytes, str]]:
    return {"archivo": (nombre, contenido, "text/csv")}


def test_http_admin_importa_commit(client: TestClient, db: Session) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(_csv("UsoCFDI,G03,Gastos,,true")),
        data={"commit": "true", "modo_duplicados": "actualizar"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 200
    assert r.json()["creadas"] == 1
    assert _total(db) == 1


def test_http_dry_run_no_escribe(client: TestClient, db: Session) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(_csv("UsoCFDI,G03,Gastos,,true")),
        data={"commit": "false"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["commit"] is False and body["creadas"] == 1
    assert _total(db) == 0


def test_http_ventas_no_puede_importar(client: TestClient) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(_csv("UsoCFDI,G03,Gastos,,true")),
        data={"commit": "true"},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"


def test_http_columnas_faltantes_400(client: TestClient) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(_csv("UsoCFDI,G03", cabecera="grupo,clave")),
        data={"commit": "true"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_invalido"


def test_http_extension_no_csv_400(client: TestClient) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(_csv("UsoCFDI,G03,Gastos,,true"), nombre="datos.txt"),
        data={"commit": "true"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_invalido"


def test_http_archivo_muy_grande_413(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(config.settings, "import_csv_max_bytes", 40)
    grande = _csv(*[f"UsoCFDI,G{i:03d},Descripción larga número {i},,true" for i in range(50)])
    r = client.post(
        "/api/v1/catalogos/constantes/importar",
        files=_files(grande),
        data={"commit": "true"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 413
    assert r.json()["error"]["codigo"] == "archivo_muy_grande"
