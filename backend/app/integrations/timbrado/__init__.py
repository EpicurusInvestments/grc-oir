"""Integración con el timbrador externo (PAC).

Un solo punto de selección del adaptador, igual que `get_almacenamiento()` en la
integración de almacenamiento. HOY solo existe el placeholder (el formato real del PAC
sigue [[POR LLENAR]]); cuando llegue la especificación se agrega el adaptador real y se
elige aquí por configuración, sin tocar nada del dominio.
"""

from __future__ import annotations

from app.integrations.timbrado.adapter_placeholder import TimbradoExportPlaceholder
from app.integrations.timbrado.port import TimbradoExportPort

__all__ = ["TimbradoExportPlaceholder", "TimbradoExportPort", "get_timbrado_export"]


def get_timbrado_export() -> TimbradoExportPort:
    """Devuelve el adaptador de exportación configurado.

    Sin `if` por ahora: hay un único adaptador. Se deja como función (y no como una
    constante) para que el día que exista el formato real el cambio sea de UNA línea aquí
    y los servicios no se enteren.
    """
    return TimbradoExportPlaceholder()
