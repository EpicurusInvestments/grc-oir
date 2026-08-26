"""Integración con el timbrador externo (PAC).

Un solo punto de selección del adaptador, igual que `get_almacenamiento()` en la
integración de almacenamiento.

Desde que llegó el layout real (`docs/referencias/ejemplo_archivo_plano_*.txt`) existe un
único adaptador: `TimbradoExportPacV40`. El placeholder que se usó mientras el formato
estaba `[[POR LLENAR]]` se ELIMINÓ en vez de conservarse — mantener un generador falso
junto al real solo invita a exportar el equivocado.
"""

from __future__ import annotations

from app.core.config import settings
from app.integrations.timbrado.adapter_pac_v40 import (
    ErrorCodificacionTimbrado,
    TimbradoExportPacV40,
)
from app.integrations.timbrado.port import DatosTimbrado, TimbradoExportPort

__all__ = [
    "DatosTimbrado",
    "ErrorCodificacionTimbrado",
    "TimbradoExportPacV40",
    "TimbradoExportPort",
    "get_timbrado_export",
]


def get_timbrado_export() -> TimbradoExportPort:
    """Devuelve el adaptador de exportación configurado.

    Sin `if` por ahora: hay un único formato. La codificación sí es configurable
    (`TIMBRADO_ENCODING`) porque es el punto abierto del layout — ver el docstring del
    adaptador.
    """
    return TimbradoExportPacV40(encoding=settings.timbrado_encoding)
