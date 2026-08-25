"""Siembra de datos de desarrollo (F1 — Órdenes) contra SQLite local.

Reproduce los datos de `frontend/src/modules/ordenes/mocks/*.ts`: los catálogos que F1
consume, las 10 OrdenCliente (una por estado), sus OrdenEstacion con periodo por día, las
Verificacion y las Incidencia. El ESQUEMA no sale de aquí (sale de la spec — Tanda 1); esto
solo son los VALORES.

No es una migración (nunca usa Alembic/`op.*`): es un script Python normal, **idempotente**
(usa `Session.merge()` sobre IDs deterministas — mismo mock, misma corrida, mismo resultado)
y re-ejecutable sin duplicar filas.

Uso (desde `backend/`, con la SQLite local ya migrada — ver Tanda 1):
    $env:DATABASE_URL = "sqlite:///./dev_ordenes.db"          # PowerShell
    .venv\\Scripts\\python.exe -m scripts.seed_dev

Para empezar de cero (la SQLite de dev es desechable por diseño — ADR-028):
    rm dev_ordenes.db
    alembic upgrade head
    python -m scripts.seed_dev

Al final imprime un reporte de hallazgos: campos de los mocks que NO caben en el modelo
real (inventados aquí con un valor razonable, marcados explícitamente) y las decisiones de
mapeo de vocabulario (v5 del prototipo → spec) aplicadas a cada registro.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from app.core.audit import LogCambioParametro
from app.core.config import settings
from app.core.db import get_engine, get_sessionmaker, url_enmascarada
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.constantes_sistema import ConstanteSistema
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.tarifa import TarifaPlaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.facturacion.costo_adicional import CostoAdicional
from app.modules.facturacion.factura_afiliado import FacturaAfiliado, FacturaAfiliadoOrden
from app.modules.facturacion.factura_agencia import FacturaAgencia
from app.modules.facturacion.factura_cliente import FacturaCliente
from app.modules.ordenes.incidencia import Incidencia
from app.modules.ordenes.orden_cliente import ITEMS_VOBO, OrdenCliente, OrdenClienteVoBoItem
from app.modules.ordenes.orden_estacion import OrdenEstacion, OrdenEstacionDia
from app.modules.ordenes.verificacion import Verificacion
from app.modules.usuarios.models import Usuario
from sqlalchemy.orm import Session

IVA_RATE = Decimal(str(settings.iva_rate))
#: Dinero cuantizado a centavos (igual que los servicios de F1/F2).
CENTAVOS = Decimal("0.01")

# Mismo UUID que siembra la migración F0-04 (`_SEED_ADMIN_ID`) — se reutiliza, no se duplica.
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Namespace propio para IDs DETERMINISTAS (mismo mock → mismo UUID siempre → idempotente).
_NS = uuid.UUID("6f3a7d2e-2a3b-4b60-9b0a-f1a1f10ce001")


def uid(clave: str) -> uuid.UUID:
    """UUID determinista a partir de la clave del mock (p.ej. 'anunciante:an1',
    'orden_cliente:oc3') — trazable y estable entre corridas."""
    return uuid.uuid5(_NS, clave)


# Hallazgos acumulados durante la siembra (mock → real no calza) — se imprimen al final.
HALLAZGOS: list[str] = []


def hallazgo(msg: str) -> None:
    if msg not in HALLAZGOS:
        HALLAZGOS.append(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# Usuarios de demo — NINGUNO: el único usuario en todos los entornos es `dev.admin`
# (sembrado por la migración F0-04, `_SEED_ADMIN_ID` = `ADMIN_ID` aquí). Antes existían
# personas de demo adicionales (`victor.garcia`, `ana.torres`) solo en SQLite — eso
# rompía en cuanto se probaba contra RDS, donde nunca se sembraron. Se unificó a un
# único usuario en ambos entornos para eliminar esa discrepancia de raíz.
# ═══════════════════════════════════════════════════════════════════════════════
USUARIOS_DEMO: list[dict[str, Any]] = []


def seed_usuarios(db: Session) -> dict[str, uuid.UUID]:
    ids = {"dev.admin": ADMIN_ID}
    for u in USUARIOS_DEMO:
        uid_ = uid(f"usuario:{u['clave']}")
        db.merge(
            Usuario(
                usuario_id=uid_,
                nombre_usuario=u["nombre_usuario"],
                email=u["email"],
                area=u["area"],
                roles_adicionales=u["roles_adicionales"],
                activo=True,
                created_at=datetime(2026, 1, 1),
            )
        )
        ids[u["clave"]] = uid_
    return ids


# ═══════════════════════════════════════════════════════════════════════════════
# Catálogos (mismos datos que frontend/src/modules/ordenes/mocks/catalogos.ts)
# ═══════════════════════════════════════════════════════════════════════════════
AGENCIAS = [
    ("ag1", "Mindshare México", "MME050610EF7", "15"),
    ("ag2", "OMD México", "OMD120815GH9", "15"),
    ("ag3", "Initiative", "INI081205AB7", "12.5"),
    ("ag4", "PHD México", "PHD140322KM2", "13"),
]

CATEGORIAS = [
    ("cat1", "Automotriz"),
    ("cat2", "Alimentos y bebidas"),
    ("cat3", "Retail"),
    ("cat4", "Telecomunicaciones"),
    ("cat5", "Farmacéutica"),
    ("cat6", "Servicios financieros"),
]

# (clave, agencia_clave|None, nombre_comercial, nombre_fiscal, rfc, dias_credito, categoria_clave)
ANUNCIANTES = [
    (
        "an1",
        "ag1",
        "Televisa Publicidad",
        "Televisa Publicidad SA de CV",
        "TPU900101XX1",
        30,
        "cat4",
    ),
    ("an2", "ag2", "Grupo Bimbo", "Bimbo SA de CV", "GBI971120AB3", 60, "cat2"),
    ("an3", "ag1", "OXXO", "Cadena Comercial OXXO SA de CV", "OCO030401CD5", 45, "cat3"),
    ("an4", "ag4", "Soriana", "Organización Soriana SAB de CV", "SOR930201IJ2", 45, "cat3"),
    ("an5", None, "Grupo Modelo", "Cervecería Modelo SA de CV", "CMO920510KL3", 30, "cat2"),
    ("an6", "ag3", "Telcel", "Radiomóvil Dipsa SA de CV", "RDI840315MN6", 30, "cat4"),
]

MARCAS = [
    ("mc1", "an1", "Televisa Deportes"),
    ("mc2", "an1", "Televisa Novelas"),
    ("mc3", "an2", "Pan Bimbo"),
    ("mc4", "an2", "Marinela"),
    ("mc5", "an3", "OXXO Tiendas"),
    ("mc6", "an3", "OXXO Gas"),
    ("mc7", "an4", "Soriana Híper"),
    ("mc8", "an4", "Soriana Mercado"),
    ("mc9", "an5", "Corona Extra"),
    ("mc10", "an5", "Modelo Especial"),
    ("mc11", "an6", "Telcel Plan Amigo"),
    ("mc12", "an6", "Telcel Empresarial"),
]

# (clave, anunciante_clave, numero, nombre, estado_contrato, fecha_inicio, fecha_fin)
# fecha_inicio/fin: el mock NO trae estos 2 campos (req. en el modelo real) — se INVENTAN
# como el año calendario que ya indica el propio número de contrato (ver hallazgo).
CONTRATOS = [
    (
        "co1",
        "an1",
        "CT-2025-001",
        "Campaña Verano 2025",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
    (
        "co1b",
        "an1",
        "CT-2024-098",
        "Anual 2024 (cerrado)",
        "finalizado",
        date(2024, 1, 1),
        date(2024, 12, 31),
    ),
    (
        "co2",
        "an2",
        "CT-2025-002",
        "Anual 2025 - Grupo Bimbo",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
    (
        "co3",
        "an3",
        "CT-2025-003",
        "Anual OXXO 2025",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
    (
        "co4",
        "an4",
        "CT-2025-004",
        "Soriana Verano 2025",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
    (
        "co5",
        "an5",
        "CT-2025-005",
        "Modelo Temporada 2025",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
    (
        "co6",
        "an6",
        "CT-2025-006",
        "Telcel Anual 2025",
        "vigente",
        date(2025, 1, 1),
        date(2025, 12, 31),
    ),
]

VENDEDORES = [
    ("ve1", "Renata Aguilar", "5"),
    ("ve2", "Roberto López", "4"),
    ("ve3", "Patricia Méndez", "4.5"),
    ("ve4", "Eduardo Castro", "3.5"),
    ("ve5", "Jorge Nava", "4"),
]

# El mock trae "razon_social_empresa"; el modelo real es "direccion_empresa" (campo
# distinto, no un renombre) — no hay dato del mock que calce ahí (ver hallazgo).
EMPRESAS_FACTURADORAS = [
    ("ef1", "OIR Comercial", "OCO900101AB1"),
    ("ef2", "GRC Servicios", "GRC050610CD3"),
    ("ef3", "OIR Digital", "OMD110215EF4"),
]

PLAZAS = [
    ("pl1", "CDMX", "Ciudad de México"),
    ("pl2", "Monterrey", "Nuevo León"),
    ("pl3", "Guadalajara", "Jalisco"),
    ("pl4", "León", "Guanajuato"),
    ("pl5", "Puebla", "Puebla"),
]

# El mock no trae razon_social_afiliado ni rfc_afiliado (req. + único en el modelo real) —
# se INVENTAN a partir del nombre (ver hallazgo).
AFILIADOS = [
    (
        "af1",
        "Multimedios Estrellas de Oro",
        "pl2",
        "Multimedios Estrellas de Oro SA de CV",
        "MEO900101AB1",
    ),
    ("af2", "OIR Bajío", "pl4", "OIR Bajío SA de CV", "OBA900101AB2"),
    ("af3", "Grupo Radio Centro", "pl1", "Grupo Radio Centro SA de CV", "GRC900101AB3"),
    ("af4", "Radiorama Jalisco", "pl3", "Radiorama Jalisco SA de CV", "RJA900101AB4"),
]

ESTACIONES = [
    ("es1", "af1", "pl2", "XHMT-FM", "90.1 FM", "fm"),
    ("es2", "af1", "pl2", "XHMA-AM", "1080 AM", "am"),
    ("es3", "af2", "pl4", "XHLE-FM", "97.7 FM", "fm"),
    ("es4", "af2", "pl4", "XHLE-TV", "Canal 4", "tv"),
    ("es5", "af3", "pl1", "XEQR-AM", "1030 AM", "am"),
    ("es6", "af3", "pl1", "XHRC-FM", "100.9 FM", "fm"),
    ("es7", "af4", "pl3", "XHGDL-FM", "95.5 FM", "fm"),
    ("es8", "af4", "pl3", "XHGDL-AM", "790 AM", "am"),
]

TARIFAS = [
    ("ta1", "pl1", "fm", "30s", "9500", "10"),
    ("ta2", "pl1", "am", "30s", "5000", "5"),
    ("ta3", "pl2", "fm", "30s", "8500", "10"),
    ("ta4", "pl2", "am", "30s", "4800", "0"),
    ("ta5", "pl3", "fm", "30s", "7800", "8"),
    ("ta6", "pl3", "am", "30s", "4200", "0"),
    ("ta7", "pl4", "fm", "30s", "7000", "5"),
    ("ta8", "pl4", "tv", "30s", "15000", "0"),
]


def seed_catalogos(db: Session) -> dict[str, dict[str, uuid.UUID]]:
    """Siembra los catálogos de F0 que F1 referencia. Regresa un mapa
    {tipo: {clave_mock: uuid_real}} para resolver las FK de las órdenes."""
    ids: dict[str, dict[str, uuid.UUID]] = {
        "agencia": {},
        "categoria": {},
        "anunciante": {},
        "marca": {},
        "contrato": {},
        "vendedor": {},
        "empresa_facturadora": {},
        "plaza": {},
        "afiliado": {},
        "estacion": {},
        "tarifa": {},
    }

    for clave, nombre, rfc, pct in AGENCIAS:
        u = uid(f"agencia:{clave}")
        db.merge(
            Agencia(
                agencia_id=u,
                nombre_agencia=nombre,
                rfc_agencia=rfc,
                porcentaje_comision_agencia_default=Decimal(pct),
            )
        )
        ids["agencia"][clave] = u

    for clave, nombre in CATEGORIAS:
        u = uid(f"categoria:{clave}")
        db.merge(Categoria(categoria_id=u, nombre_categoria=nombre))
        ids["categoria"][clave] = u

    for clave, ag_clave, nom_com, nom_fiscal, rfc, dias, _cat_clave in ANUNCIANTES:
        u = uid(f"anunciante:{clave}")
        db.merge(
            Anunciante(
                anunciante_id=u,
                agencia_id=ids["agencia"][ag_clave] if ag_clave else None,
                nombre_comercial=nom_com,
                nombre_fiscal=nom_fiscal,
                rfc_anunciante=rfc,
                dias_credito_default=dias,
            )
        )
        ids["anunciante"][clave] = u
    # nota: categoria_id no vive en Anunciante (es OrdenCliente.categoria_id, per-venta);
    # el mock la trae en AnuncianteRef como atajo de la demo — no se pierde, se aplica al
    # sembrar cada OrdenCliente con la categoría de su propio anunciante.

    for clave, an_clave, nombre in MARCAS:
        u = uid(f"marca:{clave}")
        db.merge(Marca(marca_id=u, anunciante_id=ids["anunciante"][an_clave], nombre_marca=nombre))
        ids["marca"][clave] = u

    hallazgo(
        "Contrato: el mock no trae fecha_inicio_contrato/fecha_fin_contrato (NOT NULL en "
        "el modelo real) — se sembraron como el año calendario que ya sugiere el número de "
        "contrato (p.ej. CT-2025-001 → 2025-01-01..2025-12-31)."
    )
    for clave, an_clave, numero, nombre, estado, f_ini, f_fin in CONTRATOS:
        u = uid(f"contrato:{clave}")
        db.merge(
            Contrato(
                contrato_id=u,
                anunciante_id=ids["anunciante"][an_clave],
                numero_contrato=numero,
                nombre_contrato=nombre,
                fecha_inicio_contrato=f_ini,
                fecha_fin_contrato=f_fin,
                estado_contrato=estado,
                created_by="dev.admin",
            )
        )
        ids["contrato"][clave] = u

    for clave, nombre, pct in VENDEDORES:
        u = uid(f"vendedor:{clave}")
        db.merge(
            Vendedor(
                vendedor_id=u, nombre_vendedor=nombre, porcentaje_comision_default=Decimal(pct)
            )
        )
        ids["vendedor"][clave] = u

    hallazgo(
        "EmpresaFacturadora: el mock trae 'razon_social_empresa', el modelo real tiene "
        "'direccion_empresa' (campo distinto, no un renombre) — no hay dato del mock que "
        "calce ahí; se sembró direccion_empresa=NULL."
    )
    for clave, nombre, rfc in EMPRESAS_FACTURADORAS:
        u = uid(f"empresa_facturadora:{clave}")
        db.merge(
            EmpresaFacturadora(empresa_facturadora_id=u, nombre_empresa=nombre, rfc_empresa=rfc)
        )
        ids["empresa_facturadora"][clave] = u

    for clave, nombre, estado in PLAZAS:
        u = uid(f"plaza:{clave}")
        db.merge(Plaza(plaza_id=u, nombre_plaza=nombre, estado=estado))
        ids["plaza"][clave] = u

    hallazgo(
        "Afiliado: el mock no trae razon_social_afiliado ni rfc_afiliado (NOT NULL + "
        "único en el modelo real) — se inventaron a partir del nombre. Tampoco existe "
        "'porcentaje_participacion_oir_default' en el modelo real de Afiliado (la spec no "
        "lo tiene): el % de participación OIR de cada OrdenEstacion se sembró tal cual lo "
        "trae el mock de la orden, no derivado de un default de catálogo inexistente."
    )
    for clave, nombre, plaza_clave, razon_social, rfc in AFILIADOS:
        u = uid(f"afiliado:{clave}")
        db.merge(
            Afiliado(
                afiliado_id=u,
                nombre_afiliado=nombre,
                razon_social_afiliado=razon_social,
                rfc_afiliado=rfc,
                plaza_id=ids["plaza"][plaza_clave],
            )
        )
        ids["afiliado"][clave] = u

    for clave, af_clave, plaza_clave, nombre, frecuencia, tipo_senal in ESTACIONES:
        u = uid(f"estacion:{clave}")
        db.merge(
            Estacion(
                estacion_id=u,
                afiliado_id=ids["afiliado"][af_clave],
                plaza_id=ids["plaza"][plaza_clave],  # ADR-005: igual al de su afiliado
                nombre_estacion=nombre,
                frecuencia=frecuencia,
                tipo_senal=tipo_senal,
            )
        )
        ids["estacion"][clave] = u

    for clave, plaza_clave, tipo_senal, duracion, bruta, descuento in TARIFAS:
        u = uid(f"tarifa:{clave}")
        bruta_d, descuento_d = Decimal(bruta), Decimal(descuento)
        neta = (bruta_d * (Decimal(100) - descuento_d) / Decimal(100)).quantize(Decimal("0.01"))
        db.merge(
            TarifaPlaza(
                tarifa_plaza_id=u,
                plaza_id=ids["plaza"][plaza_clave],
                tipo_senal=tipo_senal,
                duracion_spot=duracion,
                tarifa_bruta=bruta_d,
                descuento_pct=descuento_d,
                tarifa_neta=neta,
                vigencia_desde=date(2025, 1, 1),
                vigencia_hasta=date(2025, 12, 31),
                created_by="dev.admin",
            )
        )
        ids["tarifa"][clave] = u

    return ids


# ═══════════════════════════════════════════════════════════════════════════════
# Mapeo de vocabulario: "v5" del prototipo/demo → spec BD v2 (decisiones #2/#3 aprobadas)
# ═══════════════════════════════════════════════════════════════════════════════
# OrdenCliente.estatus_orden: los que no dependen del estado de sus OE mapean directo.
# "orden_interna" (v5) se resuelve aparte, según el estado de sus OE (ver resolver_estatus_oc).
MAPEO_ESTATUS_OC = {
    "orden_cliente_sin_vobo": "recibida",
    "orden_cliente_con_vobo": "capturada",
    "orden_cerrada": "orden_cerrada",
    # facturada_archivo_plano y facturada_timbrada (4.1/4.2 del prototipo) colapsan en el
    # único valor "facturada" de la spec — la spec no distingue archivo plano de timbrada
    # (eso es detalle de F2, fuera de alcance; lo confirmó el equipo).
    "facturada_archivo_plano": "facturada",
    "facturada_timbrada": "facturada",
    "cobrada": "cobrada",
    "cancelada": "cancelada",
}

# OrdenEstacion.estatus (spec, 6 valores) — la demo solo usa 3 sub-estados (2.1/2.2/2.3),
# ciclo de vida PROPIO de la OE, independiente del de la OC (confirmado con la spec):
#   2.1 asignada_afiliado     → "asignada"       (spec: "programada con afiliado")
#   2.2 programados_conciliados → "en_transmision" (spec: horario confirmado, en curso)
#   2.3 reales_conciliados    → "cerrada"        ("conciliados" = ajustados y listos para
#                                                  facturación, que es justo la definición
#                                                  de "cerrada" en la spec)
MAPEO_ESTATUS_OE = {
    "asignada_afiliado": "asignada",
    "programados_conciliados": "en_transmision",
    "reales_conciliados": "cerrada",
}


def resolver_estatus_oc(estatus_v5: str, estatus_oes_de_la_oc: list[str]) -> str:
    """`orden_interna` (v5) no tiene un valor 1:1 en la spec: se resuelve según el estado
    de sus OE — en_transmision si alguna sigue en 2.1/2.2, en_verificacion si TODAS ya
    llegaron a 2.3 (decisión aprobada explícitamente)."""
    if estatus_v5 != "orden_interna":
        return MAPEO_ESTATUS_OC[estatus_v5]
    if all(e == "reales_conciliados" for e in estatus_oes_de_la_oc):
        return "en_verificacion"
    return "en_transmision"


# ═══════════════════════════════════════════════════════════════════════════════
# OrdenCliente (10, una por estado — mismos datos que mocks/ordenesCliente.ts)
# ═══════════════════════════════════════════════════════════════════════════════
def _totales(total_spots: int, precio_unitario: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = (Decimal(total_spots) * precio_unitario).quantize(Decimal("0.01"))
    iva = (subtotal * IVA_RATE).quantize(Decimal("0.01"))
    return subtotal, iva, subtotal + iva


def _dias_campania(inicio: date, fin: date) -> int:
    return (fin - inicio).days + 1


OC_MOCKS: list[dict[str, Any]] = [
    dict(
        clave="oc1",
        folio="OC-2025-0041",
        numero="SOR-VER-25",
        fecha_venta=date(2025, 6, 20),
        empresa="ef1",
        vp="ve4",
        vs=None,
        anunciante="an4",
        agencia="ag4",
        contrato="co4",
        marca="mc7",
        producto="Soriana Híper - Campaña de verano",
        categoria="cat3",
        direccion="Monterrey, NL · Av. Lázaro Cárdenas 2225",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 7, 1),
        f_fin=date(2025, 7, 31),
        total_spots=80,
        precio_unitario=Decimal("10500"),
        comision_vp=Decimal("3.5"),
        comision_vs=None,
        comision_ag=Decimal("13"),
        obs_libres="Aún en revisión comercial, pendiente de Vo.Bo.",
        checklist={"razon_social", "plaza", "emisora", "duracion"},
        estatus_v5="orden_cliente_sin_vobo",
        created_by="ve4",
    ),
    dict(
        clave="oc2",
        folio="OC-2025-0042",
        numero="MOD-CDMX-CA",
        fecha_venta=date(2025, 6, 25),
        empresa="ef1",
        vp="ve1",
        vs=None,
        anunciante="an5",
        agencia=None,
        contrato="co5",
        marca="mc9",
        producto="Corona Extra - Verano playero",
        categoria="cat2",
        direccion="CDMX, Javier Barros Sierra 555",
        fact_directa=True,
        af_directo=False,
        f_ini=date(2025, 7, 15),
        f_fin=date(2025, 8, 31),
        total_spots=60,
        precio_unitario=Decimal("11000"),
        comision_vp=Decimal("5"),
        comision_vs=None,
        comision_ag=None,
        obs_libres="Venta directa, cliente prioritario. Con Vo.Bo., lista para asignar estaciones.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="orden_cliente_con_vobo",
        created_by="ve1",
    ),
    dict(
        clave="oc3",
        folio="OC-2025-0043",
        numero="TVPUB-CV-2025",
        fecha_venta=date(2025, 5, 15),
        empresa="ef1",
        vp="ve2",
        vs="ve3",
        anunciante="an1",
        agencia="ag1",
        contrato="co1",
        marca="mc1",
        producto="Televisa Deportes - Final Liga MX",
        categoria="cat4",
        direccion="CDMX, Vasco de Quiroga 2000",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 5, 20),
        f_fin=date(2025, 6, 20),
        total_spots=150,
        precio_unitario=Decimal("13300"),
        comision_vp=Decimal("4.5"),
        comision_vs=Decimal("4.5"),
        comision_ag=Decimal("15"),
        obs_libres="Final Liga MX. Spots prime obligatorios. En proceso de asignación a "
        "estaciones.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="orden_interna",
        created_by="ve2",
    ),
    dict(
        clave="oc4",
        folio="OC-2025-0044",
        numero="OXXO-JUN-014",
        fecha_venta=date(2025, 6, 5),
        empresa="ef1",
        vp="ve3",
        vs=None,
        anunciante="an3",
        agencia="ag1",
        contrato="co3",
        marca="mc5",
        producto="OXXO Tiendas - Promo mensual",
        categoria="cat3",
        direccion="Monterrey, NL · Av. Lázaro Cárdenas 2225",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 6, 10),
        f_fin=date(2025, 7, 10),
        total_spots=100,
        precio_unitario=Decimal("10900"),
        comision_vp=Decimal("4.5"),
        comision_vs=None,
        comision_ag=Decimal("15"),
        obs_libres="Recién asignadas 2 estaciones, faltan 20 spots por repartir.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="orden_interna",
        created_by="ve3",
    ),
    dict(
        clave="oc5",
        folio="OC-2025-0045",
        numero="BIM-MAR-15",
        fecha_venta=date(2025, 4, 10),
        empresa="ef1",
        vp="ve2",
        vs=None,
        anunciante="an2",
        agencia="ag2",
        contrato="co2",
        marca="mc4",
        producto="Marinela Pingüinos - Lanzamiento",
        categoria="cat2",
        direccion="CDMX, Reforma 1000",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 4, 15),
        f_fin=date(2025, 5, 15),
        total_spots=120,
        precio_unitario=Decimal("11900"),
        comision_vp=Decimal("4"),
        comision_vs=None,
        comision_ag=Decimal("15"),
        obs_libres="Todas sus órdenes internas ya están en 2.3 — lista para cerrar.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="orden_interna",
        created_by="ve2",
    ),
    dict(
        clave="oc6",
        folio="OC-2025-0046",
        numero="BIM-PAN-08",
        fecha_venta=date(2025, 2, 20),
        empresa="ef1",
        vp="ve2",
        vs=None,
        anunciante="an2",
        agencia="ag2",
        contrato="co2",
        marca="mc3",
        producto="Pan Bimbo Integral 680g",
        categoria="cat2",
        direccion="CDMX, Reforma 1000",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 3, 1),
        f_fin=date(2025, 3, 31),
        total_spots=90,
        precio_unitario=Decimal("11900"),
        comision_vp=Decimal("4"),
        comision_vs=None,
        comision_ag=Decimal("15"),
        obs_libres="Cerrada sin la ODC cerrada firmada; se registró como faltante.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="orden_cerrada",
        created_by="ve2",
        odc_cerrada_ref=None,
        carta_conciliacion_ref="Carta_Conciliacion_OC-2025-0046.pdf",
        cierre_sin_odc=True,
        cierre_sin_carta=False,
        fecha_cierre=date(2025, 4, 5),
    ),
    dict(
        clave="oc7",
        folio="OC-2025-0047",
        numero="TEL-ENE-2025",
        fecha_venta=date(2025, 1, 20),
        empresa="ef3",
        vp="ve5",
        vs=None,
        anunciante="an6",
        agencia="ag3",
        contrato="co6",
        marca="mc11",
        producto="Telcel Plan Amigo - Recarga fácil",
        categoria="cat4",
        direccion="CDMX, Lago Zurich 245",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 2, 1),
        f_fin=date(2025, 2, 28),
        total_spots=100,
        precio_unitario=Decimal("10500"),
        comision_vp=Decimal("4.5"),
        comision_vs=None,
        comision_ag=Decimal("12.5"),
        obs_libres="Archivo plano generado, pendiente de recibir folio fiscal del timbrador.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="facturada_archivo_plano",
        created_by="ve5",
        odc_cerrada_ref="ODC_Cerrada_OC-2025-0047.pdf",
        carta_conciliacion_ref="Carta_Conciliacion_OC-2025-0047.pdf",
        cierre_sin_odc=False,
        cierre_sin_carta=False,
        fecha_cierre=date(2025, 3, 5),
    ),
    dict(
        clave="oc8",
        folio="OC-2025-0048",
        numero="SOR-ENE-002",
        fecha_venta=date(2024, 12, 15),
        empresa="ef1",
        vp="ve4",
        vs=None,
        anunciante="an4",
        agencia="ag4",
        contrato="co4",
        marca="mc8",
        producto="Soriana Mercado - Quincena",
        categoria="cat3",
        direccion="Monterrey, NL · Av. Lázaro Cárdenas 2225",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2025, 1, 10),
        f_fin=date(2025, 2, 9),
        total_spots=80,
        precio_unitario=Decimal("9800"),
        comision_vp=Decimal("3.5"),
        comision_vs=None,
        comision_ag=Decimal("13"),
        obs_libres="CFDI timbrado y cargado. Pendiente de cobranza.",
        checklist=set(ITEMS_VOBO),
        estatus_v5="facturada_timbrada",
        created_by="ve4",
        estatus_pago_afiliado="pagado",
        odc_cerrada_ref="ODC_Cerrada_OC-2025-0048.pdf",
        carta_conciliacion_ref="Carta_Conciliacion_OC-2025-0048.pdf",
        cierre_sin_odc=False,
        cierre_sin_carta=False,
        fecha_cierre=date(2025, 2, 15),
    ),
    dict(
        clave="oc9",
        folio="OC-2025-0049",
        numero="TVPUB-NOV-2024",
        fecha_venta=date(2024, 11, 10),
        empresa="ef1",
        vp="ve2",
        vs="ve3",
        anunciante="an1",
        agencia="ag1",
        contrato="co1",
        marca="mc2",
        producto="Televisa Novelas - Estreno de temporada",
        categoria="cat4",
        direccion="CDMX, Vasco de Quiroga 2000",
        fact_directa=False,
        af_directo=False,
        f_ini=date(2024, 12, 1),
        f_fin=date(2024, 12, 31),
        total_spots=110,
        precio_unitario=Decimal("12500"),
        comision_vp=Decimal("4"),
        comision_vs=Decimal("4.5"),
        comision_ag=Decimal("13.5"),
        obs_libres="Ciclo completo: cobrada. % de agencia renegociado tras el cierre "
        "(ver historial).",
        checklist=set(ITEMS_VOBO),
        estatus_v5="cobrada",
        created_by="ve2",
        estatus_pago_afiliado="pagado",
        estatus_pago_agencia="pagado",
        odc_cerrada_ref="ODC_Cerrada_OC-2025-0049.pdf",
        carta_conciliacion_ref="Carta_Conciliacion_OC-2025-0049.pdf",
        cierre_sin_odc=False,
        cierre_sin_carta=False,
        fecha_cierre=date(2025, 1, 5),
    ),
    dict(
        clave="oc10",
        folio="OC-2025-0050",
        numero="MOD-CANC-09",
        fecha_venta=date(2025, 7, 1),
        empresa="ef1",
        vp="ve1",
        vs=None,
        anunciante="an5",
        agencia=None,
        contrato="co5",
        marca="mc10",
        producto="Modelo Especial - Fin de año",
        categoria="cat2",
        direccion="CDMX, Javier Barros Sierra 555",
        fact_directa=True,
        af_directo=False,
        f_ini=date(2025, 9, 1),
        f_fin=date(2025, 9, 30),
        total_spots=50,
        precio_unitario=Decimal("9000"),
        comision_vp=Decimal("5"),
        comision_vs=None,
        comision_ag=None,
        obs_libres="Cliente canceló la campaña por cambio de estrategia de marca, "
        "antes de asignar estaciones.",
        checklist={"razon_social", "plaza"},
        estatus_v5="cancelada",
        created_by="ve1",
    ),
]

# OE agrupadas por OC (clave) — para resolver_estatus_oc necesitamos saber, para cada OC,
# el estatus (v5) de todas sus OE ANTES de sembrarlas (se define junto con OE_MOCKS abajo).
ESTATUS_OE_POR_OC: dict[str, list[str]] = {
    "oc3": ["asignada_afiliado", "programados_conciliados", "reales_conciliados"],
    "oc4": ["asignada_afiliado", "asignada_afiliado"],
    "oc5": ["reales_conciliados", "reales_conciliados", "reales_conciliados"],
    "oc6": ["reales_conciliados", "reales_conciliados", "reales_conciliados"],
    "oc7": ["reales_conciliados", "reales_conciliados"],
    "oc8": ["reales_conciliados", "reales_conciliados"],
    "oc9": ["reales_conciliados", "reales_conciliados", "reales_conciliados"],
}


def seed_ordenes_cliente(db: Session, cat: dict[str, dict[str, uuid.UUID]]) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for oc in OC_MOCKS:
        u = uid(f"orden_cliente:{oc['clave']}")
        subtotal, iva, total = _totales(oc["total_spots"], oc["precio_unitario"])
        estatus = resolver_estatus_oc(oc["estatus_v5"], ESTATUS_OE_POR_OC.get(oc["clave"], []))
        # created_by del mock es un VENDEDOR (ve1..ve5), no un Usuario real — no hay 1:1
        # entre vendedores y cuentas de usuario en la spec; se atribuye a dev.admin (ver
        # hallazgo). El vendedor real de la venta sigue viviendo en vendedor_principal_id.
        db.merge(
            OrdenCliente(
                orden_id=u,
                folio_orden=oc["folio"],
                numero_orden_cliente=oc["numero"],
                fecha_venta=oc["fecha_venta"],
                anio_venta=oc["fecha_venta"].year,
                mes_venta=oc["fecha_venta"].month,
                empresa_facturadora_id=cat["empresa_facturadora"][oc["empresa"]],
                vendedor_principal_id=cat["vendedor"][oc["vp"]],
                vendedor_secundario_id=cat["vendedor"][oc["vs"]] if oc["vs"] else None,
                anunciante_id=cat["anunciante"][oc["anunciante"]],
                agencia_id=cat["agencia"][oc["agencia"]] if oc["agencia"] else None,
                contrato_id=cat["contrato"][oc["contrato"]] if oc["contrato"] else None,
                marca_id=cat["marca"][oc["marca"]] if oc["marca"] else None,
                categoria_id=cat["categoria"][oc["categoria"]] if oc["categoria"] else None,
                producto=oc["producto"],
                direccion_facturacion=oc["direccion"],
                facturacion_directa_cliente=oc["fact_directa"],
                afiliado_factura_directo_al_cliente=oc["af_directo"],
                fecha_inicio_campania=oc["f_ini"],
                fecha_fin_campania=oc["f_fin"],
                total_dias_campania=_dias_campania(oc["f_ini"], oc["f_fin"]),
                duracion_spot="30s",
                precio_unitario=oc["precio_unitario"],
                total_spots=oc["total_spots"],
                subtotal=subtotal,
                iva=iva,
                total=total,
                observaciones_libres=oc["obs_libres"],
                estatus_orden=estatus,
                estatus_pago_afiliado=oc.get("estatus_pago_afiliado", "pendiente"),
                estatus_pago_agencia=oc.get("estatus_pago_agencia", "pendiente"),
                created_by=ADMIN_ID,
                porcentaje_comision_vendedor_principal_snap=oc["comision_vp"],
                porcentaje_comision_vendedor_secundario_snap=oc["comision_vs"],
                porcentaje_comision_agencia_snap=oc["comision_ag"],
                odc_cerrada_ref=oc.get("odc_cerrada_ref"),
                carta_conciliacion_ref=oc.get("carta_conciliacion_ref"),
                cierre_sin_odc_cerrada=oc.get("cierre_sin_odc", False),
                cierre_sin_carta_conciliacion=oc.get("cierre_sin_carta", False),
                fecha_cierre=oc.get("fecha_cierre"),
            )
        )
        ids[oc["clave"]] = u

        for item in ITEMS_VOBO:
            completado = item in oc["checklist"]
            db.merge(
                OrdenClienteVoBoItem(
                    orden_cliente_vobo_item_id=uid(f"vobo:{oc['clave']}:{item}"),
                    orden_id=u,
                    item_clave=item,
                    completado=completado,
                    usuario_id=ADMIN_ID if completado else None,
                    fecha_completado=datetime.combine(oc["fecha_venta"], time(9, 0))
                    if completado
                    else None,
                )
            )
    hallazgo(
        "OrdenCliente.created_by: los mocks traen el ID de un VENDEDOR (ve1..ve5) como "
        "'creador', pero el modelo real exige un Usuario válido y no hay relación 1:1 "
        "vendedor↔usuario en la spec. Se atribuyeron todas las OC sembradas a dev.admin; "
        "el vendedor real de cada venta sigue en vendedor_principal_id, que sí es correcto."
    )
    return ids


# ═══════════════════════════════════════════════════════════════════════════════
# OrdenEstacion + OrdenEstacionDia (mismos datos que mocks/ordenesEstacion.ts)
# ═══════════════════════════════════════════════════════════════════════════════
# (clave, oc_clave, estacion_clave, precio_spot, pct_oir, estatus_v5,
#  periodo=[(fecha, hora_ini, hora_fin, spots), ...],
#  prog_override={fecha: spots}, real_override={fecha: spots}, observaciones)
OE_MOCKS: list[dict[str, Any]] = [
    dict(
        clave="oe1",
        oc="oc3",
        estacion="es5",
        precio_spot="9000",
        pct_oir="32.3",
        estatus_v5="asignada_afiliado",
        periodo=[
            (date(2025, 5, 22), time(7, 0), time(9, 0), 10),
            (date(2025, 5, 23), time(7, 0), time(9, 0), 10),
            (date(2025, 5, 29), time(7, 0), time(9, 0), 10),
            (date(2025, 6, 5), time(7, 0), time(9, 0), 10),
            (date(2025, 6, 12), time(7, 0), time(9, 0), 10),
            (date(2025, 6, 19), time(7, 0), time(9, 0), 10),
        ],
    ),
    dict(
        clave="oe2",
        oc="oc3",
        estacion="es6",
        precio_spot="9500",
        pct_oir="28.6",
        estatus_v5="programados_conciliados",
        periodo=[
            (date(2025, 5, 21), time(18, 0), time(20, 0), 10),
            (date(2025, 5, 28), time(18, 0), time(20, 0), 10),
            (date(2025, 6, 4), time(18, 0), time(20, 0), 10),
            (date(2025, 6, 11), time(18, 0), time(20, 0), 10),
            (date(2025, 6, 18), time(18, 0), time(20, 0), 10),
        ],
        prog_override={date(2025, 6, 11): 12},
    ),
    dict(
        clave="oe3",
        oc="oc3",
        estacion="es1",
        precio_spot="8500",
        pct_oir="36.1",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 5, 25), time(12, 0), time(14, 0), 12),
            (date(2025, 6, 1), time(12, 0), time(14, 0), 11),
            (date(2025, 6, 8), time(12, 0), time(14, 0), 11),
            (date(2025, 6, 15), time(12, 0), time(14, 0), 11),
        ],
        real_override={date(2025, 6, 15): 9},
        obs="2 spots no transmitidos por corte de programación.",
    ),
    dict(
        clave="oe4",
        oc="oc4",
        estacion="es1",
        precio_spot="7800",
        pct_oir="28.4",
        estatus_v5="asignada_afiliado",
        periodo=[
            (date(2025, 6, 12), time(9, 0), time(11, 0), 10),
            (date(2025, 6, 19), time(9, 0), time(11, 0), 10),
            (date(2025, 6, 26), time(9, 0), time(11, 0), 10),
            (date(2025, 7, 3), time(9, 0), time(11, 0), 10),
        ],
    ),
    dict(
        clave="oe5",
        oc="oc4",
        estacion="es3",
        precio_spot="7000",
        pct_oir="35.8",
        estatus_v5="asignada_afiliado",
        periodo=[
            (date(2025, 6, 13), time(8, 0), time(10, 0), 10),
            (date(2025, 6, 20), time(8, 0), time(10, 0), 10),
            (date(2025, 6, 27), time(8, 0), time(10, 0), 10),
            (date(2025, 7, 4), time(8, 0), time(10, 0), 10),
        ],
    ),
    dict(
        clave="oe6",
        oc="oc5",
        estacion="es2",
        precio_spot="6000",
        pct_oir="49.6",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 4, 17), time(12, 0), time(14, 0), 10),
            (date(2025, 4, 24), time(12, 0), time(14, 0), 10),
            (date(2025, 5, 1), time(12, 0), time(14, 0), 10),
            (date(2025, 5, 8), time(12, 0), time(14, 0), 10),
            (date(2025, 5, 14), time(12, 0), time(14, 0), 10),
        ],
    ),
    dict(
        clave="oe7",
        oc="oc5",
        estacion="es7",
        precio_spot="7800",
        pct_oir="34.5",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 4, 18), time(7, 0), time(9, 0), 10),
            (date(2025, 4, 25), time(7, 0), time(9, 0), 10),
            (date(2025, 5, 2), time(7, 0), time(9, 0), 10),
            (date(2025, 5, 9), time(7, 0), time(9, 0), 10),
        ],
        real_override={date(2025, 5, 9): 13},
        obs="Afiliado bonificó 3 spots adicionales por tema técnico.",
    ),
    dict(
        clave="oe8",
        oc="oc5",
        estacion="es8",
        precio_spot="4200",
        pct_oir="64.7",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 4, 20), time(15, 0), time(17, 0), 15),
            (date(2025, 5, 4), time(15, 0), time(17, 0), 15),
        ],
    ),
    dict(
        clave="oe9",
        oc="oc6",
        estacion="es5",
        precio_spot="9200",
        pct_oir="22.7",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 3, 3), time(7, 0), time(9, 0), 10),
            (date(2025, 3, 10), time(7, 0), time(9, 0), 10),
            (date(2025, 3, 17), time(7, 0), time(9, 0), 10),
            (date(2025, 3, 24), time(7, 0), time(9, 0), 10),
        ],
    ),
    dict(
        clave="oe10",
        oc="oc6",
        estacion="es6",
        precio_spot="9500",
        pct_oir="20.2",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 3, 4), time(18, 0), time(20, 0), 10),
            (date(2025, 3, 11), time(18, 0), time(20, 0), 10),
            (date(2025, 3, 18), time(18, 0), time(20, 0), 10),
        ],
        real_override={date(2025, 3, 18): 8},
        obs="Spots transmitidos fuera del horario prime acordado.",
    ),
    dict(
        clave="oe11",
        oc="oc6",
        estacion="es2",
        precio_spot="6200",
        pct_oir="47.9",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 3, 5), time(12, 0), time(14, 0), 10),
            (date(2025, 3, 12), time(12, 0), time(14, 0), 10),
        ],
    ),
    dict(
        clave="oe12",
        oc="oc7",
        estacion="es7",
        precio_spot="6800",
        pct_oir="35.2",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 2, 3), time(7, 0), time(9, 0), 15),
            (date(2025, 2, 10), time(7, 0), time(9, 0), 15),
            (date(2025, 2, 17), time(7, 0), time(9, 0), 15),
            (date(2025, 2, 24), time(7, 0), time(9, 0), 15),
        ],
    ),
    dict(
        clave="oe13",
        oc="oc7",
        estacion="es8",
        precio_spot="4300",
        pct_oir="59.0",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 2, 4), time(10, 0), time(12, 0), 10),
            (date(2025, 2, 11), time(10, 0), time(12, 0), 10),
            (date(2025, 2, 18), time(10, 0), time(12, 0), 10),
            (date(2025, 2, 25), time(10, 0), time(12, 0), 10),
        ],
    ),
    dict(
        clave="oe14",
        oc="oc8",
        estacion="es1",
        precio_spot="7300",
        pct_oir="25.5",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 1, 12), time(9, 0), time(11, 0), 15),
            (date(2025, 1, 19), time(9, 0), time(11, 0), 15),
            (date(2025, 1, 26), time(9, 0), time(11, 0), 15),
            (date(2025, 2, 2), time(9, 0), time(11, 0), 15),
        ],
    ),
    dict(
        clave="oe15",
        oc="oc8",
        estacion="es3",
        precio_spot="6900",
        pct_oir="29.6",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2025, 1, 13), time(8, 0), time(10, 0), 10),
            (date(2025, 1, 27), time(8, 0), time(10, 0), 10),
        ],
    ),
    dict(
        clave="oe16",
        oc="oc9",
        estacion="es5",
        precio_spot="9600",
        pct_oir="23.2",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2024, 12, 2), time(7, 0), time(9, 0), 15),
            (date(2024, 12, 9), time(7, 0), time(9, 0), 15),
            (date(2024, 12, 16), time(7, 0), time(9, 0), 10),
        ],
    ),
    dict(
        clave="oe17",
        oc="oc9",
        estacion="es6",
        precio_spot="9800",
        pct_oir="21.6",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2024, 12, 3), time(18, 0), time(20, 0), 15),
            (date(2024, 12, 10), time(18, 0), time(20, 0), 15),
            (date(2024, 12, 17), time(18, 0), time(20, 0), 10),
        ],
    ),
    dict(
        clave="oe18",
        oc="oc9",
        estacion="es1",
        precio_spot="8600",
        pct_oir="31.2",
        estatus_v5="reales_conciliados",
        periodo=[
            (date(2024, 12, 4), time(12, 0), time(14, 0), 10),
            (date(2024, 12, 11), time(12, 0), time(14, 0), 10),
            (date(2024, 12, 18), time(12, 0), time(14, 0), 10),
        ],
    ),
]

# Folio de cada OE — mismo prefijo/numeración que el frontend YA usa tras el ajuste
# folio OE- (spec), no OI- (prototipo) — ver decisión de la Tanda 1.
FOLIO_OE = {
    "oe1": "OE-2025-0043A",
    "oe2": "OE-2025-0043B",
    "oe3": "OE-2025-0043C",
    "oe4": "OE-2025-0044A",
    "oe5": "OE-2025-0044B",
    "oe6": "OE-2025-0045A",
    "oe7": "OE-2025-0045B",
    "oe8": "OE-2025-0045C",
    "oe9": "OE-2025-0046A",
    "oe10": "OE-2025-0046B",
    "oe11": "OE-2025-0046C",
    "oe12": "OE-2025-0047A",
    "oe13": "OE-2025-0047B",
    "oe14": "OE-2025-0048A",
    "oe15": "OE-2025-0048B",
    "oe16": "OE-2025-0049A",
    "oe17": "OE-2025-0049B",
    "oe18": "OE-2025-0049C",
}


def seed_ordenes_estacion(
    db: Session, cat: dict[str, dict[str, uuid.UUID]], oc_ids: dict[str, uuid.UUID]
) -> dict[str, uuid.UUID]:
    hallazgo(
        "OrdenEstacion.vendedor_id: los mocks no traen un vendedor propio por OE (el "
        "campo no existe en `OrdenEstacion` del frontend) — se sembró igual al "
        "vendedor_principal_id de su OrdenCliente (la spec permite que difiera, pero el "
        "mock no da un dato distinto para hacerlo)."
    )
    ids: dict[str, uuid.UUID] = {}
    for oe in OE_MOCKS:
        u = uid(f"orden_estacion:{oe['clave']}")
        oc_mock = next(o for o in OC_MOCKS if o["clave"] == oe["oc"])
        estacion_clave = oe["estacion"]
        # plaza_id heredada de la Estacion (ADR-005) — resuelta contra el propio mock de
        # catálogos, no inventada aquí.
        plaza_clave = next(e[2] for e in ESTACIONES if e[0] == estacion_clave)

        precio_spot = Decimal(oe["precio_spot"])
        pct_oir = Decimal(oe["pct_oir"])
        total_asignado = sum(dia[3] for dia in oe["periodo"])
        importe_estacion = (Decimal(total_asignado) * precio_spot).quantize(Decimal("0.01"))
        importe_oir = (importe_estacion * pct_oir / Decimal(100)).quantize(Decimal("0.01"))
        iva_oir = (importe_oir * IVA_RATE).quantize(Decimal("0.01"))
        importe_emisora = importe_estacion - importe_oir
        iva_emisora = (importe_emisora * IVA_RATE).quantize(Decimal("0.01"))

        estatus_oe = MAPEO_ESTATUS_OE[oe["estatus_v5"]]
        ya_programado = oe["estatus_v5"] in ("programados_conciliados", "reales_conciliados")

        db.merge(
            OrdenEstacion(
                orden_estacion_id=u,
                folio_orden_estacion=FOLIO_OE[oe["clave"]],
                orden_id=oc_ids[oe["oc"]],
                contrato_id=cat["contrato"][oc_mock["contrato"]] if oc_mock["contrato"] else None,
                anunciante_id=cat["anunciante"][oc_mock["anunciante"]],
                vendedor_id=cat["vendedor"][oc_mock["vp"]],
                agencia_id=cat["agencia"][oc_mock["agencia"]] if oc_mock["agencia"] else None,
                categoria_id=cat["categoria"][oc_mock["categoria"]]
                if oc_mock["categoria"]
                else None,
                producto=oc_mock["producto"],
                estacion_id=cat["estacion"][estacion_clave],
                plaza_id=cat["plaza"][plaza_clave],
                duracion_spot="30s",
                precio_spot=precio_spot,
                importe_estacion=importe_estacion,
                porcentaje_participacion_oir=pct_oir,
                importe_oir=importe_oir,
                iva_oir=iva_oir,
                total_oir=importe_oir + iva_oir,
                importe_emisora=importe_emisora,
                iva_emisora=iva_emisora,
                total_emisora=importe_emisora + iva_emisora,
                estatus=estatus_oe,
                observaciones_estacion=oe.get("obs"),
                created_by=ADMIN_ID,
            )
        )
        ids[oe["clave"]] = u

        prog_over = oe.get("prog_override", {})
        for fecha, hora_ini, hora_fin, spots in oe["periodo"]:
            dia_id = uid(f"orden_estacion_dia:{oe['clave']}:{fecha.isoformat()}")
            spots_programados = None
            if ya_programado:
                spots_programados = prog_over.get(fecha, spots)
            db.merge(
                OrdenEstacionDia(
                    orden_estacion_dia_id=dia_id,
                    orden_estacion_id=u,
                    fecha_transmision=fecha,
                    hora_inicio=hora_ini,
                    hora_fin=hora_fin,
                    # El mock no distingue "solicitado" de "asignado" por día (un solo
                    # número); se sembró solicitados = asignados (sin faltantes) — ver
                    # hallazgo consolidado al final.
                    spots_solicitados=spots,
                    spots_asignados=spots,
                    spots_programados=spots_programados,
                )
            )
    hallazgo(
        "OrdenEstacionDia.spots_solicitados: la demo de frontend no distingue 'solicitado' "
        "de 'asignado' a nivel de día (un solo número, `spots_diarios`) — se sembró "
        "spots_solicitados = spots_asignados en todos los días (0 faltantes)."
    )
    return ids


# ═══════════════════════════════════════════════════════════════════════════════
# Verificacion + Incidencia (mismos datos que mocks/incidencias.ts)
# ═══════════════════════════════════════════════════════════════════════════════
# 3 incidencias precargadas en la demo: (oe_clave, fecha, tipo_v5, nota)
INCIDENCIAS_MOCK = [
    ("oe3", date(2025, 6, 15), "descuento", "2 spots no transmitidos por corte de programación."),
    (
        "oe7",
        date(2025, 5, 9),
        "bonificacion",
        "Afiliado bonificó 3 spots adicionales por tema técnico.",
    ),
    (
        "oe10",
        date(2025, 3, 18),
        "descuento",
        "Spots transmitidos fuera del horario prime acordado.",
    ),
]
MAPEO_TIPO_INCIDENCIA = {"descuento": "faltante", "bonificacion": "excedente"}


def seed_verificaciones_e_incidencias(db: Session, oe_ids: dict[str, uuid.UUID]) -> None:
    incidencias_por_dia = {
        (oe_clave, fecha): (tipo, nota) for oe_clave, fecha, tipo, nota in INCIDENCIAS_MOCK
    }

    for oe in OE_MOCKS:
        if MAPEO_ESTATUS_OE[oe["estatus_v5"]] != "cerrada":  # solo 2.3 genera Verificacion
            continue
        real_over = oe.get("real_override", {})
        precio_spot = Decimal(oe["precio_spot"])
        prog_over = oe.get("prog_override", {})

        for fecha, _hi, _hf, spots in oe["periodo"]:
            programado_efectivo = prog_over.get(fecha, spots)  # ya confirmado, siempre (2.3 ⊃ 2.2)
            verificado = real_over.get(fecha, programado_efectivo)
            dia_id = uid(f"orden_estacion_dia:{oe['clave']}:{fecha.isoformat()}")
            ver_id = uid(f"verificacion:{oe['clave']}:{fecha.isoformat()}")

            db.merge(
                Verificacion(
                    verificacion_id=ver_id,
                    orden_estacion_dia_id=dia_id,
                    spots_verificados=verificado,
                    fecha_verificacion=fecha,
                    notas_verificacion=oe.get("obs") if fecha in real_over else None,
                    reconciliada=True,
                    created_by=ADMIN_ID,
                )
            )

            clave_inc = (oe["clave"], fecha)
            if clave_inc in incidencias_por_dia:
                tipo_v5, nota = incidencias_por_dia[clave_inc]
                diferencia = verificado - programado_efectivo
                db.merge(
                    Incidencia(
                        incidencia_id=uid(f"incidencia:{oe['clave']}:{fecha.isoformat()}"),
                        verificacion_id=ver_id,
                        orden_estacion_id=oe_ids[oe["clave"]],
                        tipo_incidencia=MAPEO_TIPO_INCIDENCIA[tipo_v5],
                        spots_ordenados=programado_efectivo,
                        spots_ejecutados=verificado,
                        diferencia_spots=diferencia,
                        descripcion_incidencia=nota,
                        fecha_incidencia=fecha,
                        resolucion="pendiente",
                        monto_ajuste=(Decimal(diferencia) * precio_spot).quantize(Decimal("0.01")),
                    )
                )
    hallazgo(
        "Incidencia.resolucion: la spec trae un flujo de resolución manual completo que "
        "la demo de frontend no tiene (genera incidencias 100% automáticas, sin resolver). "
        "Las 3 incidencias sembradas quedan en 'pendiente' — nadie las ha resuelto todavía "
        "(comportamiento correcto: la demo tampoco lo hacía)."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Historial de comisiones (mismos datos que mocks/historialComisiones.ts) — reutiliza
# la tabla GENÉRICA `log_cambio_parametro` (F0-03) con entidad="OrdenCliente".
# ═══════════════════════════════════════════════════════════════════════════════
HISTORIAL_COMISIONES = [
    (
        "hcp1",
        "oc7",
        "porcentaje_comision_vendedor_principal_snap",
        "4",
        "4.5",
        "dev.admin",
        "Ajuste autorizado por dirección por desempeño en la campaña.",
        datetime(2025, 3, 10, 11, 20),
    ),
    (
        "hcp2",
        "oc9",
        "porcentaje_comision_agencia_snap",
        "15",
        "13.5",
        "dev.admin",
        "Renegociación de comisión anual con Mindshare, posterior al cierre.",
        datetime(2025, 1, 10, 9, 45),
    ),
    (
        "hcp3",
        "oc8",
        "porcentaje_comision_vendedor_principal_snap",
        "4",
        "3.5",
        "dev.admin",
        "Corrección de captura: el % pactado con el vendedor era 3.5%, no 4%.",
        datetime(2025, 1, 5, 16, 5),
    ),
]


def seed_historial_comisiones(db: Session, oc_ids: dict[str, uuid.UUID]) -> None:
    for clave, oc_clave, campo, anterior, nuevo, usuario, motivo, fecha in HISTORIAL_COMISIONES:
        db.merge(
            LogCambioParametro(
                log_cambio_parametro_id=uid(f"log_cambio_parametro:{clave}"),
                entidad="OrdenCliente",
                entidad_id=str(oc_ids[oc_clave]),
                campo=campo,
                valor_anterior=anterior,
                valor_nuevo=nuevo,
                usuario=usuario,
                motivo_cambio=motivo,
                fecha_cambio=fecha,
            )
        )


# ═══════════════════════════════════════════════════════════════════════════════
def _verificar_solo_sqlite() -> None:
    """Guard de seguridad — DEBE ser lo primero que corre `main()`, antes de
    imprimir/loguear nada y antes de crear el engine (`get_engine()`).

    Este script escribe datos de demo; si `DATABASE_URL` no apunta a SQLite,
    `settings.sqlalchemy_url` resuelve a la cadena de conexión real de RDS (la base
    compartida del equipo) y seguir de largo terminaría sembrando ahí datos falsos.
    Aislado en su propia función (en vez de vivir inline al principio de `main()`)
    para que `test_seed_dev_guard.py` pueda invocarlo directo sin correr el resto del
    script, y para que el orden de las líneas de `main()` no pueda reordenarse por
    accidente sin que la prueba lo note.
    """
    if "sqlite" not in settings.sqlalchemy_url:
        raise SystemExit(
            "DATABASE_URL no apunta a SQLite — este script es SOLO para desarrollo local "
            "(ADR-028). Abortado para no tocar RDS por accidente."
        )


# ══════════════════════════════════════════════════════════════════════════════
# F2 — Facturación
# ══════════════════════════════════════════════════════════════════════════════
# Los estados de las facturas se eligieron para que sean COHERENTES con el handoff
# (ADR de la tanda 2 de F2): una `OrdenCliente` está en `facturada` si y solo si su
# `FacturaCliente` llegó al menos a `timbrada`. Por eso:
#   oc6 (orden_cerrada) → factura `preparada`   (todavía no timbrada, la OC no avanza)
#   oc7 (facturada)     → factura `timbrada`
#   oc8 (facturada)     → factura `entregada`
#   oc9 (cobrada)       → factura `cobrada`
# Sembrar, por ejemplo, una OC `facturada` con su factura en `preparada` produciría un
# estado que el sistema real nunca podría generar.

#: Cuentas contables mínimas para que `FacturaCliente.cuenta_contable_id` tenga a qué
#: apuntar. F0-05 construyó la entidad pero `seed_dev` no la sembraba.
CUENTAS_CONTABLES = [
    ("cc1", "4100-001", "Ingresos por transmisión", "ingreso"),
    ("cc2", "5100-001", "Costo de transmisión (afiliados)", "costo"),
    ("cc3", "6100-001", "Gastos de operación", "gasto"),
]

#: Claves SAT que el frontend sugiere para `metodo_pago_clave` (no hay FK: ADR de F2).
CONSTANTES_F2 = [
    ("MetodoPago", "PUE", "Pago en una sola exhibición"),
    ("MetodoPago", "PPD", "Pago en parcialidades o diferido"),
    ("FormaPago", "03", "Transferencia electrónica de fondos"),
    ("FormaPago", "99", "Por definir"),
]

#: (clave, oc, numero, estado, folio_fiscal, fecha_factura, fecha_entrega)
FACTURAS_CLIENTE_MOCK = [
    ("fc1", "oc6", "A-1041", "preparada", None, date(2025, 4, 1), None),
    ("fc2", "oc7", "A-1042", "timbrada", "9F2A1C7E-0001-4B3D-9E11-AA0102030405",
     date(2025, 4, 2), None),
    ("fc3", "oc8", "A-1043", "entregada", "9F2A1C7E-0002-4B3D-9E11-AA0102030406",
     date(2025, 4, 3), date(2025, 4, 8)),
    ("fc4", "oc9", "A-1044", "cobrada", "9F2A1C7E-0003-4B3D-9E11-AA0102030407",
     date(2025, 4, 4), date(2025, 4, 9)),
]

#: (clave, oe_claves a las que se reparte, folio de la emisora, estatus)
FACTURAS_AFILIADO_MOCK = [
    ("fa1", ["oe12", "oe13"], "EMI-2025-118", "autorizada"),
    ("fa2", ["oe16"], "EMI-2025-204", "en_revision"),
]

#: (clave, oc, folio, porcentaje, estatus)
FACTURAS_AGENCIA_MOCK = [
    ("fag1", "oc7", "AG-5521", Decimal("12.00"), "autorizada"),
    ("fag2", "oc9", "AG-5588", Decimal("10.00"), "pagada"),
]

#: (clave, tipo, oc | None, descripcion, periodo, monto). El tipo se anota explícitamente:
#: la tercera posición mezcla `None` y `str`, y sin anotación mypy la unifica mal.
COSTOS_MOCK: list[tuple[str, str, str | None, str, str, Decimal]] = [
    ("co1", "nomina", None, "Nómina operativa OIR", "2025-03", Decimal("184500.00")),
    ("co2", "overhead", None, "Renta y servicios de oficina", "2025-03", Decimal("62300.00")),
    ("co3", "overhead", "oc9", "Producción de spot (proveedor externo)", "2025-04",
     Decimal("18000.00")),
]


def seed_facturacion(
    db: Session, cat: dict[str, dict[str, uuid.UUID]], oc_ids: dict[str, uuid.UUID]
) -> tuple[int, int]:
    """Siembra las 5 entidades de F2. Devuelve (facturas de cliente, facturas de proveedor).

    Los montos NO se inventan: se derivan de la OrdenCliente / OrdenEstacion ya sembradas,
    igual que lo haría el servicio real. Así los CHECK de suma exacta (`ROUND(x, 2)`) se
    cumplen por construcción y la demo es aritméticamente consistente con F1.
    """
    for clave, codigo, nombre, tipo in CUENTAS_CONTABLES:
        u = uid(f"cuenta_contable:{clave}")
        db.merge(
            CuentaContable(
                cuenta_contable_id=u, codigo_cuenta=codigo, nombre_cuenta=nombre, tipo_cuenta=tipo
            )
        )
        cat.setdefault("cuenta_contable", {})[clave] = u

    for grupo, clave_c, descripcion in CONSTANTES_F2:
        db.merge(
            ConstanteSistema(
                constante_sistema_id=uid(f"constante:{grupo}:{clave_c}"),
                grupo=grupo,
                clave=clave_c,
                descripcion=descripcion,
            )
        )
    db.flush()

    # ── FacturaCliente ────────────────────────────────────────────────────────
    for clave, oc_clave, numero, estado, folio_fiscal, f_factura, f_entrega in (
        FACTURAS_CLIENTE_MOCK
    ):
        oc = db.get(OrdenCliente, oc_ids[oc_clave])
        if oc is None:  # pragma: no cover — la OC siempre se sembró antes
            continue
        # Receptor: agencia si la hay y no es facturación directa (misma regla del servicio).
        if oc.facturacion_directa_cliente or oc.agencia_id is None:
            receptor = db.get(Anunciante, oc.anunciante_id)
            razon_social = receptor.nombre_fiscal if receptor else "Sin anunciante"
            rfc = receptor.rfc_anunciante if receptor else "XAXX010101000"
        else:
            agencia = db.get(Agencia, oc.agencia_id)
            razon_social = agencia.nombre_agencia if agencia else "Sin agencia"
            rfc = agencia.rfc_agencia if agencia else "XAXX010101000"

        subtotal = Decimal(oc.subtotal).quantize(CENTAVOS)
        iva = (subtotal * IVA_RATE).quantize(CENTAVOS)
        db.merge(
            FacturaCliente(
                factura_id=uid(f"factura_cliente:{clave}"),
                numero_factura=numero,
                numero_pedido=oc.numero_orden_cliente,
                orden_id=oc.orden_id,
                empresa_facturadora_id=oc.empresa_facturadora_id,
                anunciante_id=oc.anunciante_id,
                agencia_id=oc.agencia_id,
                razon_social_facturacion=razon_social,
                rfc_facturacion=rfc,
                direccion_facturacion=oc.direccion_facturacion,
                descripcion_factura=(
                    f"Servicios de transmisión del {oc.fecha_inicio_campania:%d/%m/%Y} "
                    f"al {oc.fecha_fin_campania:%d/%m/%Y}"
                ),
                fecha_inicio_transmision=oc.fecha_inicio_campania,
                fecha_fin_transmision=oc.fecha_fin_campania,
                fecha_factura=f_factura,
                fecha_entrega_factura=f_entrega,
                subtotal_factura=subtotal,
                iva_factura=iva,
                total_factura=(subtotal + iva).quantize(CENTAVOS),
                cuenta_contable_id=cat["cuenta_contable"]["cc1"],
                metodo_pago_clave="PUE",
                info_cuenta_pago="BBVA · CLABE 012180001234567895 · Grupo Radio Centro",
                estado_facturacion=estado,
                folio_fiscal_sat=folio_fiscal,
                fecha_timbrado=f_factura if folio_fiscal else None,
                created_by=ADMIN_ID,
            )
        )

    # ── FacturaAfiliado + su reparto entre OrdenEstacion cerradas ─────────────
    for clave, oe_claves, folio_emisora, estatus in FACTURAS_AFILIADO_MOCK:
        # Se filtra en UNA expresión (y no reasignando la lista) para que el tipo quede
        # `list[OrdenEstacion]` y no `list[OrdenEstacion | None]`.
        oes: list[OrdenEstacion] = [
            oe
            for oe in (db.get(OrdenEstacion, uid(f"orden_estacion:{k}")) for k in oe_claves)
            if oe is not None
        ]
        if not oes:  # pragma: no cover
            continue
        # El costo del afiliado es lo que le toca a la emisora en esas OE (F1 ya lo calculó).
        monto = sum((Decimal(oe.importe_emisora) for oe in oes), Decimal("0")).quantize(CENTAVOS)
        iva = (monto * IVA_RATE).quantize(CENTAVOS)
        estacion = db.get(Estacion, oes[0].estacion_id)
        afiliado = db.get(Afiliado, estacion.afiliado_id) if estacion else None
        if afiliado is None:  # pragma: no cover — la FK de la estación lo garantiza
            continue
        factura_id = uid(f"factura_afiliado:{clave}")
        db.merge(
            FacturaAfiliado(
                factura_afiliado_id=factura_id,
                afiliado_id=afiliado.afiliado_id,
                razon_social_afiliada=afiliado.razon_social_afiliado,
                factura_emisora=folio_emisora,
                fecha_factura_afiliado=date(2025, 4, 10),
                monto_factura_afiliado=monto,
                iva_factura_afiliado=iva,
                total_factura_afiliado=(monto + iva).quantize(CENTAVOS),
                estatus_factura_afiliado=estatus,
                created_by=ADMIN_ID,
            )
        )
        for oe in oes:
            db.merge(
                FacturaAfiliadoOrden(
                    id=uid(f"factura_afiliado_orden:{clave}:{oe.folio_orden_estacion}"),
                    factura_afiliado_id=factura_id,
                    orden_estacion_id=oe.orden_estacion_id,
                    monto_asignado=Decimal(oe.importe_emisora).quantize(CENTAVOS),
                    notas_asignacion=f"Importe emisora de {oe.folio_orden_estacion}",
                )
            )

    # ── FacturaAgencia ────────────────────────────────────────────────────────
    for clave, oc_clave, folio, porcentaje, estatus in FACTURAS_AGENCIA_MOCK:
        oc = db.get(OrdenCliente, oc_ids[oc_clave])
        if oc is None or oc.agencia_id is None:  # pragma: no cover
            continue
        comision = (Decimal(oc.total) * porcentaje / Decimal(100)).quantize(CENTAVOS)
        # La agencia factura su comisión: el subtotal ES la comisión.
        iva = (comision * IVA_RATE).quantize(CENTAVOS)
        db.merge(
            FacturaAgencia(
                factura_agencia_id=uid(f"factura_agencia:{clave}"),
                agencia_id=oc.agencia_id,
                orden_id=oc.orden_id,
                folio_factura_agencia=folio,
                fecha_factura_agencia=date(2025, 4, 12),
                monto_factura_agencia=comision,
                iva_factura_agencia=iva,
                total_factura_agencia=(comision + iva).quantize(CENTAVOS),
                porcentaje_comision_agencia=porcentaje,
                comision_agencia=comision,
                estatus_factura_agencia=estatus,
                created_by=ADMIN_ID,
            )
        )

    # ── CostoAdicional ────────────────────────────────────────────────────────
    # Nombres propios (sufijo `_c`): reutilizar `clave`/`monto` chocaría con los enlaces
    # que ya tienen esas variables más arriba en la misma función.
    for clave_c, tipo_c, oc_c, descripcion_c, periodo_c, monto_c in COSTOS_MOCK:
        db.merge(
            CostoAdicional(
                costo_id=uid(f"costo_adicional:{clave_c}"),
                tipo_costo=tipo_c,
                orden_id=oc_ids[oc_c] if oc_c else None,
                descripcion_costo=descripcion_c,
                periodo_contable=periodo_c,
                monto_costo=monto_c,
                created_by=ADMIN_ID,
            )
        )

    return len(FACTURAS_CLIENTE_MOCK), len(FACTURAS_AFILIADO_MOCK) + len(FACTURAS_AGENCIA_MOCK)


def main() -> None:
    _verificar_solo_sqlite()

    # La consola de Windows (cp1252) no siempre soporta los caracteres de caja del
    # reporte final; se reconfigura a UTF-8 para que el script sea portable entre
    # PowerShell/CI/Docker.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    engine = get_engine()
    SessionLocal = get_sessionmaker()
    # `url_enmascarada()` (app/core/db.py): nunca imprimir `settings.sqlalchemy_url`
    # crudo — para mssql+pyodbc empaqueta la contraseña dentro de `odbc_connect=`,
    # donde `hide_password` de SQLAlchemy no la ve. El guion de arriba ya garantiza
    # que en este punto es SQLite (sin contraseña real), pero se enmascara siempre
    # por si el guion cambia de lugar en el futuro.
    print(f"Sembrando contra: {url_enmascarada(settings.sqlalchemy_url)}")

    with SessionLocal() as db:
        seed_usuarios(db)
        cat = seed_catalogos(db)
        oc_ids = seed_ordenes_cliente(db, cat)
        oe_ids = seed_ordenes_estacion(db, cat, oc_ids)
        seed_verificaciones_e_incidencias(db, oe_ids)
        seed_historial_comisiones(db, oc_ids)
        n_fc, n_prov = seed_facturacion(db, cat, oc_ids)
        db.commit()

    print(
        f"OK — {len(OC_MOCKS)} OrdenCliente, {len(OE_MOCKS)} OrdenEstacion, "
        f"{n_fc} FacturaCliente y {n_prov} facturas de proveedor sembradas/actualizadas."
    )
    print("\n── Hallazgos (datos del mock que no calzan 1:1 con el modelo real) ──")
    for i, h in enumerate(HALLAZGOS, 1):
        print(f"{i}. {h}\n")

    engine.dispose()


if __name__ == "__main__":
    main()
