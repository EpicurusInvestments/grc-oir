"""Pruebas F4-02 — Dashboard comercial (módulo `reportes`, solo lectura).

Como en F4-01, se inserta directamente vía ORM (SQLite en memoria) el estado que el
`ReportesService` debe agregar — se valida SOLO la lógica nueva: exclusión de
`cancelada`, el corte de vendedor secundario (comisión suma ambos roles, "Ventas" solo
cuenta al principal), "Trato directo" (agencia_id NULL), ventanas ytd/mes/trimestre y
RBAC del endpoint.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.cuenta_contable import CuentaContable  # noqa: F401 — registra la tabla
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.orden_cliente import OrdenCliente
from app.modules.ordenes.orden_estacion import OrdenEstacion  # noqa: F401 — registra la tabla
from app.modules.reportes.repository import ReportesRepository
from app.modules.reportes.router import router as reportes_router
from app.modules.reportes.service import ReportesService
from app.modules.usuarios.models import Usuario

ADMIN_ID = uuid.uuid4()
_Q2 = Decimal("0.01")


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
    db.add(
        Usuario(usuario_id=ADMIN_ID, nombre_usuario="tester", email="t@grcoir.com", area="admin")
    )
    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
    vendedor_1_id, vendedor_2_id = uuid.uuid4(), uuid.uuid4()
    anunciante_1_id, anunciante_2_id = uuid.uuid4(), uuid.uuid4()
    agencia_1_id, categoria_1_id = uuid.uuid4(), uuid.uuid4()

    db.add(Vendedor(vendedor_id=vendedor_1_id, nombre_vendedor="Vendedor Uno"))
    db.add(Vendedor(vendedor_id=vendedor_2_id, nombre_vendedor="Vendedor Dos"))
    db.add(
        Anunciante(
            anunciante_id=anunciante_1_id,
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
            rfc_anunciante="ANU900101AB1",
            dias_credito_default=30,
        )
    )
    db.add(
        Anunciante(
            anunciante_id=anunciante_2_id,
            nombre_comercial="Anunciante Dos",
            nombre_fiscal="Anunciante Dos SA de CV",
            rfc_anunciante="AND900101AB1",
            dias_credito_default=30,
        )
    )
    db.add(
        Agencia(
            agencia_id=agencia_1_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("10.00"),
        )
    )
    db.add(Categoria(categoria_id=categoria_1_id, nombre_categoria="Automotriz"))
    db.commit()
    return {
        "empresa_id": empresa_id,
        "vendedor_1": vendedor_1_id,
        "vendedor_2": vendedor_2_id,
        "anunciante_1": anunciante_1_id,
        "anunciante_2": anunciante_2_id,
        "agencia_1": agencia_1_id,
        "categoria_1": categoria_1_id,
    }


def _orden(
    db: Session,
    cat: dict[str, uuid.UUID],
    *,
    folio: str,
    fecha_venta: date,
    total: Decimal,
    vendedor_principal: str = "vendedor_1",
    vendedor_secundario: str | None = None,
    pct_principal: Decimal = Decimal("10.00"),
    pct_secundario: Decimal | None = None,
    anunciante: str = "anunciante_1",
    agencia: str | None = None,
    categoria: str | None = None,
    estatus: str = "orden_cerrada",
) -> uuid.UUID:
    subtotal = (total / Decimal("1.16")).quantize(_Q2)
    iva = (total - subtotal).quantize(_Q2)
    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden=folio,
            numero_orden_cliente=f"NUM-{folio}",
            fecha_venta=fecha_venta,
            anio_venta=fecha_venta.year,
            mes_venta=fecha_venta.month,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat[vendedor_principal],
            vendedor_secundario_id=cat[vendedor_secundario] if vendedor_secundario else None,
            porcentaje_comision_vendedor_principal_snap=pct_principal,
            porcentaje_comision_vendedor_secundario_snap=pct_secundario,
            anunciante_id=cat[anunciante],
            agencia_id=cat[agencia] if agencia else None,
            porcentaje_comision_agencia_snap=Decimal("10.00") if agencia else None,
            categoria_id=cat[categoria] if categoria else None,
            fecha_inicio_campania=fecha_venta,
            fecha_fin_campania=fecha_venta,
            total_dias_campania=1,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=subtotal,
            iva=iva,
            total=total,
            estatus_orden=estatus,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return orden_id


def _svc(db: Session) -> ReportesService:
    return ReportesService(ReportesRepository(db))


def test_ventas_excluyen_canceladas(db: Session, cat: dict[str, uuid.UUID]) -> None:
    _orden(db, cat, folio="OC-1", fecha_venta=date(2026, 11, 5), total=Decimal("1000.00"))
    _orden(
        db, cat, folio="OC-2", fecha_venta=date(2026, 11, 10), total=Decimal("500.00"),
        estatus="cancelada",
    )
    db.commit()

    r = _svc(db).dashboard_comercial("mes", "2026-11")
    assert r.ventas_total == Decimal("1000.00")
    assert r.ordenes_total == 1


def test_comision_vendedor_secundario_suma_pero_no_duplica_ventas(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Corrección del usuario: el vendedor secundario es "un vendedor más" — su
    comisión se suma a SU fila, pero las ventas de la orden solo cuentan una vez (al
    principal)."""
    _orden(
        db, cat, folio="OC-1", fecha_venta=date(2026, 11, 5), total=Decimal("1000.00"),
        vendedor_principal="vendedor_1", vendedor_secundario="vendedor_2",
        pct_principal=Decimal("10.00"), pct_secundario=Decimal("5.00"),
    )
    db.commit()

    r = _svc(db).dashboard_comercial("mes", "2026-11")
    assert r.ventas_total == Decimal("1000.00")  # una sola vez, no 2000

    por_vendedor = {v.nombre: v for v in r.top_vendedores}
    assert por_vendedor["Vendedor Uno"].ventas == Decimal("1000.00")
    assert por_vendedor["Vendedor Uno"].ordenes == 1
    assert por_vendedor["Vendedor Uno"].comision_total == Decimal("100.00")  # 1000*10%
    # El secundario NO suma ventas ni "órdenes" propias, pero SÍ su comisión.
    assert por_vendedor["Vendedor Dos"].ventas == Decimal("0")
    assert por_vendedor["Vendedor Dos"].ordenes == 0
    assert por_vendedor["Vendedor Dos"].comision_total == Decimal("50.00")  # 1000*5%


def test_vendedor_secundario_en_una_orden_principal_en_otra_se_suma_una_sola_fila(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _orden(
        db, cat, folio="OC-1", fecha_venta=date(2026, 11, 1), total=Decimal("1000.00"),
        vendedor_principal="vendedor_1", pct_principal=Decimal("10.00"),
    )
    _orden(
        db, cat, folio="OC-2", fecha_venta=date(2026, 11, 2), total=Decimal("2000.00"),
        vendedor_principal="vendedor_2", vendedor_secundario="vendedor_1",
        pct_principal=Decimal("10.00"), pct_secundario=Decimal("5.00"),
    )
    db.commit()

    r = _svc(db).dashboard_comercial("mes", "2026-11")
    por_vendedor = {v.nombre: v for v in r.top_vendedores}
    # Vendedor Uno: ventas como principal (1000) + comisión como principal (100) +
    # comisión como secundario en la otra orden (100) — UNA sola fila, no dos.
    assert por_vendedor["Vendedor Uno"].ventas == Decimal("1000.00")
    assert por_vendedor["Vendedor Uno"].comision_total == Decimal("200.00")


def test_categoria_nula_se_agrupa_como_sin_categoria(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _orden(
        db, cat, folio="OC-1", fecha_venta=date(2026, 11, 1), total=Decimal("1000.00"),
        categoria="categoria_1",
    )
    _orden(db, cat, folio="OC-2", fecha_venta=date(2026, 11, 2), total=Decimal("500.00"))
    db.commit()

    r = _svc(db).dashboard_comercial("mes", "2026-11")
    nombres = {c.nombre for c in r.top_categorias}
    assert "Automotriz" in nombres
    assert "Sin categoría" in nombres


def test_agencia_nula_es_trato_directo_sin_comision(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _orden(
        db, cat, folio="OC-1", fecha_venta=date(2026, 11, 1), total=Decimal("1000.00"),
        agencia="agencia_1",
    )
    _orden(db, cat, folio="OC-2", fecha_venta=date(2026, 11, 2), total=Decimal("500.00"))
    db.commit()

    r = _svc(db).dashboard_comercial("mes", "2026-11")
    por_agencia = {a.nombre: a for a in r.top_agencias}
    assert "Trato directo" in por_agencia
    assert por_agencia["Trato directo"].comision == Decimal("0")
    assert por_agencia["Trato directo"].comision_pct is None
    assert por_agencia["Agencia Uno"].comision == Decimal("100.00")  # 1000*10%


def test_ventana_trimestre_cubre_los_3_meses(db: Session, cat: dict[str, uuid.UUID]) -> None:
    _orden(db, cat, folio="OC-OCT", fecha_venta=date(2026, 10, 15), total=Decimal("100.00"))
    _orden(db, cat, folio="OC-NOV", fecha_venta=date(2026, 11, 15), total=Decimal("200.00"))
    _orden(db, cat, folio="OC-DIC", fecha_venta=date(2026, 12, 15), total=Decimal("300.00"))
    _orden(db, cat, folio="OC-SEP", fecha_venta=date(2026, 9, 30), total=Decimal("9999.00"))
    db.commit()

    r = _svc(db).dashboard_comercial("trimestre", "2026-11")  # Q4: oct-dic
    assert r.ventas_total == Decimal("600.00")
    assert r.desde == "2026-10-01"
    assert r.hasta == "2027-01-01"


def test_ventana_ytd_desde_enero(db: Session, cat: dict[str, uuid.UUID]) -> None:
    _orden(db, cat, folio="OC-ENE", fecha_venta=date(2026, 1, 15), total=Decimal("100.00"))
    _orden(db, cat, folio="OC-NOV", fecha_venta=date(2026, 11, 15), total=Decimal("200.00"))
    _orden(db, cat, folio="OC-DIC", fecha_venta=date(2026, 12, 15), total=Decimal("300.00"))
    db.commit()

    r = _svc(db).dashboard_comercial("ytd", "2026-11")
    assert r.ventas_total == Decimal("300.00")  # ene+nov, no dic (después del corte)
    assert r.desde == "2026-01-01"


# ── RBAC del endpoint ────────────────────────────────────────────────────────────
@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.core import config

    monkeypatch.setattr(config.settings, "auth_provider", "dev_headers")
    monkeypatch.setattr(config.settings, "app_env", "development")

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(reportes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_rbac_reportes_comercial(client: TestClient) -> None:
    ruta = "/api/v1/reportes/comercial"
    assert client.get(ruta, headers=_hdr("nominas")).status_code == 403
    assert client.get(ruta, headers=_hdr("ventas")).status_code == 200
    assert client.get(ruta, headers=_hdr("direccion")).status_code == 200
    assert client.get(ruta, headers=_hdr("admin")).status_code == 200


def test_ventana_invalida_422(client: TestClient) -> None:
    r = client.get(
        "/api/v1/reportes/comercial", params={"ventana": "semana"}, headers=_hdr("direccion")
    )
    assert r.status_code == 422


def test_exportar_comercial_xlsx_y_csv_ok(client: TestClient) -> None:
    for formato in ("xlsx", "csv"):
        r = client.get(
            "/api/v1/reportes/comercial/exportar",
            params={"formato": formato},
            headers=_hdr("direccion"),
        )
        assert r.status_code == 200, r.text
