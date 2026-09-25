"""Pruebas F1-08 · "Cancelar transmisión" de un día puntual (ADR-104).

Cubre: alta de la Verificacion (0 spots) + Incidencia (`spot_no_emitido`), recálculo de
importes de la OE excluyendo el día cancelado, liberación del cupo en el balance de
spots de la OC para otras OE, y las 2 salvaguardas de integridad necesarias para que un
día cancelado convivan con el resto del ciclo de vida sin romper la FK/UNIQUE de
`Verificacion`: `update()` con `dias` preserva los días cancelados, y `avanzar_reales`
los salta.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import DomainError, StateTransitionError
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
    OrdenCliente,
    OrdenClienteCreate,
    OrdenClienteRepository,
    OrdenClienteService,
)
from app.modules.ordenes.orden_estacion import (
    OrdenEstacion,
    OrdenEstacionCreate,
    OrdenEstacionDia,
    OrdenEstacionDiaAudioIn,
    OrdenEstacionDiaCancelarIn,
    OrdenEstacionDiaCreate,
    OrdenEstacionProgramadosIn,
    OrdenEstacionRealesIn,
    OrdenEstacionRepository,
    OrdenEstacionService,
    OrdenEstacionUpdate,
)
from app.modules.ordenes.verificacion import Verificacion
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")


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
    uid = uuid.uuid4()
    db.add(
        Usuario(usuario_id=uid, nombre_usuario="dev.admin", email="dev.admin@x.com", area="admin")
    )
    ids["usuario:dev.admin"] = uid

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
        fecha_inicio_campania=date.today() + timedelta(days=30),
        fecha_fin_campania=date.today() + timedelta(days=57),
        duracion_spot="30s",
        precio_unitario=Decimal("1000.00"),
        total_spots=100,
    )
    base.update(overrides)
    return OrdenClienteCreate(**base)


def _oe_payload(
    cat: dict[str, uuid.UUID], orden_id: uuid.UUID, **overrides: object
) -> OrdenEstacionCreate:
    base: dict[str, object] = dict(
        orden_id=orden_id,
        estacion_id=cat["estacion"],
        producto_tarifa="spot",
        duracion_spot="30s",
        precio_spot=Decimal("800.00"),
        observaciones_estacion=None,
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


def test_cancelar_dia_genera_verificacion_e_incidencia_y_recalcula(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dias = oe_svc.dias(oe.orden_estacion_id)
    dia_a_cancelar = dias[0]

    actualizada = oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia_a_cancelar.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="El cliente canceló el evento de ese día"),
        VENTAS,
    )

    # Solo quedan 10 spots facturables (el otro día) en vez de 20: 10 * 800 = 8000.
    assert actualizada.importe_estacion == Decimal("8000.00")

    verificacion = db.scalars(
        select(Verificacion).where(
            Verificacion.orden_estacion_dia_id == dia_a_cancelar.orden_estacion_dia_id
        )
    ).one()
    assert verificacion.spots_verificados == 0
    assert verificacion.reconciliada is True

    incidencia = db.scalars(
        select(Incidencia).where(Incidencia.verificacion_id == verificacion.verificacion_id)
    ).one()
    assert incidencia.tipo_incidencia == "spot_no_emitido"
    assert incidencia.spots_ordenados == 10
    assert incidencia.spots_ejecutados == 0
    assert incidencia.diferencia_spots == -10
    assert incidencia.monto_ajuste == Decimal("-8000.00")  # -10 * 800
    assert incidencia.descripcion_incidencia == "El cliente canceló el evento de ese día"

    dia_actualizado = db.get(OrdenEstacionDia, dia_a_cancelar.orden_estacion_dia_id)
    assert dia_actualizado is not None
    assert dia_actualizado.cancelada is True


def test_cancelar_dia_ya_cancelado_409(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="x"),
        VENTAS,
    )

    with pytest.raises(StateTransitionError):
        oe_svc.cancelar_dia(
            oe.orden_estacion_id,
            dia.orden_estacion_dia_id,
            OrdenEstacionDiaCancelarIn(motivo="y"),
            VENTAS,
        )


def test_cancelar_dia_ya_verificado_por_flujo_normal_409(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dia = oe_svc.dias(oe.orden_estacion_id)[0]

    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(dias=[]), VENTAS)
    oe_svc.avanzar_reales(oe.orden_estacion_id, OrdenEstacionRealesIn(dias=[]), VENTAS)

    with pytest.raises(StateTransitionError):
        oe_svc.cancelar_dia(
            oe.orden_estacion_id,
            dia.orden_estacion_dia_id,
            OrdenEstacionDiaCancelarIn(motivo="ya tarde"),
            VENTAS,
        )


def test_cancelar_dia_libera_cupo_para_otra_oe(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """`_oc_payload` por defecto trae `total_spots=100`; la OE de `_oe_payload` usa 20
    (10+10). Al cancelar un día (10), quedan 10 asignados — hay espacio de sobra para
    otra OE de 90 (100-10), pero NO para una de 91."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="x"),
        VENTAS,
    )

    # 10 (el día que sigue vivo) + 90 = 100: cabe justo.
    oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            dias=[
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=33),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=90,
                )
            ],
        ),
        VENTAS,
    )

    with pytest.raises(DomainError):
        oe_svc.create(
            _oe_payload(
                cat,
                oc.orden_id,
                dias=[
                    OrdenEstacionDiaCreate(
                        fecha_transmision=date.today() + timedelta(days=34),
                        hora_inicio=time(7, 0),
                        hora_fin=time(9, 0),
                        spots_asignados=1,
                    )
                ],
            ),
            VENTAS,
        )


def test_cancelar_dia_con_bonificables_que_excederian_lo_restante_400(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """Sube `cantidad_spots_bonificables` a 15 (edición libre, antes de transmitir) y
    cancela un día de 10 spots — de los 20 originales quedarían 10, menos que los 15
    bonificables ya capturados: debe rechazarse antes de dejar `importe_estacion`
    negativo."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.update(oe.orden_estacion_id, OrdenEstacionUpdate(cantidad_spots_bonificables=15), VENTAS)

    with pytest.raises(DomainError):
        oe_svc.cancelar_dia(
            oe.orden_estacion_id,
            dia.orden_estacion_dia_id,
            OrdenEstacionDiaCancelarIn(motivo="x"),
            VENTAS,
        )


def test_update_con_dias_preserva_el_dia_cancelado(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """Regresión: reemplazar `dias` completos (edición normal, antes de transmitir) NO
    debe intentar borrar/recrear un día ya cancelado (violaría la FK de su Verificacion)
    — debe quedar intacto aunque el cliente lo siga mandando de vuelta."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dias_originales = oe_svc.dias(oe.orden_estacion_id)
    dia_cancelado = dias_originales[0]
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia_cancelado.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="x"),
        VENTAS,
    )

    # El cliente reenvía TODOS los días que ve en pantalla (incluido el cancelado) más
    # uno nuevo — no debe reventar, y el cancelado debe seguir siendo la MISMA fila.
    actualizada = oe_svc.update(
        oe.orden_estacion_id,
        OrdenEstacionUpdate(
            dias=[
                OrdenEstacionDiaCreate(
                    fecha_transmision=dia_cancelado.fecha_transmision,
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=10,
                ),
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=40),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=5,
                ),
            ]
        ),
        VENTAS,
    )

    dias_finales = oe_svc.dias(actualizada.orden_estacion_id)
    ids_finales = {d.orden_estacion_dia_id for d in dias_finales}
    assert dia_cancelado.orden_estacion_dia_id in ids_finales  # misma fila, no una nueva
    cancelado_final = next(
        d for d in dias_finales if d.orden_estacion_dia_id == dia_cancelado.orden_estacion_dia_id
    )
    assert cancelado_final.cancelada is True
    # El día "vivo" original (día 2, no tocado) desapareció (reemplazo completo de los NO
    # cancelados); el nuevo (5 spots) sí quedó. Solo 5 spots cuentan para el importe.
    assert actualizada.importe_estacion == Decimal("4000.00")  # 5 * 800


def test_avanzar_reales_no_truena_con_un_dia_ya_cancelado(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """Regresión: si un día ya se canceló (ya tiene su propia Verificacion), el flujo
    normal 2.2→2.3 no debe intentar crear una SEGUNDA Verificacion para ese mismo día
    (violaría `uq_verificacion_orden_estacion_dia`) — debe saltarlo."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dias = oe_svc.dias(oe.orden_estacion_id)
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dias[0].orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="x"),
        VENTAS,
    )

    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(dias=[]), VENTAS)
    # No debe lanzar IntegrityError por el día ya cancelado.
    cerrada = oe_svc.avanzar_reales(oe.orden_estacion_id, OrdenEstacionRealesIn(dias=[]), VENTAS)
    assert cerrada.estatus == "cerrada"

    verificaciones = db.scalars(
        select(Verificacion)
        .join(
            OrdenEstacionDia,
            Verificacion.orden_estacion_dia_id == OrdenEstacionDia.orden_estacion_dia_id,
        )
        .where(OrdenEstacionDia.orden_estacion_id == oe.orden_estacion_id)
    ).all()
    # 1 del día cancelado (creada al cancelar) + 1 del día 2 (creada por avanzar_reales).
    assert len(verificaciones) == 2


def test_asignar_audio_a_dia_cancelado_sigue_permitido(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """No hay ninguna razón de negocio para bloquear esto — se deja tal cual (sin
    candado extra) y solo se confirma que no revienta."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="x"),
        VENTAS,
    )

    actualizado = oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=None),
        VENTAS,
    )
    assert actualizado.cancelada is True
