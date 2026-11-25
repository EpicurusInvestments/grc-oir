"""Lectura de un CFDI (XML) de un proveedor (Agencia/Vendedor/Afiliado) — patrón
anti-corrupción (skill `integraciones-externas`): el resto de la app nunca toca XML ni
namespaces de CFDI directamente, solo el resultado ya traducido de aquí.

Petición del usuario: al cargar el XML de una factura de proveedor, precargar
Subtotal/IVA (y de paso RFC/folio, para cuando se valide el RFC contra catálogo más
adelante — fuera de alcance de esta ronda). Es una lectura PURA de formato de archivo,
sin llamar a ningún sistema externo vivo — por eso no hace falta `port.py`/`adapter.py`
(no hay nada que intercambiar): con `parser.py` alcanza, mismo criterio que la skill
documenta para "lectura de formato" sin servicio detrás.

Nunca lanza una excepción hacia afuera por un XML malformado o que no sea CFDI — un
archivo que no se puede leer no debe tumbar la subida ni bloquear al usuario, que
siempre puede seguir capturando Subtotal/IVA a mano (`ok=False` + `motivo` legible).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

# CFDI 3.3 y 4.0 comparten los mismos atributos relevantes (`SubTotal`/`Total` en
# `Comprobante`, `TotalImpuestosTrasladados` en `Impuestos`) — solo cambia el URI del
# namespace, así que se prueban ambos en orden.
_NAMESPACES_CFDI = (
    "http://www.sat.gob.mx/cfd/4",
    "http://www.sat.gob.mx/cfd/3",
)


@dataclass(frozen=True)
class ResultadoLecturaCfdi:
    """Resultado de intentar leer un CFDI — `ok=False` nunca es un error de programa,
    es "este archivo no se pudo leer automáticamente", con un `motivo` para mostrar."""

    ok: bool
    motivo: str | None = None
    subtotal: Decimal | None = None
    iva: Decimal | None = None
    total: Decimal | None = None
    rfc_emisor: str | None = None
    folio: str | None = None


def _no_se_pudo_leer(motivo: str) -> ResultadoLecturaCfdi:
    return ResultadoLecturaCfdi(ok=False, motivo=motivo)


def _decimal(valor: str | None) -> Decimal | None:
    if valor is None:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def parsear_cfdi(contenido: bytes) -> ResultadoLecturaCfdi:
    """Lee `SubTotal`/`Total`/el IVA trasladado/RFC emisor/folio de un CFDI 3.3 o 4.0.

    El IVA se lee de `Comprobante/Impuestos/@TotalImpuestosTrasladados` (el total YA
    sumado por el emisor) — no se suman los `Traslado` por concepto a mano: un CFDI
    puede traer otros impuestos (IEPS) mezclados que no son IVA."""
    try:
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError:
        return _no_se_pudo_leer("El archivo no es un XML válido.")

    for ns in _NAMESPACES_CFDI:
        ns_map = {"cfdi": ns}
        if raiz.tag == f"{{{ns}}}Comprobante":
            comprobante = raiz
            break
    else:
        return _no_se_pudo_leer("El XML no tiene la estructura de un CFDI (Comprobante).")

    subtotal = _decimal(comprobante.get("SubTotal"))
    total = _decimal(comprobante.get("Total"))
    if subtotal is None or total is None:
        return _no_se_pudo_leer("El CFDI no trae SubTotal/Total legibles.")

    impuestos = comprobante.find("cfdi:Impuestos", ns_map)
    iva = _decimal(impuestos.get("TotalImpuestosTrasladados")) if impuestos is not None else None
    if iva is None:
        # Sin impuestos trasladados (p.ej. una factura exenta) — Subtotal/Total siguen
        # siendo válidos, el IVA se precarga en 0 y el usuario lo confirma/corrige.
        iva = Decimal("0")

    emisor = comprobante.find("cfdi:Emisor", ns_map)
    rfc_emisor = emisor.get("Rfc") if emisor is not None else None
    folio = comprobante.get("Folio")

    return ResultadoLecturaCfdi(
        ok=True,
        subtotal=subtotal,
        iva=iva,
        total=total,
        rfc_emisor=rfc_emisor,
        folio=folio,
    )
