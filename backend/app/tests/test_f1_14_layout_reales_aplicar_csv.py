"""Pruebas F1-14 · ADR-147/ADR-149 (petición del usuario) — "Carga de Órdenes Reales
Desde Layout" parsea el CSV (columnas Estacion, Fecha, Hora, Spots — Spots opcional,
default 1): las filas válidas se agrupan por fecha+hora exactas y sus Spots se SUMAN;
cada grupo se ofrece como `aplicados` (si la fecha+hora ya existe como día de la OE) o
`nuevos` (si no existe — se crea como día nuevo al avanzar a 2.3, mismo criterio que
asignar una hora distinta al crear la OE). Una fila inválida (estación distinta, valor
no parseable, o un grupo nuevo cuya suma da 0) se IGNORA y se reporta en `errores`, sin
tumbar el resto del archivo — confirmado con el usuario.

Mismo patrón de fixtures que `test_f1_13_layout_reales_y_formato_real_cliente.py`, pero
con una OE de VARIOS días (para poder probar match/no-match entre filas).
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import DomainError, register_error_handlers
from app.core.security import Area, CurrentUser
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.documentos import ArchivoNoPermitidoError
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
    OrdenEstacionDiaCancelarIn,
    OrdenEstacionDiaCreate,
    OrdenEstacionDiaNuevoIn,
    OrdenEstacionDiaRealIn,
    OrdenEstacionRealesIn,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.router import router as ordenes_router
from app.modules.ordenes.verificacion import Verificacion
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")


class _ArchivoFalso:
    def __init__(self, filename: str, contenido: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(contenido)


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
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="León"))
    ids["plaza"] = plaza_id

    afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="OIR Bajío",
            razon_social_afiliado="OIR Bajío SA de CV",
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
            nombre_estacion="Radio Disney",
            frecuencia="97.7 FM",
            tipo_senal="fm",
        )
    )
    ids["estacion"] = estacion_id

    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id,
            nombre_empresa="Radio Publicidad XHMéxico, S.A. de C.V.",
            rfc_empresa="OTE900101AB1",
            direccion_empresa="Av. Constituyentes 1154, Col. Lomas Altas, México, D.F., C.P. 11950",
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
            nombre_agencia="OMD México",
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
            nombre_comercial="Grupo Bimbo",
            nombre_fiscal="Grupo Bimbo SA de CV",
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
    db.add(Categoria(categoria_id=categoria_id, nombre_categoria="Alimentos y bebidas"))
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


def _oc_payload(cat: dict[str, uuid.UUID]) -> OrdenClienteCreate:
    return OrdenClienteCreate(
        numero_orden_cliente="PO-BIMBO-0421",
        fecha_venta=date(2026, 1, 10),
        empresa_facturadora_id=cat["empresa"],
        vendedor_principal_id=cat["vendedor"],
        anunciante_id=cat["anunciante"],
        agencia_id=cat["agencia"],
        contrato_id=cat["contrato"],
        marca_id=cat["marca"],
        categoria_id=cat["categoria"],
        producto="Pan Bimbo Integral 680g",
        fecha_inicio_campania=date.today() + timedelta(days=30),
        fecha_fin_campania=date.today() + timedelta(days=90),
        producto_tarifa="spot",
        duracion_spot="30s",
        precio_unitario=Decimal("1000.00"),
        total_spots=100,
    )


# 3 días, 2 de ellos con la MISMA fecha (distinto horario) — para probar que el match es
# por fecha+hora, no solo por fecha (ADR-127).
_DIA_1 = date.today() + timedelta(days=32)
_DIA_2 = date.today() + timedelta(days=33)


def _oe_payload(cat: dict[str, uuid.UUID], orden_id: uuid.UUID) -> OrdenEstacionCreate:
    return OrdenEstacionCreate(
        orden_id=orden_id,
        estacion_id=cat["estacion"],
        producto_tarifa="spot",
        duracion_spot="30s",
        precio_spot=Decimal("800.00"),
        dias=[
            OrdenEstacionDiaCreate(
                fecha_transmision=_DIA_1,
                hora_inicio=time(7, 0),
                hora_fin=time(7, 0),
                spots_asignados=10,
            ),
            OrdenEstacionDiaCreate(
                fecha_transmision=_DIA_1,
                hora_inicio=time(20, 0),
                hora_fin=time(20, 0),
                spots_asignados=5,
            ),
            OrdenEstacionDiaCreate(
                fecha_transmision=_DIA_2,
                hora_inicio=time(7, 0),
                hora_fin=time(7, 0),
                spots_asignados=8,
            ),
        ],
    )


@pytest.fixture
def oe(oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat):
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    return oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)


def _csv(*filas: str, encabezado: str = "Estacion,Fecha,Hora,Spots") -> bytes:
    return ("\n".join([encabezado, *filas]) + "\n").encode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════════
# Servicio: parseo + aplicación
# ══════════════════════════════════════════════════════════════════════════════════
def test_aplica_spots_por_fecha_y_hora_exactas(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(
        f"Radio Disney,{_DIA_1},07:00,12",
        f"Radio Disney,{_DIA_1},20:00,6",
    )
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    # 2 coincidencias reales + el 3er día de la OE (DIA_2 07:00), que el archivo no
    # menciona, se agrega como faltante en 0 (ADR-157).
    assert len(resultado.aplicados) == 3
    por_fecha_hora = {(a.fecha_transmision, a.hora_inicio): a.spots for a in resultado.aplicados}
    assert por_fecha_hora[(_DIA_1, time(7, 0))] == 12
    assert por_fecha_hora[(_DIA_1, time(20, 0))] == 6
    assert por_fecha_hora[(_DIA_2, time(7, 0))] == 0


def test_spots_vacio_usa_default_1(db: Session, oe_svc: OrdenEstacionService, oe, tmp_path) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00,")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    # + 2 faltantes (DIA_1 20:00 y DIA_2 07:00, que el archivo no menciona — ADR-157).
    assert len(resultado.aplicados) == 3
    assert resultado.aplicados[0].spots == 1


def test_columna_spots_ausente_usa_default_1(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00", encabezado="Estacion,Fecha,Hora")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    assert resultado.aplicados[0].spots == 1


def test_estacion_distinta_se_ignora_sin_tumbar_las_demas(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(
        f"Radio Disney,{_DIA_1},07:00,12",
        f"Radio MTY,{_DIA_1},20:00,6",  # estación equivocada
    )
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # + 2 faltantes (DIA_1 20:00 — su única fila válida vino con la estación
    # equivocada, así que cuenta como no mencionado — y DIA_2 07:00 — ADR-157).
    assert len(resultado.aplicados) == 3
    assert resultado.aplicados[0].spots == 12
    assert len(resultado.errores) == 1
    assert resultado.errores[0].fila == 3
    assert "Radio MTY" in resultado.errores[0].motivo


def test_estacion_insensible_a_acentos_mayusculas_y_espacios(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"  radio DISNEY  ,{_DIA_1},07:00,9")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    assert resultado.aplicados[0].spots == 9


def test_fecha_hora_sin_match_se_propone_como_dia_nuevo(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """ADR-149 (petición del usuario): una fecha+hora que no existe entre los días de
    esta OE ya NO se ignora como error — se ofrece como día NUEVO a crear si el usuario
    avanza a 2.3 (mismo criterio que asignar una hora distinta al crear la OE)."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    otra_fecha = _DIA_1 + timedelta(days=99)
    contenido = _csv(
        f"Radio Disney,{_DIA_1},07:00,12",
        f"Radio Disney,{otra_fecha},07:00,5",  # fecha que no existe en la OE
    )
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # + 2 faltantes (DIA_1 20:00 y DIA_2 07:00 — ADR-157).
    assert len(resultado.aplicados) == 3
    assert resultado.errores == []
    assert len(resultado.nuevos) == 1
    assert resultado.nuevos[0].fecha_transmision == otra_fecha
    assert resultado.nuevos[0].hora_inicio == time(7, 0)
    assert resultado.nuevos[0].spots == 5


def test_fecha_hora_nueva_con_spots_cero_es_error(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """Un día nuevo necesita spots > 0 (`spots_solicitados` no acepta 0) — si la fecha+
    hora no existe y la suma de spots da 0, se reporta como error en vez de proponerse
    como día nuevo."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    otra_fecha = _DIA_1 + timedelta(days=99)
    contenido = _csv(f"Radio Disney,{otra_fecha},07:00,0")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # El archivo no tocó ningún día existente de la OE (la única fila válida era una
    # fecha nueva, rechazada) — los 3 se agregan como faltantes en 0 (ADR-157).
    assert len(resultado.aplicados) == 3
    assert all(a.spots == 0 for a in resultado.aplicados)
    assert resultado.nuevos == []
    assert len(resultado.errores) == 1
    assert "0 spots" in resultado.errores[0].motivo


def test_filas_con_misma_fecha_hora_suman_spots(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """ADR-149 (petición del usuario): 2+ filas con la misma fecha+hora no se pisan
    entre sí — sus `Spots` se SUMAN."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(
        f"Radio Disney,{_DIA_1},07:00,2",
        f"  radio DISNEY  ,{_DIA_1},07:00,4",  # misma fecha+hora, estación normalizada
        f"Radio Disney,{_DIA_1},07:00,8",
    )
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    # + 2 faltantes (DIA_1 20:00 y DIA_2 07:00 — ADR-157).
    assert len(resultado.aplicados) == 3
    assert resultado.aplicados[0].spots == 14


def test_filas_nuevas_con_misma_fecha_hora_suman_spots(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    otra_fecha = _DIA_1 + timedelta(days=99)
    contenido = _csv(
        f"Radio Disney,{otra_fecha},09:00,3",
        f"Radio Disney,{otra_fecha},09:00,7",
    )
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.errores == []
    assert len(resultado.nuevos) == 1
    assert resultado.nuevos[0].spots == 10


def test_fecha_invalida_se_ignora(db: Session, oe_svc: OrdenEstacionService, oe, tmp_path) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv("Radio Disney,31/13/2026,07:00,5")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # Ninguna fila válida tocó ningún día de la OE — los 3 se agregan como faltantes
    # en 0 (ADR-157).
    assert len(resultado.aplicados) == 3
    assert all(a.spots == 0 for a in resultado.aplicados)
    assert "Fecha inválida" in resultado.errores[0].motivo


def test_spots_no_numerico_se_ignora(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00,abc")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # Ninguna fila válida tocó ningún día de la OE — los 3 se agregan como faltantes
    # en 0 (ADR-157).
    assert len(resultado.aplicados) == 3
    assert all(a.spots == 0 for a in resultado.aplicados)
    assert "Spots inválido" in resultado.errores[0].motivo


def test_encabezados_faltantes_reporta_un_solo_error(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"{_DIA_1},07:00,5", encabezado="Fecha,Hora,Spots")  # falta Estacion
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert resultado.aplicados == []
    assert len(resultado.errores) == 1
    assert resultado.errores[0].fila == 0
    assert "Encabezados esperados" in resultado.errores[0].motivo


# ══════════════════════════════════════════════════════════════════════════════════
# ADR-157 (petición del usuario): conciliación completa contra lo programado — un día
# que el archivo no menciona ya no desaparece, se marca como faltante (spots=0).
# ══════════════════════════════════════════════════════════════════════════════════
def test_dia_no_mencionado_se_marca_como_faltante_en_cero(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    # Solo toca 1 de los 3 días de la OE.
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00,12")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    assert len(resultado.aplicados) == 3
    por_fecha_hora = {(a.fecha_transmision, a.hora_inicio): a.spots for a in resultado.aplicados}
    assert por_fecha_hora[(_DIA_1, time(7, 0))] == 12
    assert por_fecha_hora[(_DIA_1, time(20, 0))] == 0
    assert por_fecha_hora[(_DIA_2, time(7, 0))] == 0


def test_dia_faltante_genera_incidencia_al_avanzar(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """El `spots=0` que ADR-157 agrega para un día no mencionado en el archivo se manda
    a `avanzar_reales` exactamente como cualquier otro override manual — sin caso
    especial: genera su `Incidencia` de tipo `faltante` igual que si el usuario hubiera
    editado ese día a 0 a mano."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00,12")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )
    dia_faltante = next(
        a
        for a in resultado.aplicados
        if (a.fecha_transmision, a.hora_inicio) == (_DIA_1, time(20, 0))
    )
    assert dia_faltante.spots == 0

    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=dia_faltante.orden_estacion_dia_id,
                    spots_verificados=0,
                )
            ],
            dias_nuevos=[],
        ),
        VENTAS,
    )

    verificacion = db.scalar(
        select(Verificacion).where(
            Verificacion.orden_estacion_dia_id == dia_faltante.orden_estacion_dia_id
        )
    )
    assert verificacion is not None
    assert verificacion.spots_verificados == 0

    incidencia = db.scalar(
        select(Incidencia).where(Incidencia.verificacion_id == verificacion.verificacion_id)
    )
    assert incidencia is not None
    assert incidencia.tipo_incidencia == "faltante"


def test_dia_cancelado_no_se_marca_como_faltante(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """Un día ya cancelado (ADR-104) tiene su propia `Verificacion` creada al cancelar —
    no debe volver a aparecer como "faltante" solo porque el archivo no lo menciona
    (una segunda `Verificacion` violaría `uq_verificacion_orden_estacion_dia`)."""
    dias = oe_svc._repo.listar_dias(oe.orden_estacion_id)
    dia_a_cancelar = next(d for d in dias if d.hora_inicio == time(20, 0))
    oe_svc.cancelar_dia(
        oe.orden_estacion_id,
        dia_a_cancelar.orden_estacion_dia_id,
        OrdenEstacionDiaCancelarIn(motivo="Prueba"),
        VENTAS,
    )

    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = _csv(f"Radio Disney,{_DIA_1},07:00,12")
    resultado = oe_svc.agregar_layout_real(
        oe.orden_estacion_id, _ArchivoFalso("layout.csv", contenido), VENTAS, almacenamiento
    )

    # Solo el día cancelado queda fuera: DIA_1 07:00 (tocado) + DIA_2 07:00 (faltante).
    # El cancelado (DIA_1 20:00) NO debe aparecer.
    claves = {(a.fecha_transmision, a.hora_inicio) for a in resultado.aplicados}
    assert claves == {(_DIA_1, time(7, 0)), (_DIA_2, time(7, 0))}


def test_xlsx_se_rechaza_por_no_estar_en_la_lista_blanca(
    db: Session, oe_svc: OrdenEstacionService, oe, tmp_path
) -> None:
    """ADR-154 (petición del usuario): antes (ADR-146) xlsx se aceptaba sin parsear;
    ahora la carga de layout se restringió a SOLO csv, así que xlsx se rechaza."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = b"PK\x03\x04 contenido de prueba de excel"

    with pytest.raises(ArchivoNoPermitidoError):
        oe_svc.agregar_layout_real(
            oe.orden_estacion_id, _ArchivoFalso("layout.xlsx", contenido), VENTAS, almacenamiento
        )


# ══════════════════════════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session, tmp_path) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path)
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "dev.admin", "X-Dev-Area": area}


def test_http_post_layout_devuelve_archivo_aplicados_y_errores(
    client: TestClient, db: Session, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    contenido = _csv(
        f"Radio Disney,{_DIA_1},07:00,12",
        f"Radio MTY,{_DIA_1},20:00,6",
    )
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/layout-reales",
        files={"archivo": ("layout.csv", contenido, "text/csv")},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["archivo"]["nombre_archivo"] == "layout.csv"
    # + 2 faltantes (DIA_1 20:00 — su única fila vino con la estación equivocada — y
    # DIA_2 07:00 — ADR-157).
    assert len(body["aplicados"]) == 3
    assert body["aplicados"][0]["spots"] == 12
    assert body["nuevos"] == []
    assert len(body["errores"]) == 1
    assert "Radio MTY" in body["errores"][0]["motivo"]


# ══════════════════════════════════════════════════════════════════════════════════
# ADR-149: avanzar_reales con `dias_nuevos` (días que el layout propuso crear)
# ══════════════════════════════════════════════════════════════════════════════════
def test_avanzar_reales_crea_dia_nuevo_sin_incidencia(
    db: Session, oe_svc: OrdenEstacionService, oe
) -> None:
    otra_fecha = _DIA_1 + timedelta(days=10)  # dentro de la campaña (hoy+30..hoy+90)
    resultado = oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[],
            dias_nuevos=[
                OrdenEstacionDiaNuevoIn(
                    fecha_transmision=otra_fecha, hora_inicio=time(9, 0), spots=5
                )
            ],
        ),
        VENTAS,
    )
    assert resultado.estatus == "cerrada"

    nuevo_dia = db.scalar(
        select(OrdenEstacionDia).where(
            OrdenEstacionDia.orden_estacion_id == oe.orden_estacion_id,
            OrdenEstacionDia.fecha_transmision == otra_fecha,
            OrdenEstacionDia.hora_inicio == time(9, 0),
        )
    )
    assert nuevo_dia is not None
    assert nuevo_dia.spots_solicitados == 5
    assert nuevo_dia.spots_asignados == 5
    assert nuevo_dia.spots_programados is None

    verificacion = db.scalar(
        select(Verificacion).where(
            Verificacion.orden_estacion_dia_id == nuevo_dia.orden_estacion_dia_id
        )
    )
    assert verificacion is not None
    assert verificacion.spots_verificados == 5

    # spots_asignados == spots_verificados por construcción → nunca hay Incidencia.
    incidencia = db.scalar(
        select(Incidencia).where(Incidencia.verificacion_id == verificacion.verificacion_id)
    )
    assert incidencia is None


def test_avanzar_reales_dia_nuevo_fuera_de_campania_400(
    db: Session, oe_svc: OrdenEstacionService, oe
) -> None:
    fuera_de_campania = date.today() + timedelta(days=365)
    with pytest.raises(DomainError):
        oe_svc.avanzar_reales(
            oe.orden_estacion_id,
            OrdenEstacionRealesIn(
                dias=[],
                dias_nuevos=[
                    OrdenEstacionDiaNuevoIn(
                        fecha_transmision=fuera_de_campania, hora_inicio=time(9, 0), spots=5
                    )
                ],
            ),
            VENTAS,
        )


def test_avanzar_reales_dia_nuevo_excede_balance_spots_400(
    db: Session, oe_svc: OrdenEstacionService, oe
) -> None:
    # La OC de `oe` tiene total_spots=100; los 3 días de `oe` ya suman 10+5+8=23
    # asignados — pedir 80 más excede el balance.
    otra_fecha = _DIA_1 + timedelta(days=10)  # dentro de la campaña
    with pytest.raises(DomainError):
        oe_svc.avanzar_reales(
            oe.orden_estacion_id,
            OrdenEstacionRealesIn(
                dias=[],
                dias_nuevos=[
                    OrdenEstacionDiaNuevoIn(
                        fecha_transmision=otra_fecha, hora_inicio=time(9, 0), spots=80
                    )
                ],
            ),
            VENTAS,
        )


def test_avanzar_reales_dia_nuevo_ya_existe_mismo_fecha_hora_400(
    db: Session, oe_svc: OrdenEstacionService, oe
) -> None:
    with pytest.raises(DomainError):
        oe_svc.avanzar_reales(
            oe.orden_estacion_id,
            OrdenEstacionRealesIn(
                dias=[],
                dias_nuevos=[
                    OrdenEstacionDiaNuevoIn(
                        fecha_transmision=_DIA_1, hora_inicio=time(7, 0), spots=5
                    )
                ],
            ),
            VENTAS,
        )


def test_http_avanzar_reales_con_dias_nuevos(
    client: TestClient, db: Session, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    otra_fecha = (_DIA_1 + timedelta(days=10)).isoformat()  # dentro de la campaña

    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/reales",
        json={
            "dias": [],
            "dias_nuevos": [
                {"fecha_transmision": otra_fecha, "hora_inicio": "09:00:00", "spots": 6}
            ],
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200, r.text

    r2 = client.get(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/dias", headers=_hdr("ventas")
    )
    assert r2.status_code == 200
    fechas_horas = {(d["fecha_transmision"], d["hora_inicio"]) for d in r2.json()}
    assert (otra_fecha, "09:00:00") in fechas_horas
