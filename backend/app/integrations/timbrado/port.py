"""Puerto de exportación al timbrador externo (PAC) — patrón anti-corrupción.

Mismo criterio que el puerto de almacenamiento (ADR-020 → ADR-027): el dominio depende
SOLO de esta interfaz y el adaptador concreto se inyecta por configuración.

**El sistema NUNCA timbra** (ADR-002). Este puerto solo EXPORTA la información que el PAC
necesita; el folio fiscal, el XML y el PDF vuelven por captura/carga, no por aquí.

El adaptador recibe un `DatosTimbrado` con valores YA RESUELTOS —no la entidad ORM— para
que la capa de integración no consulte la base: resolver la orden, el emisor, el receptor
y las constantes fiscales es trabajo del servicio. Así el adaptador es una función pura de
datos a bytes, y se prueba sin base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class DatosTimbrado:
    """Todo lo que el layout del PAC necesita, resuelto por el servicio.

    Los campos `None` que el PAC exige se reportan por `campos_faltantes()`: hoy el modelo
    de datos no los tiene (ver la ficha de F2). Se dejan explícitos en vez de inventarlos
    porque un valor fiscal equivocado produce un CFDI que TIMBRA pero está mal.
    """

    # ── Documento ──────────────────────────────────────────────────────────────
    numero_factura: str
    fecha_emision: datetime
    fecha_factura: date
    #: Periodo transmitido (heredado de la campaña de la OrdenCliente).
    periodo_inicio: date
    periodo_fin: date
    descripcion: str
    observaciones: str | None = None

    # ── Importes ───────────────────────────────────────────────────────────────
    subtotal: Decimal = Decimal("0.00")
    iva: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    #: Tasa de IVA vigente (de configuración central, no un literal).
    tasa_iva: Decimal = Decimal("0.16")
    moneda: str = "MXN"

    # ── Emisor (EmpresaFacturadora) ────────────────────────────────────────────
    emisor_nombre: str = ""
    emisor_rfc: str = ""
    #: Dirección en TEXTO LIBRE: el modelo no la tiene desglosada y el layout sí la pide
    #: campo por campo. Ver `campos_faltantes()`.
    emisor_direccion: str | None = None

    # ── Receptor (anunciante o agencia, según facturación directa) ─────────────
    receptor_nombre: str = ""
    receptor_rfc: str = ""
    receptor_direccion: str | None = None

    # ── Referencias comerciales (OrdenCliente) ─────────────────────────────────
    orden_folio: str | None = None
    orden_numero_cliente: str | None = None
    orden_producto: str | None = None
    porcentaje_comision_agencia: Decimal | None = None
    importe_comision_agencia: Decimal | None = None
    info_cuenta_pago: str | None = None

    # ── Pago ───────────────────────────────────────────────────────────────────
    #: Clave de `ConstantesSistema` grupo MetodoPago (PUE/PPD). OJO: el layout del PAC la
    #: llama `FormaPago`, al revés de la nomenclatura del SAT.
    metodo_pago_clave: str | None = None
    #: Clave SAT de FORMA de pago (01/03/99…). El layout la llama `MedioPago`.
    forma_pago_clave: str | None = None

    # ── Sustitución de un CFDI previo (self-FK de FacturaCliente) ──────────────
    #: Folio fiscal de la factura relacionada. Se envía como TipoRelacion 04.
    folio_fiscal_relacionado: str | None = None

    # ── Constantes fiscales (catálogo `ConstantesSistema`) ─────────────────────
    # El servicio las resuelve solo si el grupo tiene UNA constante activa: con varias, la
    # elección es una decisión fiscal que nadie ha tomado y se reporta como faltante.
    serie: str | None = None
    regimen_fiscal_emisor: str | None = None
    regimen_fiscal_receptor: str | None = None
    uso_cfdi: str | None = None
    clave_prod_serv: str | None = None
    clave_unidad: str | None = None
    codigo_postal_expedicion: str | None = None

    #: Nombres de los campos que el servicio no pudo resolver, para trazabilidad.
    no_resueltos: tuple[str, ...] = field(default_factory=tuple)


class TimbradoExportPort(Protocol):
    """Exportación de una factura al formato que espera el timbrador."""

    #: Identificador del formato, para trazabilidad en logs y pruebas.
    nombre_formato: str

    def exportar(self, datos: DatosTimbrado) -> bytes:
        """Serializa la factura al archivo plano que se envía al PAC.

        Devuelve BYTES, no `str`: el layout fija una codificación concreta y esa decisión
        pertenece al adaptador, no al dominio.
        """
        ...

    def nombre_archivo(self, datos: DatosTimbrado) -> str:
        """Nombre sugerido del archivo exportado."""
        ...

    def campos_faltantes(self, datos: DatosTimbrado) -> list[str]:
        """Campos que el PAC exige y que NO se pudieron llenar.

        Lista vacía = el archivo está completo. Con elementos, el archivo se genera igual
        (para poder revisarlo) pero el PAC lo rechazaría: quien lo descargue debe saberlo.
        """
        ...
