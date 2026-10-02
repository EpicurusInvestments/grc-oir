"""Exporta catálogos reales (capturados en AWS RDS) hacia el SQLite local de
desarrollo (ADR-028).

Por qué existe: mientras la conexión a RDS esté disponible, este script trae al
SQLite local los catálogos REALES que el equipo ya capturó en el sistema — a
diferencia de `cargar_codigos_postales.py`, que carga un catálogo ESTÁTICO (SEPOMEX)
desde un CSV del repo y no depende de RDS en absoluto.

Tablas que copia (en este orden, respetando llaves foráneas):
    Plaza, Categoria, Vendedor, EmpresaFacturadora, CuentaContable,
    ConstanteSistema, Agencia, ContactoAgencia, Afiliado, ContactoAfiliado,
    Estacion, Anunciante, Marca, ContactoAnunciante, Contrato, TarifaPlaza.

Qué NO copia (a propósito):
    - `asentamiento_postal`: usa `cargar_codigos_postales.py` (CSV local, ya
      incluido en el repo; no depende de RDS).
    - `usuario`: credenciales/hashes reales no deben terminar en un SQLite de
      desarrollo; `seed_dev.py` ya siembra un usuario `dev.admin` sintético.
    - Entidades operativas de F1-F5 (órdenes, facturas, cobranza, etc.): fuera de
      alcance de "catálogos"; usa `seed_dev.py` para datos sintéticos de prueba.

Requiere que RDS esté alcanzable. Construye la URL de origen directamente desde
DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD/... del `.env`, IGNORANDO `DATABASE_URL`
— así puede correr sin tener que comentar/descomentar nada, aunque `DATABASE_URL` ya
esté apuntando al SQLite local (ADR-028). El DESTINO sí es siempre el que resuelva
`settings.sqlalchemy_url` (por eso exige que sea SQLite: ver `_verificar_destino_sqlite`).

Uso (desde `backend/`, con RDS alcanzable):
    .venv\\Scripts\\python.exe -m scripts.exportar_catalogos_rds_a_sqlite

Idempotente: por tabla, borra lo existente en el SQLite destino y reinserta desde RDS
(mismo patrón que `cargar_codigos_postales.py`), en lotes de 5000 filas.
"""

from __future__ import annotations

import urllib.parse

from app.core.config import settings
from app.core.db import get_engine as _get_destino_engine
from app.core.db import get_sessionmaker as _get_destino_sessionmaker
from app.modules.catalogos.afiliado import Afiliado, ContactoAfiliado
from app.modules.catalogos.agencia import Agencia, ContactoAgencia
from app.modules.catalogos.anunciante import Anunciante, ContactoAnunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.constantes_sistema import ConstanteSistema
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.tarifa import TarifaPlaza
from app.modules.catalogos.vendedor import Vendedor
from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.orm import Session, sessionmaker

_LOTE = 5000

# Orden de copiado: los padres siempre antes que sus hijos (FKs).
_TABLAS_EN_ORDEN = [
    Plaza,
    Categoria,
    Vendedor,
    EmpresaFacturadora,
    CuentaContable,
    ConstanteSistema,
    Agencia,
    ContactoAgencia,
    Afiliado,
    ContactoAfiliado,
    Estacion,
    Anunciante,
    Marca,
    ContactoAnunciante,
    Contrato,
    TarifaPlaza,
]


def _url_rds() -> str:
    """URL mssql+pyodbc de RDS, construida directo desde DB_HOST/... del `.env`.

    Ignora `DATABASE_URL` a propósito: aunque esté seteada al SQLite local
    (ADR-028), el ORIGEN de este script siempre debe ser RDS.
    """
    odbc_str = (
        f"DRIVER={{{settings.odbc_driver}}};"
        f"SERVER={settings.db_host},{settings.db_port};"
        f"DATABASE={settings.db_name};"
        f"UID={settings.db_user};"
        f"PWD={settings.db_password};"
        f"Encrypt={settings.db_encrypt};"
        f"TrustServerCertificate={settings.db_trust_server_certificate};"
    )
    return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc_str)


def _verificar_destino_sqlite() -> None:
    """Nunca sobrescribir un destino que no sea SQLite (mismo guardarraíl que
    `seed_dev.py::_verificar_solo_sqlite`)."""
    if "sqlite" not in settings.sqlalchemy_url:
        raise RuntimeError(
            "El destino (settings.sqlalchemy_url) no es SQLite. Este script solo "
            "debe correr para poblar el SQLite local de desarrollo (ADR-028); revisa "
            "DATABASE_URL en tu .env antes de continuar."
        )


def _copiar_tabla(origen: Session, destino: Session, modelo: type) -> int:
    # Se usa la `Table` de Core (no `select(modelo)`/`insert(modelo)` a nivel ORM):
    # un select ORM de la clase entera devuelve UNA fila-objeto por renglón bajo una
    # sola llave (p.ej. {"Plaza": <Plaza obj>}), no un mapeo columna-por-columna.
    tabla = modelo.__table__
    filas = origen.execute(select(tabla)).mappings().all()
    destino.execute(delete(tabla))
    total = 0
    for inicio in range(0, len(filas), _LOTE):
        lote = [dict(fila) for fila in filas[inicio : inicio + _LOTE]]
        if lote:
            destino.execute(insert(tabla), lote)
            total += len(lote)
        destino.commit()
    return total


def main() -> None:
    _verificar_destino_sqlite()

    origen_engine = create_engine(_url_rds())
    OrigenSession = sessionmaker(bind=origen_engine)
    DestinoSession = _get_destino_sessionmaker()
    _get_destino_engine()  # fuerza la creación perezosa antes de usarlo abajo.

    print(f"Origen (RDS):    {settings.db_host}/{settings.db_name}")
    print(f"Destino (local): {settings.sqlalchemy_url}")

    with OrigenSession() as origen, DestinoSession() as destino:
        for modelo in _TABLAS_EN_ORDEN:
            nombre = modelo.__tablename__
            print(f"Copiando {nombre}...")
            total = _copiar_tabla(origen, destino, modelo)
            print(f"  {total} filas copiadas en {nombre}.")

    print("Listo.")


if __name__ == "__main__":
    main()
