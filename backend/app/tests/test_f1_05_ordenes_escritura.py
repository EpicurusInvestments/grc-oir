"""Pruebas F1-05 · Escritura y lógica de negocio de Órdenes (SQLite).

Cubre lo que se movió del reducer de React al backend real: alta/edición de
OrdenCliente (cálculos, folio, checklist de Vo.Bo., comisiones snapshot auditadas),
el canal sensible de comisiones (Dirección/Admin únicamente), asignación de
OrdenEstacion (herencia de la OC, % OIR calculado, validaciones de tarifa/balance),
el avance 2.1→2.2→2.3 (generación automática de Verificacion/Incidencia, cascada de
estatus OE→OC) y el cierre de la OC (precondiciones, backfill de comisiones).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base, get_db
from app.core.errors import DomainError, NotFoundError, PermissionDeniedError, StateTransitionError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import Incidencia
from app.modules.ordenes.orden_cliente import (
    ITEMS_VOBO,
    EstatusOrden,
    OrdenCliente,
    OrdenClienteCerrarIn,
    OrdenClienteComisionesUpdate,
    OrdenClienteCreate,
    OrdenClienteRepository,
    OrdenClienteService,
    OrdenClienteUpdate,
)
from app.modules.ordenes.orden_estacion import (
    EstatusOrdenEstacion,
    OrdenEstacion,
    OrdenEstacionCreate,
    OrdenEstacionDiaCreate,
    OrdenEstacionDiaProgramadoIn,
    OrdenEstacionDiaRealIn,
    OrdenEstacionProgramadosIn,
    OrdenEstacionRealesIn,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.router import router as ordenes_router
from app.modules.ordenes.verificacion import Verificacion
from app.modules.usuarios.models import Usuario

# Un solo usuario real (`dev.admin`, el único sembrado en cualquier entorno — nunca
# personas de demo adicionales) en las 4 áreas: `área` viaja en un header INDEPENDIENTE
# de `username` (`core/security.py::get_current_user`), así que basta con variar `area`
# para probar el RBAC por área sin necesitar un `Usuario` distinto por persona.
VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")
DIRECCION = CurrentUser(username="dev.admin", area=Area.DIRECCION, ip="127.0.0.1")
ADMIN = CurrentUser(username="dev.admin", area=Area.ADMIN, ip="127.0.0.1")
NOMINAS = CurrentUser(username="dev.admin", area=Area.NOMINAS, ip="127.0.0.1")


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
def cat(db: Session) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for username, area in [
        ("dev.admin", "admin"),
    ]:
        uid = uuid.uuid4()
        db.add(
            Usuario(usuario_id=uid, nombre_usuario=username, email=f"{username}@x.com", area=area)
        )
        ids[f"usuario:{username}"] = uid

    plaza_id = uuid.uuid4()
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="CDMX"))
    ids["plaza"] = plaza_id

    afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="Afiliado Uno",
            razon_social_afiliado="Afiliado Uno SA de CV",
            rfc_afiliado="AUN900101AB1",
            plaza_id=plaza_id,
        )
    )
    ids["afiliado"] = afiliado_id

    estacion_id = uuid.uuid4()
    db.add(
        Estacion(
            estacion_id=estacion_id,
            afiliado_id=afiliado_id,
            plaza_id=plaza_id,
            nombre_estacion="XHTEST-FM",
            tipo_senal="fm",
        )
    )
    ids["estacion"] = estacion_id

    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
    ids["empresa"] = empresa_id

    vendedor_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=vendedor_id,
            nombre_vendedor="Vendedor Uno",
            porcentaje_comision_default=Decimal("4.00"),
        )
    )
    ids["vendedor"] = vendedor_id

    agencia_id = uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("15.00"),
        )
    )
    ids["agencia"] = agencia_id

    anunciante_id = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            agencia_id=agencia_id,
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
            rfc_anunciante="ANU900101AB1",
            dias_credito_default=30,
        )
    )
    ids["anunciante"] = anunciante_id

    otro_id = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=otro_id,
            agencia_id=None,
            nombre_comercial="Otro Anunciante",
            nombre_fiscal="Otro Anunciante SA de CV",
            rfc_anunciante="OTR900101AB1",
            dias_credito_default=30,
        )
    )
    ids["otro_anunciante"] = otro_id

    contrato_id = uuid.uuid4()
    db.add(
        Contrato(
            contrato_id=contrato_id,
            anunciante_id=anunciante_id,
            numero_contrato="CT-001",
            nombre_contrato="Contrato Uno",
            fecha_inicio_contrato=date(2025, 1, 1),
            fecha_fin_contrato=date(2025, 12, 31),
            estado_contrato="vigente",
        )
    )
    ids["contrato"] = contrato_id

    marca_id = uuid.uuid4()
    db.add(Marca(marca_id=marca_id, anunciante_id=anunciante_id, nombre_marca="Marca Uno"))
    ids["marca"] = marca_id

    categoria_id = uuid.uuid4()
    db.add(Categoria(categoria_id=categoria_id, nombre_categoria="Categoria Uno"))
    ids["categoria"] = categoria_id

    db.commit()
    return ids


@pytest.fixture
def oc_svc(db: Session) -> OrdenClienteService:
    repo = OrdenClienteRepository(db, OrdenCliente, search_columns=[OrdenCliente.folio_orden])
    return OrdenClienteService(repo)


@pytest.fixture
def oe_svc(db: Session) -> OrdenEstacionService:
    repo = OrdenEstacionRepository(
        db, OrdenEstacion, search_columns=[OrdenEstacion.folio_orden_estacion]
    )
    return OrdenEstacionService(repo)


def _oc_payload(cat: dict[str, uuid.UUID], **overrides: object) -> OrdenClienteCreate:
    base: dict[str, object] = dict(
        numero_orden_cliente="NUM-001",
        fecha_venta=date(2026, 1, 10),
        empresa_facturadora_id=cat["empresa"],
        vendedor_principal_id=cat["vendedor"],
        anunciante_id=cat["anunciante"],
        agencia_id=cat["agencia"],
        contrato_id=cat["contrato"],
        marca_id=cat["marca"],
        categoria_id=cat["categoria"],
        producto="Producto de prueba",
        # Relativas a hoy (no fijas): OrdenClienteCreate rechaza fecha_inicio_campania pasada.
        fecha_inicio_campania=date.today() + timedelta(days=30),
        fecha_fin_campania=date.today() + timedelta(days=57),
        duracion_spot="30s",
        precio_unitario=Decimal("1000.00"),
        total_spots=100,
    )
    base.update(overrides)
    return OrdenClienteCreate(**base)


def _dar_vobo_completo(oc_svc: OrdenClienteService, orden_id: uuid.UUID) -> None:
    for item in ITEMS_VOBO:
        oc_svc.vobo_toggle(orden_id, item, True, ADMIN)
    oc_svc.dar_vobo(orden_id, VENTAS)


# ── Alta de OrdenCliente ──────────────────────────────────────────────────────
def test_crear_oc_calcula_totales_y_folio(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    # Nota: `oc` es la instancia Pydantic en memoria (llamada de servicio directa, no
    # HTTP) — el `@field_serializer` a string solo aplica al serializar a JSON, así que
    # aquí se compara contra `Decimal` (las pruebas HTTP más abajo sí comparan strings).
    assert oc.subtotal == Decimal("100000.00")
    assert oc.iva == Decimal("16000.00")
    assert oc.total == Decimal("116000.00")
    assert oc.anio_venta == 2026
    assert oc.mes_venta == 1
    assert oc.total_dias_campania == 28
    assert oc.estatus_orden == EstatusOrden.RECIBIDA
    assert oc.folio_orden == "OC-2026-0041"


def test_crear_oc_folio_correlativo(oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]) -> None:
    primera = oc_svc.create(_oc_payload(cat), VENTAS)
    segunda = oc_svc.create(_oc_payload(cat, numero_orden_cliente="NUM-002"), VENTAS)
    n1 = int(primera.folio_orden.rsplit("-", 1)[1])
    n2 = int(segunda.folio_orden.rsplit("-", 1)[1])
    assert n2 == n1 + 1


def test_crear_oc_checklist_creado_vacio(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    items = oc_svc.vobo(oc.orden_id)
    assert {i.item_clave for i in items} == set(ITEMS_VOBO)
    assert all(not i.completado for i in items)


def test_crear_oc_fk_inexistente_404(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(NotFoundError):
        oc_svc.create(_oc_payload(cat, anunciante_id=uuid.uuid4()), VENTAS)


def test_crear_oc_rechaza_fecha_inicio_pasada(cat: dict[str, uuid.UUID]) -> None:
    with pytest.raises(ValidationError):
        _oc_payload(
            cat,
            fecha_inicio_campania=date.today() - timedelta(days=1),
            fecha_fin_campania=date.today() + timedelta(days=10),
        )


def test_crear_oc_contrato_de_otro_anunciante_400(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(DomainError):
        oc_svc.create(_oc_payload(cat, anunciante_id=cat["otro_anunciante"]), VENTAS)


def test_crear_oc_comision_auditada_sin_motivo(
    db: Session, oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(
        _oc_payload(cat, porcentaje_comision_vendedor_principal_snap=Decimal("5.00")), VENTAS
    )
    logs = db.scalars(
        select(LogCambioParametro).where(LogCambioParametro.entidad_id == str(oc.orden_id))
    ).all()
    assert len(logs) == 1
    assert logs[0].valor_anterior is None
    assert logs[0].valor_nuevo == "5.00"
    assert logs[0].motivo_cambio is None


# ── Checklist / Vo.Bo. ────────────────────────────────────────────────────────
def test_dar_vobo_incompleto_409(oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oc_svc.vobo_toggle(oc.orden_id, ITEMS_VOBO[0], True, VENTAS)
    with pytest.raises(StateTransitionError):
        oc_svc.dar_vobo(oc.orden_id, VENTAS)


def test_dar_vobo_completo_transiciona(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    actualizada = oc_svc.get(oc.orden_id)
    assert actualizada.estatus_orden == EstatusOrden.CAPTURADA


def test_dar_vobo_al_crear_con_checklist_completo(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    checklist = dict.fromkeys(ITEMS_VOBO, True)
    oc = oc_svc.create(_oc_payload(cat, revision_checklist=checklist, dar_vobo=True), VENTAS)
    assert oc.estatus_orden == EstatusOrden.CAPTURADA


def test_dar_vobo_al_crear_incompleto_409(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(StateTransitionError):
        oc_svc.create(
            _oc_payload(cat, revision_checklist={ITEMS_VOBO[0]: True}, dar_vobo=True), VENTAS
        )


# ── Edición normal ────────────────────────────────────────────────────────────
def test_editar_oc_recalcula_totales(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    editada = oc_svc.update(oc.orden_id, OrdenClienteUpdate(total_spots=50), VENTAS)
    assert editada.subtotal == Decimal("50000.00")
    assert editada.total == Decimal("58000.00")


def test_editar_oc_con_campania_ya_pasada_no_se_bloquea(
    db: Session, oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    """La regla de 'fecha_inicio_campania no puede ser pasada' solo aplica si el valor
    REALMENTE cambia (ver `_pre_update`): una orden ya en curso, cuya campaña por
    definición ya empezó, debe poder seguir editándose (aquí, otro campo) sin que el
    simple paso del calendario la bloquee."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    obj = db.get(OrdenCliente, oc.orden_id)
    assert obj is not None
    obj.fecha_inicio_campania = date.today() - timedelta(days=5)
    obj.fecha_fin_campania = date.today() + timedelta(days=5)
    db.commit()

    editada = oc_svc.update(oc.orden_id, OrdenClienteUpdate(total_spots=50), VENTAS)
    assert editada.total_spots == 50


def test_editar_oc_rechaza_cambiar_fecha_inicio_a_pasada(
    db: Session, oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    """A diferencia del caso anterior, aquí sí se intenta CAMBIAR fecha_inicio_campania
    a un valor nuevo — ese nuevo valor no puede ser una fecha pasada."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    with pytest.raises(DomainError):
        oc_svc.update(
            oc.orden_id,
            OrdenClienteUpdate(fecha_inicio_campania=date.today() - timedelta(days=1)),
            VENTAS,
        )


def test_editar_oc_permite_cambiar_fecha_inicio_a_futura(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    nueva_fecha = date.today() + timedelta(days=45)
    editada = oc_svc.update(
        oc.orden_id, OrdenClienteUpdate(fecha_inicio_campania=nueva_fecha), VENTAS
    )
    assert editada.fecha_inicio_campania == nueva_fecha


def test_editar_oc_amplia_rango_libremente_aunque_haya_dias_de_oe(
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """Ampliar el rango de campaña NUNCA rompe nada: todo día ya capturado seguía
    cabiendo, así que no se valida contra las OE hijas."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)  # -> capturada
    oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # días en hoy+32 y hoy+39

    editada = oc_svc.update(
        oc.orden_id,
        OrdenClienteUpdate(
            fecha_inicio_campania=date.today() + timedelta(days=20),
            fecha_fin_campania=date.today() + timedelta(days=70),
        ),
        VENTAS,
    )
    assert editada.fecha_fin_campania == date.today() + timedelta(days=70)


def test_editar_oc_angosta_rango_sin_tocar_dias_de_oe_se_permite(
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """Angostar es válido en tanto ningún día ya capturado quede fuera del nuevo rango."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # días en hoy+32 y hoy+39

    editada = oc_svc.update(
        oc.orden_id,
        OrdenClienteUpdate(
            fecha_inicio_campania=date.today() + timedelta(days=31),
            fecha_fin_campania=date.today() + timedelta(days=45),
        ),
        VENTAS,
    )
    assert editada.fecha_inicio_campania == date.today() + timedelta(days=31)


def test_editar_oc_angosta_fecha_fin_dejando_fuera_un_dia_de_oe_400(
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # días en hoy+32 y hoy+39

    with pytest.raises(DomainError):
        oc_svc.update(
            oc.orden_id,
            # Deja fuera el día de hoy+39.
            OrdenClienteUpdate(fecha_fin_campania=date.today() + timedelta(days=35)),
            VENTAS,
        )


def test_editar_oc_angosta_fecha_inicio_dejando_fuera_un_dia_de_oe_400(
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # días en hoy+32 y hoy+39

    with pytest.raises(DomainError):
        oc_svc.update(
            oc.orden_id,
            # Deja fuera el día de hoy+32.
            OrdenClienteUpdate(fecha_inicio_campania=date.today() + timedelta(days=33)),
            VENTAS,
        )


def test_editar_oc_congelada_409(
    db: Session, oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    obj = db.get(OrdenCliente, oc.orden_id)
    assert obj is not None
    obj.estatus_orden = EstatusOrden.ORDEN_CERRADA.value
    db.commit()
    with pytest.raises(StateTransitionError):
        oc_svc.update(oc.orden_id, OrdenClienteUpdate(numero_orden_cliente="X"), VENTAS)


# ── Comisiones (canal dedicado) ───────────────────────────────────────────────
def test_comisiones_ventas_403(oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    with pytest.raises(PermissionDeniedError):
        oc_svc.actualizar_comisiones(
            oc.orden_id,
            OrdenClienteComisionesUpdate(
                porcentaje_comision_vendedor_principal_snap=Decimal("6.00"),
                motivo_cambio="ajuste",
            ),
            VENTAS,
        )


def test_comisiones_direccion_sin_motivo_400(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(
        _oc_payload(cat, porcentaje_comision_vendedor_principal_snap=Decimal("4.00")), VENTAS
    )
    with pytest.raises(DomainError):
        oc_svc.actualizar_comisiones(
            oc.orden_id,
            OrdenClienteComisionesUpdate(
                porcentaje_comision_vendedor_principal_snap=Decimal("6.00")
            ),
            DIRECCION,
        )


def test_comisiones_direccion_con_motivo_ok(
    db: Session, oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(
        _oc_payload(cat, porcentaje_comision_vendedor_principal_snap=Decimal("4.00")), VENTAS
    )
    editada = oc_svc.actualizar_comisiones(
        oc.orden_id,
        OrdenClienteComisionesUpdate(
            porcentaje_comision_vendedor_principal_snap=Decimal("6.00"),
            motivo_cambio="Ajuste autorizado por desempeño.",
        ),
        DIRECCION,
    )
    assert editada.porcentaje_comision_vendedor_principal_snap == Decimal("6.00")
    logs = db.scalars(
        select(LogCambioParametro).where(LogCambioParametro.entidad_id == str(oc.orden_id))
    ).all()
    cambio = [log_ for log_ in logs if log_.valor_anterior == "4.00"]
    assert len(cambio) == 1
    assert cambio[0].valor_nuevo == "6.00"
    assert cambio[0].motivo_cambio == "Ajuste autorizado por desempeño."


def test_comisiones_sin_cambios_no_exige_motivo(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(
        _oc_payload(cat, porcentaje_comision_vendedor_principal_snap=Decimal("4.00")), VENTAS
    )
    # Mismo valor que ya tiene -> no es un cambio, no debe exigir motivo ni fallar.
    resultado = oc_svc.actualizar_comisiones(
        oc.orden_id,
        OrdenClienteComisionesUpdate(porcentaje_comision_vendedor_principal_snap=Decimal("4.00")),
        DIRECCION,
    )
    assert resultado.porcentaje_comision_vendedor_principal_snap == Decimal("4.00")


# ── OrdenEstacion ─────────────────────────────────────────────────────────────
def _oe_payload(
    cat: dict[str, uuid.UUID], orden_id: uuid.UUID, **overrides: object
) -> OrdenEstacionCreate:
    base: dict[str, object] = dict(
        orden_id=orden_id,
        estacion_id=cat["estacion"],
        precio_spot=Decimal("800.00"),
        observaciones_estacion=None,
        # Mismo rango relativo que la campaña de `_oc_payload` (hoy+30 .. hoy+57).
        dias=[
            OrdenEstacionDiaCreate(
                fecha_transmision=date.today() + timedelta(days=32),
                hora_inicio=time(7, 0),
                hora_fin=time(9, 0),
                spots_asignados=10,
            ),
            OrdenEstacionDiaCreate(
                fecha_transmision=date.today() + timedelta(days=39),
                hora_inicio=time(7, 0),
                hora_fin=time(9, 0),
                spots_asignados=10,
            ),
        ],
    )
    base.update(overrides)
    return OrdenEstacionCreate(**base)


def test_crear_oe_hereda_calcula_y_promueve_oc(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)  # -> capturada

    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    assert oe.anunciante_id == oc.anunciante_id
    assert oe.vendedor_id == oc.vendedor_principal_id
    assert oe.agencia_id == oc.agencia_id
    assert oe.duracion_spot == oc.duracion_spot
    assert oe.plaza_id == cat["plaza"]
    assert oe.estatus == EstatusOrdenEstacion.ASIGNADA
    # 20 spots * 800 = 16000; % OIR = (1000-800)/1000*100 = 20.0
    assert oe.importe_estacion == Decimal("16000.00")
    assert oe.porcentaje_participacion_oir == Decimal("20.0")
    assert oe.importe_oir == Decimal("3200.00")
    assert oe.folio_orden_estacion == oc.folio_orden.replace("OC-", "OE-") + "A"

    oc_tras = oc_svc.get(oc.orden_id)
    assert oc_tras.estatus_orden == EstatusOrden.EN_TRANSMISION


def test_crear_oe_precio_mayor_a_tarifa_cliente_400(
    oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    with pytest.raises(DomainError):
        oe_svc.create(_oe_payload(cat, oc.orden_id, precio_spot=Decimal("1500.00")), VENTAS)


def test_crear_oe_excede_balance_de_spots_400(
    oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat, total_spots=15), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    with pytest.raises(DomainError):
        oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # 20 spots > 15


def test_crear_oe_fecha_fuera_de_campania_400(
    oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    with pytest.raises(DomainError):
        oe_svc.create(
            _oe_payload(
                cat,
                oc.orden_id,
                dias=[
                    OrdenEstacionDiaCreate(
                        fecha_transmision=date.today() + timedelta(days=100),  # fuera de la campaña
                        hora_inicio=time(7, 0),
                        hora_fin=time(9, 0),
                        spots_asignados=10,
                    )
                ],
            ),
            VENTAS,
        )


# ── Programados / Reales / cascada de estatus ─────────────────────────────────
def test_flujo_programados_reales_genera_incidencia_y_cascada(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat, total_spots=20), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    # 2.1 -> 2.2: confirma un día distinto (el primer día, hoy+32 -> 8, en vez de 10).
    programada = oe_svc.avanzar_programados(
        oe.orden_estacion_id,
        OrdenEstacionProgramadosIn(
            dias=[
                OrdenEstacionDiaProgramadoIn(
                    fecha_transmision=date.today() + timedelta(days=32), spots_programados=8
                )
            ],
            reporte_programados_ref="reporte_prog.pdf",
        ),
        VENTAS,
    )
    assert programada.estatus == EstatusOrdenEstacion.EN_TRANSMISION

    # 2.2 -> 2.3: el primer día (hoy+32) se transmite con 6 (faltante de 2 vs programado=8);
    # el segundo día (hoy+39) se transmite tal cual programado (10, sin override -> sin incidencia).
    cerrada = oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    fecha_transmision=date.today() + timedelta(days=32), spots_verificados=6
                )
            ],
            testigos_url="https://ejemplo.com/testigo.mp3",
            notas_transmision="Corte de programación.",
        ),
        VENTAS,
    )
    assert cerrada.estatus == EstatusOrdenEstacion.CERRADA

    verificaciones = db.scalars(select(Verificacion)).all()
    assert len(verificaciones) == 2  # una por día, SIEMPRE (spec)

    incidencias = db.scalars(select(Incidencia)).all()
    assert len(incidencias) == 1
    inc = incidencias[0]
    assert inc.tipo_incidencia == "faltante"
    assert inc.diferencia_spots == -2
    assert inc.monto_ajuste == Decimal("-1600.00")  # -2 * 800
    assert inc.resolucion == "pendiente"

    # Única OE de la OC ya cerrada -> la OC pasa a en_verificacion.
    oc_tras = oc_svc.get(oc.orden_id)
    assert oc_tras.estatus_orden == EstatusOrden.EN_VERIFICACION


def test_cascada_solo_al_cerrar_la_ultima_oe(
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat, total_spots=40), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe1 = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe2 = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    for oe in (oe1, oe2):
        oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)

    oe_svc.avanzar_reales(oe1.orden_estacion_id, OrdenEstacionRealesIn(), VENTAS)
    assert oc_svc.get(oc.orden_id).estatus_orden == EstatusOrden.EN_TRANSMISION  # aún falta oe2

    oe_svc.avanzar_reales(oe2.orden_estacion_id, OrdenEstacionRealesIn(), VENTAS)
    assert oc_svc.get(oc.orden_id).estatus_orden == EstatusOrden.EN_VERIFICACION


# ── Cierre ────────────────────────────────────────────────────────────────────
def test_cerrar_sin_orden_estacion_409(
    oc_svc: OrdenClienteService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    with pytest.raises(StateTransitionError):
        oc_svc.cerrar(oc.orden_id, OrdenClienteCerrarIn(), VENTAS)


def test_cerrar_con_oe_pendiente_409(
    oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat, total_spots=20), VENTAS)
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)  # se queda en "asignada"
    with pytest.raises(StateTransitionError):
        oc_svc.cerrar(oc.orden_id, OrdenClienteCerrarIn(), VENTAS)


def test_cerrar_backfill_comisiones_y_flags(
    oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat: dict[str, uuid.UUID]
) -> None:
    oc = oc_svc.create(_oc_payload(cat, total_spots=20), VENTAS)  # sin comisiones
    _dar_vobo_completo(oc_svc, oc.orden_id)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(oe.orden_estacion_id, OrdenEstacionRealesIn(), VENTAS)

    cerrada = oc_svc.cerrar(oc.orden_id, OrdenClienteCerrarIn(odc_cerrada_ref="odc.pdf"), VENTAS)
    assert cerrada.estatus_orden == EstatusOrden.ORDEN_CERRADA
    assert cerrada.porcentaje_comision_vendedor_principal_snap == Decimal(
        "4.00"
    )  # default vendedor
    assert cerrada.porcentaje_comision_agencia_snap == Decimal("15.00")  # default agencia
    assert cerrada.cierre_sin_odc_cerrada is False
    assert cerrada.cierre_sin_carta_conciliacion is True  # no se mandó carta_conciliacion_ref
    assert cerrada.fecha_cierre is not None


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: RBAC de escritura (Nóminas sin acceso; Dirección solo por el canal dedicado)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    from app.core.errors import register_error_handlers

    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str, user: str = "dev.admin") -> dict[str, str]:
    return {"X-Dev-User": user, "X-Dev-Area": area}


def test_http_nominas_no_puede_crear_orden(client: TestClient, cat: dict[str, uuid.UUID]) -> None:
    r = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "NUM-HTTP",
            "fecha_venta": "2026-01-10",
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": str(date.today() + timedelta(days=30)),
            "fecha_fin_campania": str(date.today() + timedelta(days=57)),
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
        },
        headers=_hdr("nominas"),
    )
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"


def test_http_direccion_no_puede_crear_pero_si_editar_comisiones(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    fecha_inicio = str(date.today() + timedelta(days=30))
    fecha_fin = str(date.today() + timedelta(days=57))
    r_crear = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "NUM-HTTP2",
            "fecha_venta": "2026-01-10",
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": fecha_inicio,
            "fecha_fin_campania": fecha_fin,
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
        },
        headers=_hdr("direccion", "dev.admin"),
    )
    assert r_crear.status_code == 403

    r_creada = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "NUM-HTTP3",
            "fecha_venta": "2026-01-10",
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": fecha_inicio,
            "fecha_fin_campania": fecha_fin,
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
            "porcentaje_comision_vendedor_principal_snap": "4.00",
        },
        headers=_hdr("ventas", "dev.admin"),
    )
    assert r_creada.status_code == 201
    orden_id = r_creada.json()["orden_id"]

    r_com = client.patch(
        f"/api/v1/ordenes/clientes/{orden_id}/comisiones",
        json={
            "porcentaje_comision_vendedor_principal_snap": "7.00",
            "motivo_cambio": "Ajuste por negociación.",
        },
        headers=_hdr("direccion", "dev.admin"),
    )
    assert r_com.status_code == 200
    assert r_com.json()["porcentaje_comision_vendedor_principal_snap"] == "7.00"
