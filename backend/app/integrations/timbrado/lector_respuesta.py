"""Lectura del XML YA TIMBRADO que regresa el PAC — Timbre Fiscal Digital (ADR-296,
petición del usuario). Patrón anti-corrupción (skill `integraciones-externas`), mismo
criterio que `app/integrations/facturas_proveedor/parser.py`: una lectura PURA de
formato de archivo, sin llamar a ningún sistema externo vivo.

Distinto de ese otro parser: aquel lee `Comprobante/@SubTotal`/`@Total` (factura de
PROVEEDOR, Agencia/Vendedor/Afiliado); este lee el complemento `TimbreFiscalDigital`
que el PAC AGREGA al CFDI al timbrarlo — para precargar "Registrar respuesta del
timbrado" (Factura, Nota de Crédito; Complemento de Pago todavía no existe) con lo
que el usuario de otro modo tendría que copiar a mano del XML.

Nunca lanza una excepción hacia afuera por un XML que no se pueda leer — el usuario
siempre puede seguir capturando los 3 campos a mano (`ok=False` + `motivo` legible).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from xml.etree import ElementTree

# Mismas 2 versiones de CFDI que el parser de proveedor — ver ahí el porqué.
_NAMESPACES_CFDI = (
    "http://www.sat.gob.mx/cfd/4",
    "http://www.sat.gob.mx/cfd/3",
)
#: Se busca por NOMBRE LOCAL del nodo, no por el URI exacto del namespace de TFD: el
#: SAT ha publicado más de una versión de ese namespace (1.0/1.1) y lo único que
#: importa aquí son sus 3 atributos, no cuál versión exacta trae el archivo.
_TFD_TAG = "TimbreFiscalDigital"


@dataclass(frozen=True)
class ResultadoLecturaTimbre:
    """`ok=False` nunca es un error de programa, es "este archivo no se pudo leer
    automáticamente", con un `motivo` para mostrar — igual que `ResultadoLecturaCfdi`."""

    ok: bool
    motivo: str | None = None
    folio_fiscal_sat: str | None = None
    fecha_timbrado: date | None = None
    no_certificado_sat: str | None = None


def _no_se_pudo_leer(motivo: str) -> ResultadoLecturaTimbre:
    return ResultadoLecturaTimbre(ok=False, motivo=motivo)


def parsear_timbre_fiscal(contenido: bytes) -> ResultadoLecturaTimbre:
    """Lee `UUID`/`FechaTimbrado`/`NoCertificadoSAT` del Timbre Fiscal Digital de un
    CFDI 3.3 o 4.0 ya timbrado."""
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

    complemento = comprobante.find("cfdi:Complemento", ns_map)
    if complemento is None:
        return _no_se_pudo_leer("El CFDI no trae Complemento — ¿ya está timbrado?")

    tfd = next(
        (hijo for hijo in complemento if hijo.tag.rpartition("}")[2] == _TFD_TAG), None
    )
    if tfd is None:
        return _no_se_pudo_leer(
            "El Complemento no trae Timbre Fiscal Digital — ¿ya está timbrado?"
        )

    uuid_ = tfd.get("UUID")
    fecha_cruda = tfd.get("FechaTimbrado")
    if not uuid_ or not fecha_cruda:
        return _no_se_pudo_leer("El Timbre Fiscal Digital no trae UUID/FechaTimbrado legibles.")

    try:
        fecha = datetime.fromisoformat(fecha_cruda).date()
    except ValueError:
        return _no_se_pudo_leer(f"FechaTimbrado con formato inesperado: {fecha_cruda!r}.")

    return ResultadoLecturaTimbre(
        ok=True,
        folio_fiscal_sat=uuid_,
        fecha_timbrado=fecha,
        no_certificado_sat=tfd.get("NoCertificadoSAT"),
    )
