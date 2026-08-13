"""Prueba del guard de `scripts/seed_dev.py` — auditoría de migración a RDS, Tanda 4c.

`seed_dev.py` escribe datos de demo; si algún día alguien reordena `main()` sin darse
cuenta, ese guard podría dejar de ser lo primero que corre y el script terminaría
resolviendo un engine contra RDS antes de abortar (incidente real que motivó esta
prueba — ver `INFORME-MIGRACION-RDS-F1.md`). Sin esta prueba, la protección depende
de que nadie reordene dos líneas.
"""

from __future__ import annotations

import pytest
from scripts import seed_dev

from app.core.config import settings


def test_guard_aborta_si_database_url_no_es_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url", "")
    assert "sqlite" not in settings.sqlalchemy_url  # confirma la premisa de la prueba

    with pytest.raises(SystemExit):
        seed_dev._verificar_solo_sqlite()


def test_main_aborta_antes_de_crear_el_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el guard alguna vez deja de ser la primera instrucción de `main()`, esta
    prueba debe fallar: reemplaza `get_engine` por una función que revienta si se
    llega a invocar, para probar que `main()` nunca llega tan lejos."""
    monkeypatch.setattr(settings, "database_url", "")

    def _get_engine_no_deberia_llamarse() -> None:
        raise AssertionError("get_engine() se llamó pese a que el guard debía abortar antes")

    monkeypatch.setattr(seed_dev, "get_engine", _get_engine_no_deberia_llamarse)

    with pytest.raises(SystemExit):
        seed_dev.main()
