"""Adaptador PLACEHOLDER de exportación al PAC.

╔══════════════════════════════════════════════════════════════════════════════════╗
║  FORMATO BORRADOR — **NO es el layout real del PAC.**                            ║
║  El formato que espera el timbrador sigue sin definirse ([[POR LLENAR]] desde el  ║
║  inicio del proyecto; el archivo de referencia                                   ║
║  `archivo_plano_FACTURA_33_NPG_D_28_11757_V40.txt` no vino con su especificación).║
║                                                                                  ║
║  Este adaptador existe para NO bloquear el resto de F2: permite construir y       ║
║  probar el flujo completo (`preparada → enviada_a_timbrado`, captura de la        ║
║  respuesta) con un archivo real y determinista. Cuando llegue la especificación,  ║
║  se escribe otro adaptador y se cambia la selección en `__init__.py`; NADA del    ║
║  dominio cambia.                                                                 ║
║                                                                                  ║
║  PENDIENTE CRÍTICO antes de producción. No usar este archivo para enviar nada a   ║
║  un PAC real: sería rechazado.                                                    ║
╚══════════════════════════════════════════════════════════════════════════════════╝

El archivo generado lleva la advertencia en su PRIMERA línea, a propósito: si alguien lo
manda por error, quien lo reciba ve de inmediato que no es un layout válido.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.facturacion.factura_cliente import FacturaCliente

#: Marca literal en la primera línea del archivo. Las pruebas la verifican: si alguien
#: escribe el adaptador real reutilizando este módulo, la prueba falla y obliga a mirar.
ADVERTENCIA = "## FORMATO BORRADOR - NO ES EL LAYOUT REAL DEL PAC - NO ENVIAR A TIMBRAR ##"

#: Separador de campos. Elegido por ser improbable dentro de una razón social.
_SEP = "|"


def _texto(valor: object) -> str:
    """Normaliza a texto plano de una línea (el separador no puede colarse en un campo)."""
    if valor is None:
        return ""
    return str(valor).replace(_SEP, " ").replace("\r", " ").replace("\n", " ").strip()


def _monto(valor: Decimal | None) -> str:
    return f"{valor:.2f}" if valor is not None else "0.00"


class TimbradoExportPlaceholder:
    """Genera un archivo de texto con los campos conocidos de `FacturaCliente`."""

    nombre_formato = "borrador-v0"

    def exportar(self, factura: FacturaCliente) -> bytes:
        """Una línea por campo (`CLAVE|valor`), legible y diffeable.

        Deliberadamente NO imita un layout posicional ni un CFDI: un archivo que
        APARENTA ser el formato real es peor que uno que evidentemente no lo es —
        invita a que alguien lo dé por bueno.
        """
        campos: list[tuple[str, str]] = [
            ("NUMERO_FACTURA", _texto(factura.numero_factura)),
            ("NUMERO_PEDIDO", _texto(factura.numero_pedido)),
            ("REFERENCIA_ADICIONAL", _texto(factura.referencia_adicional)),
            ("ORDEN_ID", _texto(factura.orden_id)),
            ("RECEPTOR_RAZON_SOCIAL", _texto(factura.razon_social_facturacion)),
            ("RECEPTOR_RFC", _texto(factura.rfc_facturacion)),
            ("RECEPTOR_DIRECCION", _texto(factura.direccion_facturacion)),
            ("DESCRIPCION", _texto(factura.descripcion_factura)),
            ("OBSERVACIONES", _texto(factura.observaciones_factura)),
            ("PERIODO_INICIO", _texto(factura.fecha_inicio_transmision)),
            ("PERIODO_FIN", _texto(factura.fecha_fin_transmision)),
            ("FECHA_FACTURA", _texto(factura.fecha_factura)),
            ("SUBTOTAL", _monto(factura.subtotal_factura)),
            ("IVA", _monto(factura.iva_factura)),
            ("TOTAL", _monto(factura.total_factura)),
            ("METODO_PAGO_CLAVE", _texto(factura.metodo_pago_clave)),
            ("INFO_CUENTA_PAGO", _texto(factura.info_cuenta_pago)),
            ("LAYOUT", _texto(factura.layout_factura)),
        ]
        lineas = [ADVERTENCIA, *(f"{clave}{_SEP}{valor}" for clave, valor in campos)]
        # UTF-8 explícito: el formato real definirá el suyo (ver docstring del puerto).
        return ("\n".join(lineas) + "\n").encode("utf-8")

    def nombre_archivo(self, factura: FacturaCliente) -> str:
        numero = _texto(factura.numero_factura).replace(" ", "_") or "sin_numero"
        return f"BORRADOR_{numero}.txt"
