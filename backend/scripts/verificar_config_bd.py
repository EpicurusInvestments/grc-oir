"""Verificación de configuración de base de datos — SOLO lectura, CERO conexión.

Responde una pregunta muy concreta antes de tocar Alembic: ¿a qué base van a apuntar
sus comandos, RDS o el SQLite local de desarrollo (ADR-028)? Con el switch de
`DATABASE_URL` (ADR-028), `alembic current`/`upgrade` pueden estar leyendo un archivo
local mientras alguien asume que están leyendo RDS — este script existe para que esa
duda nunca dependa de memoria ni de suposiciones.

Resuelve la URL por el MISMO camino que usa `migrations/env.py`: importa
`app.core.config.settings` y lee `settings.sqlalchemy_url` — la misma propiedad,
ni una variable de entorno leída por su cuenta, ni una URL reconstruida a mano. Si el
día de mañana `sqlalchemy_url` cambia de lógica, este script hereda el cambio solo con
importar `settings` de nuevo — no hay una segunda copia de la lógica que se pueda
desincronizar.

No crea un `Engine`, no llama `.connect()`, no hace ping a nada. Solo `make_url(...)`
sobre el string ya resuelto, para poder inspeccionar sus partes (host, puerto, base,
usuario) y renderizarlo de vuelta con la contraseña enmascarada
(`URL.render_as_string(hide_password=True)`).

Uso (desde `backend/`):
    .venv\\Scripts\\python.exe -m scripts.verificar_config_bd
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.db import url_enmascarada
from sqlalchemy.engine import URL, make_url

SEPARADOR = "=" * 78


def _partes_odbc_connect(url: URL) -> dict[str, str]:
    """Host/puerto/base/usuario reales cuando vienen empacados en `odbc_connect=`
    (caso `mssql+pyodbc` de este proyecto) — ahí `url.host`/`url.port`/`url.username`
    están estructuralmente vacíos porque TODO vive dentro de ese único parámetro de
    query. Parseo best-effort del formato `CLAVE=valor;CLAVE=valor;...` que construye
    `Settings.sqlalchemy_url`; nunca incluye `PWD` (esa se enmascara aparte)."""
    odbc_connect = url.query.get("odbc_connect")
    if not odbc_connect:
        return {}
    partes: dict[str, str] = {}
    for segmento in str(odbc_connect).split(";"):
        if "=" in segmento:
            clave, _, valor = segmento.partition("=")
            if clave.strip().upper() != "PWD":
                partes[clave.strip().upper()] = valor.strip()
    return partes


def main() -> None:
    import sys

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    url_cruda = settings.sqlalchemy_url  # MISMA propiedad que usa migrations/env.py
    url = make_url(url_cruda)
    es_sqlite = url.get_backend_name() == "sqlite"

    print(SEPARADOR)
    print("VERIFICACIÓN DE CONFIGURACIÓN DE BASE DE DATOS (solo lectura, sin conectar)")
    print(SEPARADOR)

    print(f"\nMODO: {'SQLite local' if es_sqlite else 'SQL Server / RDS'}")
    print(f"Dialecto + driver: {url.drivername}")

    if es_sqlite:
        print("Host: N/A (SQLite no usa host/puerto)")
        print("Puerto: N/A (SQLite no usa host/puerto)")
        print(f"Nombre de la base (archivo): {url.database}")
        print("Usuario: N/A (SQLite no tiene usuario)")
    else:
        # `url.host`/`.port`/`.database`/`.username` están vacíos estructuralmente
        # (todo vive en el query param `odbc_connect=`, ver `_partes_odbc_connect`).
        partes = _partes_odbc_connect(url)
        servidor = partes.get("SERVER", "")
        host, _, puerto = servidor.partition(",")
        print(f"Host: {host or '(no se pudo determinar)'}")
        print(f"Puerto: {puerto or '(no se pudo determinar)'}")
        print(f"Nombre de la base: {partes.get('DATABASE', '(no se pudo determinar)')}")
        print(f"Usuario: {partes.get('UID', '(no se pudo determinar)')}")

    print(f"\nURL completa (contraseña enmascarada): {url_enmascarada(url_cruda)}")

    print(
        f"\nDATABASE_URL (override de SQLite, ADR-028): {settings.database_url or '(no definida)'}"
    )
    if settings.database_url:
        print(
            "  → SÍ está definida: por eso el modo es SQLite local, sin importar db_host/db_user."
        )
    else:
        print("  → NO está definida: por eso se construyó la URL mssql+pyodbc de siempre.")

    print("\nArchivos .env que pydantic-settings intenta cargar (en este orden, se fusionan):")
    for candidato in (".env", "../.env"):
        ruta = Path(candidato).resolve()
        existe = ruta.is_file()
        print(f"  - {candidato} → {ruta} [{'EXISTE, se cargó' if existe else 'no existe'}]")

    print(f"\n{SEPARADOR}")
    if es_sqlite:
        print("⚠️  APUNTA A SQLITE LOCAL — los comandos de Alembic NO tocarán RDS")
    else:
        print("✅ APUNTA A SQL SERVER (RDS) — los comandos de Alembic leerán y escribirán en RDS")
    print(SEPARADOR)


if __name__ == "__main__":
    main()
