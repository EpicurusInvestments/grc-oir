"""Pruebas · ContactoAnunciante + ContactoAgencia (SQLite).

Entidades NUEVAS, fuera de la spec BD v2 (petición del usuario: Agencia y Anunciante ya
traían un solo contacto plano — `contacto_nombre`/`contacto_email`/`contacto_telefono`,
sin tocar — y ahora admiten varios). Mirror línea por línea de las pruebas de `Marca`
(`test_f0_03_anunciante_marca.py`), una vez por cada entidad padre:

- alta/edición/listado por el padre (anunciante u agencia) y validación de padre
  inexistente en alta y edición;
- activar/desactivar (baja lógica, sin bloqueo por dependientes — no se pidió esa regla);
- campos opcionales (puesto/teléfono/correo) pueden omitirse.

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
from app.modules.catalogos.agencia import (
    Agencia,
    AgenciaCreate,
    AgenciaRepository,
    AgenciaService,
    ContactoAgencia,
    ContactoAgenciaCreate,
    ContactoAgenciaRepository,
    ContactoAgenciaService,
    ContactoAgenciaUpdate,
)
from app.modules.catalogos.anunciante import (
    Anunciante,
    AnuncianteCreate,
    AnuncianteRepository,
    AnuncianteService,
    ContactoAnunciante,
    ContactoAnuncianteCreate,
    ContactoAnuncianteRepository,
    ContactoAnuncianteService,
    ContactoAnuncianteUpdate,
)
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
def agencia_svc(db: Session) -> AgenciaService:
    repo = AgenciaRepository(db, Agencia, search_columns=[Agencia.nombre_agencia])
    return AgenciaService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


@pytest.fixture
def anunciante_svc(db: Session) -> AnuncianteService:
    from app.modules.catalogos.anunciante import Marca, MarcaRepository
    from app.modules.catalogos.contrato import Contrato, ContratoRepository
    from app.shared.base_repository import BaseRepository

    repo = AnuncianteRepository(
        db,
        Anunciante,
        search_columns=[Anunciante.nombre_comercial, Anunciante.nombre_fiscal],
    )
    return AnuncianteService(
        repo,
        agencia_repo=BaseRepository(db, Agencia),
        marca_repo=MarcaRepository(db, Marca),
        contrato_repo=ContratoRepository(db, Contrato),
    )


@pytest.fixture
def contacto_anunciante_svc(
    db: Session, anunciante_svc: AnuncianteService
) -> ContactoAnuncianteService:
    repo = ContactoAnuncianteRepository(
        db, ContactoAnunciante, search_columns=[ContactoAnunciante.nombre_contacto]
    )
    return ContactoAnuncianteService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


@pytest.fixture
def contacto_agencia_svc(db: Session) -> ContactoAgenciaService:
    repo = ContactoAgenciaRepository(
        db, ContactoAgencia, search_columns=[ContactoAgencia.nombre_contacto]
    )
    return ContactoAgenciaService(repo, agencia_repo=AgenciaRepository(db, Agencia))


# ── helpers ───────────────────────────────────────────────────────────────────
def _agencia(svc: AgenciaService, nombre: str = "ACME Media") -> uuid.UUID:
    a = svc.create(AgenciaCreate(nombre_agencia=nombre, rfc_agencia="AME950101AB1"), ADMIN)
    return a.agencia_id


def _anunciante(svc: AnuncianteService, nombre: str = "Refrescos SA") -> uuid.UUID:
    a = svc.create(
        AnuncianteCreate(
            nombre_comercial=nombre,
            nombre_fiscal=f"{nombre} de CV",
            rfc_anunciante="RSA950101AB1",
            dias_credito_default=0,
        ),
        ADMIN,
    )
    return a.anunciante_id


# ── ContactoAnunciante ──────────────────────────────────────────────────────────
def test_contacto_anunciante_alta_y_listado_por_anunciante(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a = _anunciante(anunciante_svc)
    contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(
            anunciante_id=a,
            nombre_contacto="Ana López",
            puesto_contacto="Gerente de Marketing",
            telefono_contacto="5555551234",
            email_contacto="ana@refrescos.mx",
        ),
        ADMIN,
    )
    contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a, nombre_contacto="Beto Ruiz"), ADMIN
    )
    page = contacto_anunciante_svc.list_por_anunciante(a, ListParams())
    assert page.total == 2
    nombres = {c.nombre_contacto for c in page.items}
    assert nombres == {"Ana López", "Beto Ruiz"}
    ana = next(c for c in page.items if c.nombre_contacto == "Ana López")
    assert ana.puesto_contacto == "Gerente de Marketing"
    assert ana.telefono_contacto == "5555551234"
    assert ana.email_contacto == "ana@refrescos.mx"


def test_contacto_anunciante_campos_opcionales_pueden_omitirse(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a = _anunciante(anunciante_svc)
    creado = contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a, nombre_contacto="Solo Nombre"), ADMIN
    )
    assert creado.puesto_contacto is None
    assert creado.telefono_contacto is None
    assert creado.email_contacto is None


def test_contacto_anunciante_anunciante_inexistente_rechazado_en_alta(
    contacto_anunciante_svc: ContactoAnuncianteService,
) -> None:
    with pytest.raises(NotFoundError):
        contacto_anunciante_svc.create(
            ContactoAnuncianteCreate(anunciante_id=uuid.uuid4(), nombre_contacto="X"), ADMIN
        )


def test_contacto_anunciante_editar_actualiza_campos(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a = _anunciante(anunciante_svc)
    c = contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a, nombre_contacto="Ana López"), ADMIN
    )
    editado = contacto_anunciante_svc.update(
        c.contacto_anunciante_id,
        ContactoAnuncianteUpdate(puesto_contacto="Directora", telefono_contacto="5551112222"),
        ADMIN,
    )
    assert editado.nombre_contacto == "Ana López"  # sin tocar
    assert editado.puesto_contacto == "Directora"
    assert editado.telefono_contacto == "5551112222"


def test_contacto_anunciante_editar_reasignar_a_anunciante_inexistente_rechazado(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a = _anunciante(anunciante_svc)
    c = contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a, nombre_contacto="Ana López"), ADMIN
    )
    with pytest.raises(NotFoundError):
        contacto_anunciante_svc.update(
            c.contacto_anunciante_id,
            ContactoAnuncianteUpdate(anunciante_id=uuid.uuid4()),
            ADMIN,
        )


def test_contacto_anunciante_desactivar_y_reactivar(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a = _anunciante(anunciante_svc)
    c = contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a, nombre_contacto="Ana López"), ADMIN
    )
    desactivado = contacto_anunciante_svc.cambiar_estado(
        c.contacto_anunciante_id, activo=False, usuario=ADMIN
    )
    assert desactivado.activo is False
    reactivado = contacto_anunciante_svc.cambiar_estado(
        c.contacto_anunciante_id, activo=True, usuario=ADMIN
    )
    assert reactivado.activo is True


def test_contacto_anunciante_listado_solo_del_anunciante_pedido(
    anunciante_svc: AnuncianteService, contacto_anunciante_svc: ContactoAnuncianteService
) -> None:
    a1 = _anunciante(anunciante_svc, "Refrescos SA")
    a2 = _anunciante(anunciante_svc, "Galletas SA")
    contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a1, nombre_contacto="De A1"), ADMIN
    )
    contacto_anunciante_svc.create(
        ContactoAnuncianteCreate(anunciante_id=a2, nombre_contacto="De A2"), ADMIN
    )
    page = contacto_anunciante_svc.list_por_anunciante(a1, ListParams())
    assert page.total == 1
    assert page.items[0].nombre_contacto == "De A1"


# ── ContactoAgencia (mismas pruebas, mirror exacto) ──────────────────────────────
def test_contacto_agencia_alta_y_listado_por_agencia(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    contacto_agencia_svc.create(
        ContactoAgenciaCreate(
            agencia_id=ag,
            nombre_contacto="Carla Mora",
            puesto_contacto="Ejecutiva de cuenta",
            telefono_contacto="5559998877",
            email_contacto="carla@acme.mx",
        ),
        ADMIN,
    )
    contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag, nombre_contacto="Diego Vela"), ADMIN
    )
    page = contacto_agencia_svc.list_por_agencia(ag, ListParams())
    assert page.total == 2
    nombres = {c.nombre_contacto for c in page.items}
    assert nombres == {"Carla Mora", "Diego Vela"}
    carla = next(c for c in page.items if c.nombre_contacto == "Carla Mora")
    assert carla.puesto_contacto == "Ejecutiva de cuenta"
    assert carla.telefono_contacto == "5559998877"
    assert carla.email_contacto == "carla@acme.mx"


def test_contacto_agencia_campos_opcionales_pueden_omitirse(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    creado = contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag, nombre_contacto="Solo Nombre"), ADMIN
    )
    assert creado.puesto_contacto is None
    assert creado.telefono_contacto is None
    assert creado.email_contacto is None


def test_contacto_agencia_agencia_inexistente_rechazado_en_alta(
    contacto_agencia_svc: ContactoAgenciaService,
) -> None:
    with pytest.raises(NotFoundError):
        contacto_agencia_svc.create(
            ContactoAgenciaCreate(agencia_id=uuid.uuid4(), nombre_contacto="X"), ADMIN
        )


def test_contacto_agencia_editar_actualiza_campos(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    c = contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag, nombre_contacto="Carla Mora"), ADMIN
    )
    editado = contacto_agencia_svc.update(
        c.contacto_agencia_id,
        ContactoAgenciaUpdate(puesto_contacto="Directora de cuentas", email_contacto="c@acme.mx"),
        ADMIN,
    )
    assert editado.nombre_contacto == "Carla Mora"  # sin tocar
    assert editado.puesto_contacto == "Directora de cuentas"
    assert editado.email_contacto == "c@acme.mx"


def test_contacto_agencia_editar_reasignar_a_agencia_inexistente_rechazado(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    c = contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag, nombre_contacto="Carla Mora"), ADMIN
    )
    with pytest.raises(NotFoundError):
        contacto_agencia_svc.update(
            c.contacto_agencia_id, ContactoAgenciaUpdate(agencia_id=uuid.uuid4()), ADMIN
        )


def test_contacto_agencia_desactivar_y_reactivar(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    c = contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag, nombre_contacto="Carla Mora"), ADMIN
    )
    desactivado = contacto_agencia_svc.cambiar_estado(
        c.contacto_agencia_id, activo=False, usuario=ADMIN
    )
    assert desactivado.activo is False
    reactivado = contacto_agencia_svc.cambiar_estado(
        c.contacto_agencia_id, activo=True, usuario=ADMIN
    )
    assert reactivado.activo is True


def test_contacto_agencia_listado_solo_de_la_agencia_pedida(
    agencia_svc: AgenciaService, contacto_agencia_svc: ContactoAgenciaService
) -> None:
    ag1 = _agencia(agencia_svc, "ACME Media")
    ag2 = _agencia(agencia_svc, "Zenith")
    contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag1, nombre_contacto="De AG1"), ADMIN
    )
    contacto_agencia_svc.create(
        ContactoAgenciaCreate(agencia_id=ag2, nombre_contacto="De AG2"), ADMIN
    )
    page = contacto_agencia_svc.list_por_agencia(ag1, ListParams())
    assert page.total == 1
    assert page.items[0].nombre_contacto == "De AG1"
