"""Pruebas · ContactoAfiliado (SQLite).

Entidad NUEVA, fuera de la spec BD v2 (ADR-094): el Afiliado ya traía un solo contacto
plano (`contacto_nombre`/`contacto_email`/`contacto_telefono`, sin tocar) y ahora admite
varios. Mirror exacto de `test_f0_contacto_anunciante_agencia.py` (ADR-091):

- alta/edición/listado por el afiliado y validación de afiliado inexistente en alta y
  edición;
- activar/desactivar (baja lógica, sin bloqueo por dependientes — no se pidió esa regla);
- campos opcionales (puesto/teléfono/correo) pueden omitirse;
- aislamiento: el listado de un afiliado no trae contactos de otro.

El DDL real se valida contra RDS con `alembic upgrade` (round-trip verificado).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import NotFoundError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import (
    Afiliado,
    AfiliadoCreate,
    AfiliadoRepository,
    AfiliadoService,
    ContactoAfiliado,
    ContactoAfiliadoCreate,
    ContactoAfiliadoRepository,
    ContactoAfiliadoService,
    ContactoAfiliadoUpdate,
)
from app.modules.catalogos.estacion import Estacion, EstacionRepository
from app.shared.schemas import ListParams

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")


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
def afiliado_svc(db: Session) -> AfiliadoService:
    return AfiliadoService(
        AfiliadoRepository(
            db,
            Afiliado,
            search_columns=[Afiliado.nombre_afiliado, Afiliado.razon_social_afiliado],
        ),
        estacion_repo=EstacionRepository(db, Estacion),
    )


@pytest.fixture
def contacto_afiliado_svc(db: Session) -> ContactoAfiliadoService:
    repo = ContactoAfiliadoRepository(
        db, ContactoAfiliado, search_columns=[ContactoAfiliado.nombre_contacto]
    )
    return ContactoAfiliadoService(repo, afiliado_repo=AfiliadoRepository(db, Afiliado))


# ── helpers ───────────────────────────────────────────────────────────────────
def _afiliado(
    svc: AfiliadoService,
    nombre: str = "OIR Bajío",
    rfc: str = "OIR920301AB1",
) -> uuid.UUID:
    a = svc.create(
        AfiliadoCreate(
            nombre_afiliado=nombre,
            razon_social_afiliado=f"{nombre} SA de CV",
            rfc_afiliado=rfc,
        ),
        ADMIN,
    )
    return a.afiliado_id


def test_contacto_afiliado_alta_y_listado_por_afiliado(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi = _afiliado(afiliado_svc)
    contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(
            afiliado_id=afi,
            nombre_contacto="Fernanda Ortiz",
            puesto_contacto="Gerente de operación",
            telefono_contacto="4771234567",
            email_contacto="f.ortiz@oirbajio.com",
        ),
        ADMIN,
    )
    contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi, nombre_contacto="Beto Ruiz"), ADMIN
    )
    page = contacto_afiliado_svc.list_por_afiliado(afi, ListParams())
    assert page.total == 2
    nombres = {c.nombre_contacto for c in page.items}
    assert nombres == {"Fernanda Ortiz", "Beto Ruiz"}
    fer = next(c for c in page.items if c.nombre_contacto == "Fernanda Ortiz")
    assert fer.puesto_contacto == "Gerente de operación"
    assert fer.telefono_contacto == "4771234567"
    assert fer.email_contacto == "f.ortiz@oirbajio.com"


def test_contacto_afiliado_campos_opcionales_pueden_omitirse(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi = _afiliado(afiliado_svc)
    creado = contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi, nombre_contacto="Solo Nombre"), ADMIN
    )
    assert creado.puesto_contacto is None
    assert creado.telefono_contacto is None
    assert creado.email_contacto is None


def test_contacto_afiliado_afiliado_inexistente_rechazado_en_alta(
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    with pytest.raises(NotFoundError):
        contacto_afiliado_svc.create(
            ContactoAfiliadoCreate(afiliado_id=uuid.uuid4(), nombre_contacto="X"), ADMIN
        )


def test_contacto_afiliado_editar_actualiza_campos(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi = _afiliado(afiliado_svc)
    c = contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi, nombre_contacto="Fernanda Ortiz"), ADMIN
    )
    editado = contacto_afiliado_svc.update(
        c.contacto_afiliado_id,
        ContactoAfiliadoUpdate(puesto_contacto="Directora", telefono_contacto="4779998877"),
        ADMIN,
    )
    assert editado.nombre_contacto == "Fernanda Ortiz"  # sin tocar
    assert editado.puesto_contacto == "Directora"
    assert editado.telefono_contacto == "4779998877"


def test_contacto_afiliado_editar_reasignar_a_afiliado_inexistente_rechazado(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi = _afiliado(afiliado_svc)
    c = contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi, nombre_contacto="Fernanda Ortiz"), ADMIN
    )
    with pytest.raises(NotFoundError):
        contacto_afiliado_svc.update(
            c.contacto_afiliado_id, ContactoAfiliadoUpdate(afiliado_id=uuid.uuid4()), ADMIN
        )


def test_contacto_afiliado_desactivar_y_reactivar(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi = _afiliado(afiliado_svc)
    c = contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi, nombre_contacto="Fernanda Ortiz"), ADMIN
    )
    desactivado = contacto_afiliado_svc.cambiar_estado(
        c.contacto_afiliado_id, activo=False, usuario=ADMIN
    )
    assert desactivado.activo is False
    reactivado = contacto_afiliado_svc.cambiar_estado(
        c.contacto_afiliado_id, activo=True, usuario=ADMIN
    )
    assert reactivado.activo is True


def test_contacto_afiliado_listado_solo_del_afiliado_pedido(
    afiliado_svc: AfiliadoService,
    contacto_afiliado_svc: ContactoAfiliadoService,
) -> None:
    afi1 = _afiliado(afiliado_svc, "OIR Bajío", rfc="OIR920301AB1")
    afi2 = _afiliado(afiliado_svc, "OIR Centro", rfc="MEO850101OP2")
    contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi1, nombre_contacto="De AFI1"), ADMIN
    )
    contacto_afiliado_svc.create(
        ContactoAfiliadoCreate(afiliado_id=afi2, nombre_contacto="De AFI2"), ADMIN
    )
    page = contacto_afiliado_svc.list_por_afiliado(afi1, ListParams())
    assert page.total == 1
    assert page.items[0].nombre_contacto == "De AFI1"
