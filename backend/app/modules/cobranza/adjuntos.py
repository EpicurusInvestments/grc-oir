"""Adjuntos de Cobranza y Pagos (comprobante de pago, estado de cuenta bancario).

Construido con `build_adjuntos_router` (`app/shared/adjuntos_router.py`, ADR-067) — F3
es el tercer consumidor que justificó extraer esa factory de F1/F2.

Dos tipos que pertenecen a dominios de negocio distintos dentro del módulo (ver
`__init__.py`): el comprobante de pago es de CxC, el estado de cuenta es de Tesorería —
que NO tiene `pagos:editar` en la matriz (ver `movimiento_bancario.py`). El router de
adjuntos es UN endpoint genérico sin lógica de negocio por tipo, así que en vez de
partirlo en dos permisos se usa `cobranza:leer` para ambas acciones: es la ÚNICA clave
que las 8 áreas satisfacen a la vez (CxC tiene `WRITE` sobre `cobranza`, que ya cubre
`leer`; las otras 7 —incluida Tesorería— están en su lista de solo-lectura). El
guardarraíl fino (que solo Tesorería pueda ASIGNAR el archivo a un
`MovimientoBancario`) vive en `movimiento_bancario.py`, no aquí — mismo criterio
pragmático que F2 ya documentó para sus propios adjuntos ("se usa la clave más amplia
del módulo").

`content_disposition="attachment"` (se descarga, mismo criterio que F2) y SÍ quita el
prefijo UUID en la descarga (mismo criterio que F1) — a diferencia de F2, aquí no hay
un motivo para preservarlo: es un archivo nuevo, sin la deuda histórica de F2.
"""

from __future__ import annotations

from enum import StrEnum

from app.shared.adjuntos_router import build_adjuntos_router


class TipoAdjuntoCobranza(StrEnum):
    #: Comprobante de pago del cliente (`PagoCliente.archivo_path`).
    COMPROBANTE_PAGO = "comprobante_pago"
    #: Estado de cuenta / soporte del movimiento bancario (`MovimientoBancario.archivo_path`).
    ESTADO_CUENTA = "estado_cuenta"


_PREFIJOS: dict[TipoAdjuntoCobranza, str] = {
    TipoAdjuntoCobranza.COMPROBANTE_PAGO: "cobranza/pagos/comprobante/",
    TipoAdjuntoCobranza.ESTADO_CUENTA: "cobranza/bancario/estado_cuenta/",
}

router = build_adjuntos_router(
    tag="cobranza:adjuntos",
    tipos=TipoAdjuntoCobranza,
    prefijos=_PREFIJOS,
    permiso_subir="cobranza:leer",
    permiso_descargar="cobranza:leer",
    content_disposition="attachment",
    quitar_prefijo_uuid_en_descarga=True,
)
