"""Enums de catálogo compartidos entre módulos (no específicos de ninguno).

Reubicado desde `app/modules/catalogos/tarifa.py` (ver ADR-032): `DuracionSpot` la usa
tanto `TarifaPlaza` (F0-02) como `OrdenCliente`/`OrdenEstacion` (F1).

**ADR-098 (petición del usuario):** se retiró el valor `mencion` — desde ADR-097
"Mención" ya es un valor del campo `producto` de `TarifaPlaza` (junto con
`spot`/`control_remoto`/`patrocinio`), así que tenerlo también aquí era una duración de
spot sin sentido (una "mención" no dura 20/30/60 segundos, es un tipo de colocación
publicitaria). Queda `20s | 30s | 60s`.
"""

from __future__ import annotations

from enum import StrEnum


class DuracionSpot(StrEnum):
    S20 = "20s"
    S30 = "30s"
    S60 = "60s"
