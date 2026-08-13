"""Enums de catálogo compartidos entre módulos (no específicos de ninguno).

Reubicado desde `app/modules/catalogos/tarifa.py` (ver ADR-032): `DuracionSpot` la usa
tanto `TarifaPlaza` (F0-02) como `OrdenCliente`/`OrdenEstacion` (F1) — spec BD v2:
`20s | 30s | 60s | mencion`.
"""

from __future__ import annotations

from enum import StrEnum


class DuracionSpot(StrEnum):
    S20 = "20s"
    S30 = "30s"
    S60 = "60s"
    MENCION = "mencion"
