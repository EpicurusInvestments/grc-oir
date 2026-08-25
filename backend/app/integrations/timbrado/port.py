"""Puerto de exportación al timbrador externo (PAC) — patrón anti-corrupción.

Mismo criterio que el puerto de almacenamiento (ADR-020 → ADR-027): el dominio depende
SOLO de esta interfaz y el adaptador concreto se inyecta por configuración, así que
cambiar de formato o de PAC no toca la capa de negocio.

**El sistema NUNCA timbra** (ADR-002). Este puerto solo EXPORTA la información que el PAC
necesita; el folio fiscal, el XML y el PDF vuelven por captura/carga, no por aquí.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover — solo para tipos, evita el ciclo de imports
    from app.modules.facturacion.factura_cliente import FacturaCliente


class TimbradoExportPort(Protocol):
    """Exportación de una factura al formato que espera el timbrador."""

    #: Identificador del formato, para trazabilidad en logs y pruebas.
    nombre_formato: str

    def exportar(self, factura: FacturaCliente) -> bytes:
        """Serializa la factura al archivo plano que se envía al PAC.

        Devuelve BYTES, no `str`: el layout real del PAC probablemente fije una
        codificación concreta (los timbradores mexicanos suelen pedir ISO-8859-1 o
        UTF-8 sin BOM), y esa decisión pertenece al adaptador, no al dominio.
        """
        ...

    def nombre_archivo(self, factura: FacturaCliente) -> str:
        """Nombre sugerido del archivo exportado."""
        ...
