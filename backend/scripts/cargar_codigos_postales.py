"""Carga del catálogo de códigos postales (SEPOMEX) — F0.

Siembra `asentamiento_postal` desde el catálogo público de Correos de México
(`backend/app/data/sepomex_codigos_postales.csv`, abril 2016 — ver el README de esa
carpeta para la fuente y cómo actualizarlo). NO es una migración: 145,908 filas son
demasiadas para vivir dentro de un `upgrade()` de Alembic; esto es un script normal,
re-ejecutable, que corre DESPUÉS de `alembic upgrade head`.

Idempotente por REEMPLAZO COMPLETO: borra todo lo que haya en la tabla y vuelve a
insertar desde el CSV. Con ~146k filas, un upsert fila por fila no aporta nada frente
a recargar completo cada vez que el catálogo se actualiza.

El CSV pierde el cero a la izquierda de algunos CP (los de Ciudad de México que
empiezan en "0", p.ej. "06700" queda como "6700" — se ve como un valor NUMÉRICO en
algún paso previo de generación del archivo): se restaura con `.zfill(5)` al cargar.

Uso (desde `backend/`, con las migraciones ya aplicadas):
    .venv\\Scripts\\python.exe -m scripts.cargar_codigos_postales
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.db import get_engine, get_sessionmaker, url_enmascarada
from app.modules.catalogos.codigo_postal import AsentamientoPostal
from sqlalchemy import delete, insert

_CSV = Path(__file__).resolve().parent.parent / "app" / "data" / "sepomex_codigos_postales.csv"
_LOTE = 5000


def _filas(ruta: Path) -> Iterator[dict[str, Any]]:
    with ruta.open("r", encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            yield {
                "codigo_postal": fila["cp"].strip().zfill(5),
                "asentamiento": fila["asentamiento"].strip(),
                "tipo_asentamiento": fila["tipo"].strip() or None,
                "municipio": fila["municipio"].strip(),
                "estado": fila["estado"].strip(),
                "ciudad": fila.get("ciudad", "").strip() or None,
                "pais": "MEX",
            }


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if not _CSV.is_file():
        print(f"No se encontró el archivo: {_CSV}")
        raise SystemExit(1)

    engine = get_engine()
    db = get_sessionmaker()()
    try:
        print(f"BD destino: {url_enmascarada(str(engine.url))}")
        print(f"Archivo: {_CSV}")

        print("Borrando datos previos de asentamiento_postal…")
        db.execute(delete(AsentamientoPostal))
        db.commit()

        total = 0
        lote: list[dict[str, Any]] = []
        for fila in _filas(_CSV):
            lote.append(fila)
            if len(lote) >= _LOTE:
                db.execute(insert(AsentamientoPostal), lote)
                db.commit()
                total += len(lote)
                print(f"  {total} filas cargadas…")
                lote = []
        if lote:
            db.execute(insert(AsentamientoPostal), lote)
            db.commit()
            total += len(lote)

        print(f"Listo: {total} filas insertadas en asentamiento_postal.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
