"""Pruebas F1-07 · "Material a Transmitir" (ADR-103): audios de OrdenEstacion.

Cubre: lista blanca de audio (`EXTENSIONES_AUDIO_ORDENES`) a nivel de `leer_adjunto`,
las reglas de negocio del servicio (`agregar_audio`/`eliminar_audio`/`asignar_audio_dia`
— orden por defecto, renumeración al borrar, override por día) y los endpoints HTTP
completos (subir/listar/descargar/borrar + RBAC), con `AlmacenamientoLocal` en
`tmp_path` (sin red ni credenciales), mismo patrón que `test_ordenes_adjuntos.py`.
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import DomainError, NotFoundError, register_error_handlers
from app.core.security import Area, CurrentUser
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.documentos import (
    EXTENSIONES_AUDIO_ORDENES,
    ArchivoNoPermitidoError,
    leer_adjunto,
)
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import Incidencia  # noqa: F401 — registra la tabla
from app.modules.ordenes.orden_cliente import (
    OrdenCliente,
    OrdenClienteCreate,
    OrdenClienteRepository,
    OrdenClienteService,
)
from app.modules.ordenes.orden_estacion import (
    OrdenEstacion,
    OrdenEstacionAudioStagedIn,
    OrdenEstacionCreate,
    OrdenEstacionDia,
    OrdenEstacionDiaAudioIn,
    OrdenEstacionDiaCreate,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.router import router as ordenes_router
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")

MP3_BYTES = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 40
WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 20
OGG_BYTES = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00" + b"\x00" * 20


class _ArchivoFalso:
    def __init__(self, filename: str, contenido: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(contenido)


# ══════════════════════════════════════════════════════════════════════════════════
# leer_adjunto contra la lista blanca de audio
# ══════════════════════════════════════════════════════════════════════════════════
def test_leer_adjunto_acepta_mp3_wav_ogg() -> None:
    for nombre, contenido in [("a.mp3", MP3_BYTES), ("b.wav", WAV_BYTES), ("c.ogg", OGG_BYTES)]:
        contenido_leido, nombre_sano, extension = leer_adjunto(
            _ArchivoFalso(nombre, contenido),
            max_bytes=1024,
            extensiones_permitidas=EXTENSIONES_AUDIO_ORDENES,
        )
        assert contenido_leido == contenido
        assert nombre_sano.endswith(f".{extension}")


def test_leer_adjunto_rechaza_pdf_para_audio() -> None:
    with pytest.raises(ArchivoNoPermitidoError):
        leer_adjunto(
            _ArchivoFalso("a.pdf", b"%PDF-1.7"),
            max_bytes=1024,
            extensiones_permitidas=EXTENSIONES_AUDIO_ORDENES,
        )


def test_extensiones_audio_no_incluyen_m4a_ni_ejecutables() -> None:
    assert set(EXTENSIONES_AUDIO_ORDENES) == {"mp3", "wav", "ogg"}
    assert "m4a" not in EXTENSIONES_AUDIO_ORDENES
    assert "exe" not in EXTENSIONES_AUDIO_ORDENES


# ══════════════════════════════════════════════════════════════════════════════════
# Fixtures (mismo patrón que test_f1_06_ordenes_pdf.py)
# ══════════════════════════════════════════════════════════════════════════════════
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
            nombre_estacion="XHLE-FM",
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


def _oc_payload(cat: dict[str, uuid.UUID], **overrides: object) -> OrdenClienteCreate:
    base: dict[str, object] = dict(
        numero_orden_cliente="PO-BIMBO-0419",
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
        ],
    )
    base.update(overrides)
    return OrdenEstacionCreate(**base)


# ══════════════════════════════════════════════════════════════════════════════════
# ADR-109: material sembrado en create() (subido a S3 ANTES de que exista la OE,
# vía /ordenes/material-staging)
# ══════════════════════════════════════════════════════════════════════════════════
def test_create_con_audios_sembrados_crea_las_filas_en_orden(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            audios=[
                OrdenEstacionAudioStagedIn(
                    ref="orden_estacion/audios/abc_uno.mp3", nombre_archivo="uno.mp3"
                ),
                OrdenEstacionAudioStagedIn(
                    ref="orden_estacion/audios/def_dos.wav", nombre_archivo="dos.wav"
                ),
            ],
        ),
        VENTAS,
    )

    audios = oe_svc.audios(oe.orden_estacion_id)
    assert [a.nombre_archivo for a in audios] == ["uno.mp3", "dos.wav"]
    assert [a.orden for a in audios] == [0, 1]
    # `ref` (clave S3) es interno — no lo expone `OrdenEstacionAudioRead` (mismo criterio
    # que el resto de adjuntos, ADR-042); se confirma contra el modelo crudo.
    crudo = oe_svc.obtener_audio(oe.orden_estacion_id, audios[0].orden_estacion_audio_id)
    assert crudo.ref == "orden_estacion/audios/abc_uno.mp3"


def test_create_sin_audios_no_crea_ninguna_fila(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """El campo es opcional (`default_factory=list`) — una OE sin material sembrado
    (el caso de siempre, y el de editar) sigue funcionando exactamente igual."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    assert oe_svc.audios(oe.orden_estacion_id) == []


def test_create_con_audios_sembrados_y_luego_agregar_mas_continua_el_orden(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    """El endpoint dedicado de siempre (`agregar_audio`) sigue funcionando después de
    sembrar audios en create() — sin duplicar orden=0, continúa desde el máximo real."""
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            audios=[
                OrdenEstacionAudioStagedIn(
                    ref="orden_estacion/audios/abc_uno.mp3", nombre_archivo="uno.mp3"
                )
            ],
        ),
        VENTAS,
    )
    nuevo = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("tres.mp3", MP3_BYTES), VENTAS, almacenamiento
    )
    assert nuevo.orden == 1


# ══════════════════════════════════════════════════════════════════════════════════
# ADR-111: elegir un audio NO default por día, ya en el alta (antes de tener
# `orden_estacion_dia_id` real) — "Sustitución de Material" también disponible en create.
# ══════════════════════════════════════════════════════════════════════════════════
def test_create_con_audio_staging_ref_asigna_el_audio_correcto_por_dia(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            audios=[
                OrdenEstacionAudioStagedIn(
                    ref="orden_estacion/audios/abc_uno.mp3", nombre_archivo="uno.mp3"
                ),
                OrdenEstacionAudioStagedIn(
                    ref="orden_estacion/audios/def_dos.wav", nombre_archivo="dos.wav"
                ),
            ],
            dias=[
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=32),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=5,
                    # Sin `audio_staging_ref`: se queda con el default (uno.mp3).
                ),
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=33),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=5,
                    audio_staging_ref="orden_estacion/audios/def_dos.wav",
                ),
            ],
        ),
        VENTAS,
    )

    audios = {
        a.nombre_archivo: a.orden_estacion_audio_id for a in oe_svc.audios(oe.orden_estacion_id)
    }
    dias = oe_svc._repo.listar_dias(oe.orden_estacion_id)
    dias_por_fecha = {d.fecha_transmision: d for d in dias}
    assert dias_por_fecha[date.today() + timedelta(days=32)].orden_estacion_audio_id is None
    assert (
        dias_por_fecha[date.today() + timedelta(days=33)].orden_estacion_audio_id
        == audios["dos.wav"]
    )


def test_create_con_audio_staging_ref_invalido_falla(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    with pytest.raises(DomainError):
        oe_svc.create(
            _oe_payload(
                cat,
                oc.orden_id,
                audios=[
                    OrdenEstacionAudioStagedIn(
                        ref="orden_estacion/audios/abc_uno.mp3", nombre_archivo="uno.mp3"
                    )
                ],
                dias=[
                    OrdenEstacionDiaCreate(
                        fecha_transmision=date.today() + timedelta(days=32),
                        hora_inicio=time(7, 0),
                        hora_fin=time(9, 0),
                        spots_asignados=5,
                        audio_staging_ref="orden_estacion/audios/no-existe.mp3",
                    ),
                ],
            ),
            VENTAS,
        )


# ══════════════════════════════════════════════════════════════════════════════════
# Servicio: orden por defecto, renumeración al borrar, override por día
# ══════════════════════════════════════════════════════════════════════════════════
def test_agregar_audio_asigna_orden_incremental(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    primero = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("cancion.mp3", MP3_BYTES), VENTAS, almacenamiento
    )
    segundo = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("otra.wav", WAV_BYTES), VENTAS, almacenamiento
    )
    assert primero.orden == 0
    assert segundo.orden == 1

    audios = oe_svc.audios(oe.orden_estacion_id)
    assert [a.nombre_archivo for a in audios] == ["cancion.mp3", "otra.wav"]


def test_eliminar_audio_default_promueve_al_siguiente_y_limpia_overrides(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    a0 = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("uno.mp3", MP3_BYTES), VENTAS, almacenamiento
    )
    a1 = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("dos.wav", WAV_BYTES), VENTAS, almacenamiento
    )
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    # El día se asigna EXPLICITAMENTE al segundo audio (no al default) antes de borrar el primero.
    oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=a1.orden_estacion_audio_id),
        VENTAS,
    )

    oe_svc.eliminar_audio(oe.orden_estacion_id, a0.orden_estacion_audio_id, VENTAS)

    restantes = oe_svc.audios(oe.orden_estacion_id)
    assert len(restantes) == 1
    assert restantes[0].orden_estacion_audio_id == a1.orden_estacion_audio_id
    assert restantes[0].orden == 0  # renumerado: pasa a ser el nuevo default

    # El día seguía apuntando a a1 (no al que se borró) — no se tocó.
    dia_actualizado = db.get(OrdenEstacionDia, dia.orden_estacion_dia_id)
    assert dia_actualizado is not None
    assert dia_actualizado.orden_estacion_audio_id == a1.orden_estacion_audio_id


def test_eliminar_audio_referenciado_por_dia_lo_deja_en_default(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    a0 = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("uno.mp3", MP3_BYTES), VENTAS, almacenamiento
    )
    oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("dos.wav", WAV_BYTES), VENTAS, almacenamiento
    )
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=a0.orden_estacion_audio_id),
        VENTAS,
    )

    oe_svc.eliminar_audio(oe.orden_estacion_id, a0.orden_estacion_audio_id, VENTAS)

    dia_actualizado = db.get(OrdenEstacionDia, dia.orden_estacion_dia_id)
    assert dia_actualizado is not None
    assert dia_actualizado.orden_estacion_audio_id is None  # vuelve al default


def test_asignar_audio_dia_de_otra_oe_404(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe1 = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe2 = oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            dias=[
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=33),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=10,
                )
            ],
        ),
        VENTAS,
    )
    audio_de_oe1 = oe_svc.agregar_audio(
        oe1.orden_estacion_id, _ArchivoFalso("uno.mp3", MP3_BYTES), VENTAS, almacenamiento
    )
    dia_de_oe2 = oe_svc.dias(oe2.orden_estacion_id)[0]

    with pytest.raises(NotFoundError):
        oe_svc.asignar_audio_dia(
            oe2.orden_estacion_id,
            dia_de_oe2.orden_estacion_dia_id,
            OrdenEstacionDiaAudioIn(orden_estacion_audio_id=audio_de_oe1.orden_estacion_audio_id),
            VENTAS,
        )


# ══════════════════════════════════════════════════════════════════════════════════
# HTTP: subir / listar / descargar / borrar + RBAC
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


def _crear_oc_oe_http(client: TestClient, cat: dict[str, uuid.UUID]) -> str:
    r = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "PO-HTTP-AUDIO",
            "fecha_venta": str(date.today()),
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": str(date.today() + timedelta(days=1)),
            "fecha_fin_campania": str(date.today() + timedelta(days=30)),
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    orden_id = r.json()["orden_id"]

    r = client.post(
        "/api/v1/ordenes/estaciones",
        json={
            "orden_id": orden_id,
            "estacion_id": str(cat["estacion"]),
            "producto_tarifa": "spot",
            "duracion_spot": "30s",
            "precio_spot": "800.00",
            "dias": [
                {
                    "fecha_transmision": str(date.today() + timedelta(days=2)),
                    "hora_inicio": "07:00:00",
                    "hora_fin": "09:00:00",
                    "spots_asignados": 5,
                }
            ],
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    return r.json()["orden_estacion_id"]


def test_http_subir_listar_descargar_borrar_audio(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    oe_id = _crear_oc_oe_http(client, cat)

    files = {"archivo": ("spot.mp3", MP3_BYTES, "audio/mpeg")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 201, r.text
    audio = r.json()
    assert audio["nombre_archivo"] == "spot.mp3"
    assert audio["orden"] == 0

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/audios", headers=_hdr("ventas"))
    assert r.status_code == 200
    assert len(r.json()) == 1

    audio_id = audio["orden_estacion_audio_id"]
    r = client.get(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios/{audio_id}/archivo", headers=_hdr("ventas")
    )
    assert r.status_code == 200
    assert r.content == MP3_BYTES
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["content-disposition"] == 'attachment; filename="spot.mp3"'

    r = client.delete(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios/{audio_id}", headers=_hdr("ventas")
    )
    assert r.status_code == 204

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/audios", headers=_hdr("ventas"))
    assert r.json() == []


def test_http_rbac_nominas_no_puede_subir_audio(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    oe_id = _crear_oc_oe_http(client, cat)
    files = {"archivo": ("spot.mp3", MP3_BYTES, "audio/mpeg")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios", files=files, headers=_hdr("nominas")
    )
    assert r.status_code == 403


def test_http_subir_formato_no_permitido_400(client: TestClient, cat: dict[str, uuid.UUID]) -> None:
    oe_id = _crear_oc_oe_http(client, cat)
    files = {"archivo": ("documento.pdf", b"%PDF-1.7", "application/pdf")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_permitido"


def test_http_asignar_audio_a_dia_puntual(client: TestClient, cat: dict[str, uuid.UUID]) -> None:
    oe_id = _crear_oc_oe_http(client, cat)
    files = {"archivo": ("spot.mp3", MP3_BYTES, "audio/mpeg")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/audios", files=files, headers=_hdr("ventas")
    )
    audio_id = r.json()["orden_estacion_audio_id"]

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/dias", headers=_hdr("ventas"))
    dia_id = r.json()[0]["orden_estacion_dia_id"]

    r = client.put(
        f"/api/v1/ordenes/estaciones/{oe_id}/dias/{dia_id}/audio",
        json={"orden_estacion_audio_id": audio_id},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["orden_estacion_audio_id"] == audio_id

    # Quitar el override (null) regresa el día al default.
    r = client.put(
        f"/api/v1/ordenes/estaciones/{oe_id}/dias/{dia_id}/audio",
        json={"orden_estacion_audio_id": None},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200
    assert r.json()["orden_estacion_audio_id"] is None


# ══════════════════════════════════════════════════════════════════════════════════
# ADR-109 HTTP: /ordenes/material-staging (subir ANTES de que exista la OE) + create()
# con audios sembrados
# ══════════════════════════════════════════════════════════════════════════════════
def test_http_material_staging_sube_sin_ningun_id_de_padre(client: TestClient) -> None:
    """El endpoint no pide `orden_id`/`orden_estacion_id` en absoluto — se puede llamar
    ANTES de que exista ninguna orden."""
    files = {"archivo": ("spot.mp3", MP3_BYTES, "audio/mpeg")}
    r = client.post(
        "/api/v1/ordenes/material-staging?tipo=audio", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["nombre_archivo"] == "spot.mp3"
    assert body["ref"].startswith("orden_estacion/audios/")


def test_http_material_staging_rechaza_formato_no_permitido(client: TestClient) -> None:
    files = {"archivo": ("documento.pdf", b"%PDF-1.7", "application/pdf")}
    r = client.post(
        "/api/v1/ordenes/material-staging?tipo=audio", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_permitido"


def test_http_crear_oe_con_material_staging_previo(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    """Flujo completo: subir el material ANTES de crear la OE (sin ningún id todavía),
    luego crear la OE mandando esos refs en `audios` — deben quedar como material real,
    consultable por el endpoint normal de audios de esa OE."""
    subida = client.post(
        "/api/v1/ordenes/material-staging?tipo=audio",
        files={"archivo": ("spot.mp3", MP3_BYTES, "audio/mpeg")},
        headers=_hdr("ventas"),
    ).json()

    r = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "PO-STAGING",
            "fecha_venta": str(date.today()),
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": str(date.today() + timedelta(days=1)),
            "fecha_fin_campania": str(date.today() + timedelta(days=30)),
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    orden_id = r.json()["orden_id"]

    r = client.post(
        "/api/v1/ordenes/estaciones",
        json={
            "orden_id": orden_id,
            "estacion_id": str(cat["estacion"]),
            "producto_tarifa": "spot",
            "duracion_spot": "30s",
            "precio_spot": "800.00",
            "dias": [
                {
                    "fecha_transmision": str(date.today() + timedelta(days=2)),
                    "hora_inicio": "07:00:00",
                    "hora_fin": "09:00:00",
                    "spots_asignados": 5,
                }
            ],
            "audios": [{"ref": subida["ref"], "nombre_archivo": subida["nombre_archivo"]}],
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    oe_id = r.json()["orden_estacion_id"]

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/audios", headers=_hdr("ventas"))
    assert r.status_code == 200
    audios = r.json()
    assert len(audios) == 1
    assert audios[0]["nombre_archivo"] == "spot.mp3"
    assert audios[0]["orden"] == 0
