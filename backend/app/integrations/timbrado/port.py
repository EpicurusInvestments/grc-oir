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
class DomicilioFiscal:
    """Domicilio desglosado, igual a los grupos `ExEmisorDomFiscal`/`ExReceptorDomFiscal`
    del layout del PAC (ADR-059: `Anunciante`/`EmpresaFacturadora` ya lo capturan así).
    Todos opcionales: un domicilio a medio llenar sigue siendo mejor que nada, el layout
    solo pide lo que tenga valor."""

    calle: str | None = None
    numero_exterior: str | None = None
    numero_interior: str | None = None
    colonia: str | None = None
    localidad: str | None = None
    referencia: str | None = None
    municipio: str | None = None
    estado: str | None = None
    pais: str = "MEX"
    codigo_postal: str | None = None

    #: Con estos 5 llenos ya alcanza para el layout, aunque falten NroInterior/Referencia
    #: (opcionales en cualquier dirección real). Única fuente de verdad de "completo":
    #: la usan tanto `campos_faltantes()` como el mapeo a `Ex*DomFiscal` — un domicilio a
    #: medias NUNCA se manda desglosado con huecos, cae entero al texto libre legacy.
    _CAMPOS_MINIMOS = ("calle", "colonia", "municipio", "estado", "codigo_postal")

    def esta_completo(self) -> bool:
        return all(getattr(self, campo) for campo in self._CAMPOS_MINIMOS)


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
    #: Dirección en TEXTO LIBRE (legacy, ADR-059): respaldo para registros que todavía
    #: no tienen `emisor_domicilio` desglosado. Ver `campos_faltantes()`.
    emisor_direccion: str | None = None
    #: Domicilio desglosado (ADR-059) — lo que el layout realmente pide campo por campo.
    #: `None` si `EmpresaFacturadora` todavía no lo captura así (registro viejo).
    emisor_domicilio: DomicilioFiscal | None = None

    # ── Receptor (anunciante o agencia, según facturación directa) ─────────────
    receptor_nombre: str = ""
    receptor_rfc: str = ""
    #: Igual que `emisor_direccion`: texto libre, respaldo de `receptor_domicilio`.
    receptor_direccion: str | None = None
    #: Domicilio desglosado (ADR-059). Solo se resuelve cuando el receptor de ESTA
    #: factura es el Anunciante (`Agencia` todavía no tiene domicilio estructurado).
    receptor_domicilio: DomicilioFiscal | None = None

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

    # ── Facturas relacionadas (N:N de FacturaCliente, ADR-062) ─────────────────
    #: Folios fiscales de las facturas relacionadas. Se envían todos como TipoRelacion 04
    #: — CFDI 4.0 permite varios `CfdiRelacionado` bajo un mismo tipo de relación.
    folios_fiscales_relacionados: tuple[str, ...] = ()

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
