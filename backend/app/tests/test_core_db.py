"""Pruebas de `app/core/db.py` · ADR-114 (fix): `get_db()` no debe reventar si la
conexión a RDS murió a mitad de un request y `session.close()` falla al intentar el
rollback implícito. Sin el fix, esa segunda excepción se escapa del `finally` del
generador en un punto que ya no envuelve el middleware de errores de FastAPI — el
cliente ve un corte de conexión crudo ("Network Error") en vez del 500 con JSON que
FastAPI ya iba a mandar por la excepción original.
"""

from __future__ import annotations

import pytest

from app.core import db as db_module


class _SesionQueFallaAlCerrar:
    def close(self) -> None:
        raise RuntimeError("Communication link failure (conexión ya muerta)")


def test_get_db_no_propaga_si_session_close_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "get_sessionmaker", lambda: _SesionQueFallaAlCerrar)

    generador = db_module.get_db()
    sesion = next(generador)
    assert isinstance(sesion, _SesionQueFallaAlCerrar)

    # Antes del fix, esto propagaba el `RuntimeError` de `close()` en vez de terminar
    # limpio el generador (`StopIteration`, lo normal al agotar un `yield` único).
    with pytest.raises(StopIteration):
        next(generador)


def test_get_db_cierra_normal_cuando_no_hay_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    cerrada = {"valor": False}

    class _SesionNormal:
        def close(self) -> None:
            cerrada["valor"] = True

    monkeypatch.setattr(db_module, "get_sessionmaker", lambda: _SesionNormal)

    generador = db_module.get_db()
    next(generador)
    with pytest.raises(StopIteration):
        next(generador)
    assert cerrada["valor"] is True
