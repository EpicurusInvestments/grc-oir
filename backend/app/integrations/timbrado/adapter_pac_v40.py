"""Adaptador REAL del archivo plano del PAC (layout V40).

Reconstruido a partir del ejemplo de producción
`docs/referencias/ejemplo_archivo_plano_FACTURA_33_NPG_D_28_11757_V40 (2).txt`.

**Es un ejemplo, no una especificación.** Lo que sigue está MEDIDO sobre ese archivo, no
inventado, pero conviene saber qué es dato duro y qué es inferencia de una sola muestra:

MEDIDO Y SEGURO
- Estructura: `XXXINICIO`, 20 secciones `================ Nombre`, `XXXFINDETA` cerrando el
  detalle, `xxxFinRelaciones` cerrando documentos relacionados, `XXXFINDO` al final.
- Saltos de línea **CRLF**.
- Clave del campo a la izquierda y valor en la **columna 17**… salvo en `AGREGADOS`, donde
  es la **19**. Verificado en 168 líneas: 17 aparece 163 veces y 19 seis veces (todas en
  AGREGADOS). Las pocas excepciones del ejemplo son líneas con valor VACÍO y tabuladores
  sueltos — ruido del generador, no una regla.
- El detalle es posicional, con anchos fijos por columna (ver `_COLUMNAS_DETALLE`).

INFERIDO DE UNA SOLA MUESTRA (documentado como riesgo)
- Los anchos del detalle salen de una única fila. Una prueba regenera esa fila
  BYTE A BYTE desde sus valores: si el layout se rompe, falla.
- Que los campos vacíos puedan ir vacíos (el ejemplo trae ~120 así).
- Si un campo es obligatorio o no. Lo que el modelo no puede llenar se reporta en
  `campos_faltantes()` en vez de rellenarse con algo plausible.

CODIFICACIÓN — punto abierto importante
El ejemplo llegó **ya corrupto**: contiene 3 veces U+FFFD donde iban `Ó` y `ñ`
(«MENCI?N», «Campa?a»), señal de que el original NO era UTF-8 y alguien lo convirtió mal.
Los archivos planos de los PAC mexicanos suelen ser **CP1252/Latin-1**, y ese es el valor
por defecto (`TIMBRADO_ENCODING`). Si un carácter no cabe en la codificación elegida, se
lanza un error claro en vez de escribir basura: mejor fallar que mandar un nombre fiscal
mutilado. **Confirmar con el PAC antes de producción.**
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.integrations.timbrado.port import DatosTimbrado, DomicilioFiscal

#: Fin de línea del layout (medido en el ejemplo).
CRLF = "\r\n"

#: Columna donde empieza el valor. `AGREGADOS` es la excepción (medida, no supuesta).
_COL_VALOR = 17
_COL_VALOR_AGREGADOS = 19

#: Marcas de control del archivo.
_INICIO = "XXXINICIO"
_FIN_DETALLE = "XXXFINDETA"
_FIN_RELACIONES = "xxxFinRelaciones"
_FIN_DOCUMENTO = "XXXFINDO"

#: Cabecera literal del detalle, copiada tal cual del ejemplo (los nombres de columna y su
#: posición son parte del formato: el PAC las espera ahí).
_CABECERA_DETALLE = (
    "                    CONCEPTO                     CANT      U.MED          COSTO   "
    "      IMPORTE                   ClaveProdServ  ClaveUnidad    Impuesto2      "
    "TipoFact2      TasaOCuot2     Importe2       BaseImp2       ObjetoImp      "
    "RfcCuentaTerceros         NombreACuentaterceros            RegFisACuentaTerc     "
    "  DomFisCuentaTer               "
)

#: (nombre, inicio, ancho, alineación). `derecha` = el valor termina en `inicio+ancho_util`
#: y el resto es relleno; así se reproduce exactamente la fila del ejemplo.
_COLUMNAS_DETALLE: tuple[tuple[str, int, int, str, int], ...] = (
    ("concepto", 0, 49, "izquierda", 0),
    ("cantidad", 49, 10, "derecha", 3),
    ("unidad", 59, 15, "derecha", 4),
    ("costo", 74, 14, "derecha", 10),
    ("importe", 88, 26, "derecha", 11),
    ("clave_prod_serv", 114, 15, "izquierda", 0),
    ("clave_unidad", 129, 15, "izquierda", 0),
    ("impuesto2", 144, 15, "izquierda", 0),
    ("tipo_fact2", 159, 15, "izquierda", 0),
    ("tasa_o_cuota2", 174, 15, "izquierda", 0),
    ("importe2", 189, 15, "izquierda", 0),
    ("base_imp2", 204, 15, "izquierda", 0),
    ("objeto_imp", 219, 15, "izquierda", 0),
    ("rfc_cuenta_terceros", 234, 26, "izquierda", 0),
    ("nombre_a_cuenta_terceros", 260, 33, "izquierda", 0),
    ("reg_fis_a_cuenta_terc", 293, 24, "izquierda", 0),
    ("dom_fis_cuenta_ter", 317, 30, "izquierda", 0),
)

#: Secciones y sus campos, EN ORDEN. Transcrito del ejemplo; una prueba compara esta
#: estructura contra el archivo de referencia, así que una errata de transcripción falla.
_LAYOUT: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "IdDoc",
        (
            "NumeroInterno", "NroAprob", "AnoAprob", "Tipo", "Serie", "Folio", "Estado",
            "FechaEmis", "FormaPago", "MedioPago", "CondPago", "TermPagoCdg",
            "TermPagoDias", "FechaVenc", "Exportacion",
        ),
    ),
    (
        "ExEmisor",
        (
            "RFCEmisor", "NmbEmisor", "CdgGLNEmisor", "TpoCdgIntEmisor1", "CdgIntEmisor1",
            "TpoCdgIntEmisor2", "CdgIntEmisor2", "CdgSucursal", "Sucursal", "CdgVendedor",
        ),
    ),
    (
        "ExEmisorDomFiscal",
        (
            "Calle", "NroExterior", "NroInterior", "Colonia", "Localidad", "Referencia",
            "Municipio", "Estado", "Pais", "CodigoPostal", "GLN",
        ),
    ),
    (
        "ExEmisorLugarExped",
        (
            "Calle", "NroExterior", "NroInterior", "Colonia", "Localidad", "Referencia",
            "Municipio", "Estado", "Pais", "CodigoPostal", "GLN",
        ),
    ),
    (
        "ExReceptor",
        (
            "RFCRecep", "NmbRecep", "RegimenFiscal", "CdgGLNRecep", "TpoCdgIntRecep1",
            "CdgIntRecep1", "CdgSucursal", "Sucursal", "Contacto",
        ),
    ),
    (
        "ExReceptorDomFiscal",
        (
            "Calle", "NroExterior", "NroInterior", "Colonia", "Localidad", "Referencia",
            "Municipio", "Estado", "Pais", "CodigoPostal", "GLN",
        ),
    ),
    (
        "ExReceptorLugarRecep",
        (
            "Calle", "NroExterior", "NroInterior", "Colonia", "Localidad", "Referencia",
            "Municipio", "Estado", "Pais", "CodigoPostal", "GLN",
        ),
    ),
    ("Detalle", ()),  # posicional: se arma aparte
    (
        "Totales",
        (
            "Moneda", "FctConv", "Indlista", "TipoLista", "SubTotal", "MntDcto", "PctDcto",
            "MntRcgo", "PctRcgo", "MntBase", "MntImp", "MntRet", "VlrPagar", "VlrPalabras",
        ),
    ),
    (
        "ExImpuestos",
        (
            "TipoImp1", "TasaImp1", "MontoImp1", "TipoImp2", "TasaImp2", "MontoImp2",
            "TipoFact1", "TipoFact2", "Baseiva1", "Baseiva2",
        ),
    ),
    (
        "ExRetenciones",
        (
            "TipoRet1", "TasaRet1", "MontoRet1", "TipoRet2", "TasaRet2", "MontoRet2",
            "TipoFact1", "TipoFact2",
        ),
    ),
    (
        "DscRcgGlobal",
        (
            "TpoMov1", "CodigoDR1", "GlosaDR1", "TpoValor1", "ValorDR1", "TpoMov2",
            "CodigoDR2", "GlosaDR2", "TpoValor2", "ValorDR2",
        ),
    ),
    (
        "Addendas",
        (
            "IdAreaOld", "IdArea", "IdRevision", "Banderas", "ReceiverIDs",
            "SenderIDGeneric", "SenderID", "SenderIDCorvi", "EmisorRI", "Addendas1",
            "Addendas2", "Addendas3", "Addendas4", "Addendas5", "Addendas6",
        ),
    ),
    (
        "Personalizados",
        (
            "Conducto", "Campaña", "Solicitud", "TipoMovimiento", "TipoFactura",
            "PeriodoTrans", "Descripcion1", "Descripcion2", "Descripcion3", "Descripcion4",
            "Descripcion5", "DomConducto", "ColConducto", "EdoConducto", "DelConducto",
            "CpConducto", "Convenio", "Orden", "Email", "TelEmisor", "PorcAgencia",
            "ImpAgencia",
        ),
    ),
    (
        "ContactoEmisor",
        (
            "Tipo1", "Nombre1", "Descripcion1", "eMail1", "Telefono1", "Extension1", "Fax1",
            "Tipo2", "Nombre2", "Descripcion2", "eMail2", "Telefono2", "Extension2", "Fax2",
        ),
    ),
    (
        "ContactoReceptor",
        ("Tipo1", "Nombre1", "Descripcion1", "eMail1", "Telefono1", "Extension1", "Fax1"),
    ),
    (
        "AGREGADOS",
        (
            "Regimen", "MedioPago", "NumCtaPago", "LugarExpedicion", "Confirmacion",
            "Residencia Fiscal", "NumRegIDTrib", "UsoCFDI",
        ),
    ),
    ("Documentos Relacionados", ()),  # posicional
    ("FINAGREGADOS", ()),
    ("Referencia", ()),
)

#: Constantes SAT que se derivan de la tasa de IVA, no de una decisión de negocio:
#: 002 = IVA, "Tasa" = tipo de factor, 02 = "Sí objeto de impuesto".
_IMPUESTO_IVA = "002"
_TIPO_FACTOR_TASA = "Tasa"
_OBJETO_IMPUESTO_SI = "02"

#: Valores fijos observados en el ejemplo para el tipo de documento (factura de ingreso).
_TIPO_DOCUMENTO = "33"
_ESTADO_ORIGINAL = "ORIGINAL"
_EXPORTACION_NO_APLICA = "01"
#: TipoRelacion 04 = "Sustitución de los CFDI previos" (catálogo del SAT).
_TIPO_RELACION_SUSTITUCION = "04"

#: Campos que el PAC exige y que HOY el modelo no puede llenar. Se reportan, no se
#: inventan: un valor fiscal plausible pero equivocado produce un CFDI que timbra mal.
_OBLIGATORIOS = {
    "serie": "IdDoc.Serie",
    "regimen_fiscal_receptor": "ExReceptor.RegimenFiscal",
    "regimen_fiscal_emisor": "AGREGADOS.Regimen",
    "uso_cfdi": "AGREGADOS.UsoCFDI",
    "clave_prod_serv": "Detalle.ClaveProdServ",
    "clave_unidad": "Detalle.ClaveUnidad / U.MED",
    "codigo_postal_expedicion": "AGREGADOS.LugarExpedicion",
    "forma_pago_clave": "AGREGADOS.MedioPago",
}

def _domicilio_incompleto(dom: DomicilioFiscal | None, legacy: str | None) -> bool:
    """`True` si NI el domicilio desglosado (ADR-059) NI el texto libre legacy alcanzan
    para llenar el bloque `Ex*DomFiscal` del layout."""
    if dom is not None and dom.esta_completo():
        return False
    return not legacy


class ErrorCodificacionTimbrado(ValueError):
    """Un carácter no cabe en la codificación del layout. Se falla en vez de mutilarlo."""


def _texto(valor: object) -> str:
    """Normaliza a una línea. El layout es posicional: un salto interno lo rompería."""
    if valor is None:
        return ""
    return str(valor).replace("\r", " ").replace("\n", " ").rstrip()


def _monto(valor: Decimal | None) -> str:
    return f"{valor:.2f}" if valor is not None else ""


def _domicilio_valores(
    prefijo: str, dom: DomicilioFiscal | None, legacy: str | None
) -> dict[tuple[str, str], str]:
    """Entradas de un bloque `Ex*DomFiscal`. Con domicilio desglosado COMPLETO (ADR-059,
    `esta_completo()` — mismo criterio que `campos_faltantes()`) llena Calle/NroExterior/
    …/CodigoPostal de verdad; si está vacío O a medias, cae al apaño anterior — el texto
    libre completo va en `Referencia` (visible, no una equivalencia real; nunca se manda
    un domicilio desglosado con huecos)."""
    if dom is not None and dom.esta_completo():
        return {
            (prefijo, "Calle"): _texto(dom.calle),
            (prefijo, "NroExterior"): _texto(dom.numero_exterior),
            (prefijo, "NroInterior"): _texto(dom.numero_interior),
            (prefijo, "Colonia"): _texto(dom.colonia),
            (prefijo, "Localidad"): _texto(dom.localidad),
            (prefijo, "Referencia"): _texto(dom.referencia),
            (prefijo, "Municipio"): _texto(dom.municipio),
            (prefijo, "Estado"): _texto(dom.estado),
            (prefijo, "Pais"): _texto(dom.pais) or "MEX",
            (prefijo, "CodigoPostal"): _texto(dom.codigo_postal),
        }
    return {
        (prefijo, "Referencia"): _texto(legacy),
        (prefijo, "Pais"): "MEX",
    }


def _fecha_hora(valor: datetime) -> str:
    return valor.strftime("%Y-%m-%d %H:%M:%S")


def _periodo(inicio: date, fin: date) -> str:
    """`PeriodoTrans` del ejemplo: '14/04/2026  Al  30/04/2026' (dos espacios)."""
    return f"{inicio:%d/%m/%Y}  Al  {fin:%d/%m/%Y}"


def _trocear(texto: str, ancho: int, partes: int) -> list[str]:
    """Parte un texto largo en N tramos de ancho fijo (`Descripcion1..5` del ejemplo).

    El ejemplo corta a la mitad de una palabra («…EN LAS EMI» / «SORAS ALFA…»), así que el
    corte es por LONGITUD, no por palabra: se replica ese comportamiento.
    """
    return [texto[i * ancho : (i + 1) * ancho] for i in range(partes)]


class TimbradoExportPacV40:
    """Escribe el archivo plano V40 del PAC."""

    nombre_formato = "pac-v40"

    def __init__(self, encoding: str = "cp1252") -> None:
        self._encoding = encoding

    # ── API del puerto ────────────────────────────────────────────────────────
    def campos_faltantes(self, datos: DatosTimbrado) -> list[str]:
        faltantes = [
            etiqueta
            for atributo, etiqueta in _OBLIGATORIOS.items()
            if not getattr(datos, atributo, None)
        ]
        if _domicilio_incompleto(datos.emisor_domicilio, datos.emisor_direccion):
            faltantes.append("ExEmisorDomFiscal.* (domicilio del emisor)")
        if _domicilio_incompleto(datos.receptor_domicilio, datos.receptor_direccion):
            faltantes.append("ExReceptorDomFiscal.* (domicilio del receptor)")
        return faltantes

    def nombre_archivo(self, datos: DatosTimbrado) -> str:
        serie = _texto(datos.serie) or "SN"
        numero = _texto(datos.numero_factura).replace(" ", "_") or "SIN_NUMERO"
        return f"FACTURA_{_TIPO_DOCUMENTO}_{serie}_{numero}.txt"

    def exportar(self, datos: DatosTimbrado) -> bytes:
        valores = self._valores(datos)
        lineas: list[str] = [_INICIO]

        for seccion, campos in _LAYOUT:
            lineas.append(f"================ {seccion}")
            if seccion == "Detalle":
                lineas.extend(self._detalle(datos))
                continue
            if seccion == "Documentos Relacionados":
                lineas.extend(self._relacionados(datos))
                continue
            ancho = _COL_VALOR_AGREGADOS if seccion == "AGREGADOS" else _COL_VALOR
            for campo in campos:
                valor = valores.get((seccion, campo), "")
                lineas.append(f"{campo.ljust(ancho)}{valor}")
            if seccion in ("ExReceptorLugarRecep", "Totales", "FINAGREGADOS"):
                lineas.append("")  # líneas en blanco que el ejemplo trae entre secciones

        lineas.append(_FIN_DOCUMENTO)
        texto = CRLF.join(lineas) + CRLF
        return self._codificar(texto)

    # ── Armado ────────────────────────────────────────────────────────────────
    def _codificar(self, texto: str) -> bytes:
        try:
            return texto.encode(self._encoding)
        except UnicodeEncodeError as exc:
            fragmento = texto[max(0, exc.start - 30) : exc.end + 30].replace(CRLF, " ⏎ ")
            raise ErrorCodificacionTimbrado(
                f"El carácter {texto[exc.start:exc.end]!r} no existe en la codificación "
                f"'{self._encoding}' del layout del PAC. Contexto: …{fragmento}…"
            ) from exc

    def _detalle(self, datos: DatosTimbrado) -> list[str]:
        """Una sola línea de concepto: el modelo factura la orden completa, no por partida."""
        celdas = {
            "concepto": _texto(datos.descripcion),
            "cantidad": "1",
            "unidad": _texto(datos.clave_unidad),
            "costo": _monto(datos.subtotal),
            "importe": _monto(datos.subtotal),
            "clave_prod_serv": _texto(datos.clave_prod_serv),
            "clave_unidad": _texto(datos.clave_unidad),
            "impuesto2": _IMPUESTO_IVA,
            "tipo_fact2": _TIPO_FACTOR_TASA,
            "tasa_o_cuota2": f"{datos.tasa_iva:.6f}",
            "importe2": _monto(datos.iva),
            "base_imp2": _monto(datos.subtotal),
            "objeto_imp": _OBJETO_IMPUESTO_SI,
        }
        return [_CABECERA_DETALLE, self.formatear_detalle(celdas), "", _FIN_DETALLE]

    @staticmethod
    def formatear_detalle(celdas: dict[str, str]) -> str:
        """Arma la línea posicional. Público a propósito: la prueba de regresión regenera
        con esto la fila del archivo de referencia y la compara byte a byte."""
        fila = ""
        for nombre, inicio, ancho, alineacion, ancho_util in _COLUMNAS_DETALLE:
            valor = celdas.get(nombre, "")
            if alineacion == "derecha":
                # Alineado a la DERECHA dentro de un ancho útil y luego rellenado hasta
                # el ancho de la columna: así se reproduce el ejemplo exactamente.
                celda = valor.rjust(ancho_util).ljust(ancho)
            else:
                celda = valor.ljust(ancho)
            fila = fila.ljust(inicio) + celda[:ancho]
        return fila

    def _relacionados(self, datos: DatosTimbrado) -> list[str]:
        cabecera = "TipoRelacion".ljust(_COL_VALOR) + "UUID".ljust(36)
        filas = [cabecera]
        for folio in datos.folios_fiscales_relacionados:
            filas.append(_TIPO_RELACION_SUSTITUCION.ljust(_COL_VALOR) + _texto(folio))
        filas.extend(["", _FIN_RELACIONES])
        return filas

    def _valores(self, d: DatosTimbrado) -> dict[tuple[str, str], str]:
        """Mapea el dominio al layout. Lo que no se puede llenar va VACÍO, nunca inventado."""
        descripciones = _trocear(_texto(d.descripcion), 100, 5)
        v: dict[tuple[str, str], str] = {
            # ── IdDoc ──
            ("IdDoc", "NumeroInterno"): _texto(d.numero_factura),
            ("IdDoc", "Tipo"): _TIPO_DOCUMENTO,
            ("IdDoc", "Serie"): _texto(d.serie),
            ("IdDoc", "Folio"): _texto(d.numero_factura),
            ("IdDoc", "Estado"): _ESTADO_ORIGINAL,
            ("IdDoc", "FechaEmis"): _fecha_hora(d.fecha_emision),
            # El layout llama `FormaPago` a lo que el SAT llama MÉTODO de pago (PUE/PPD)
            # y `MedioPago` a la FORMA (01/03/99). Nomenclatura invertida: se respeta la
            # del PAC, que es quien lee el archivo.
            ("IdDoc", "FormaPago"): _texto(d.metodo_pago_clave),
            ("IdDoc", "MedioPago"): _texto(d.forma_pago_clave),
            ("IdDoc", "FechaVenc"): _fecha_hora(d.fecha_emision),
            ("IdDoc", "Exportacion"): _EXPORTACION_NO_APLICA,
            # ── Emisor ──
            ("ExEmisor", "RFCEmisor"): _texto(d.emisor_rfc),
            ("ExEmisor", "NmbEmisor"): _texto(d.emisor_nombre),
            **_domicilio_valores("ExEmisorDomFiscal", d.emisor_domicilio, d.emisor_direccion),
            ("ExEmisorLugarExped", "CodigoPostal"): _texto(d.codigo_postal_expedicion),
            ("ExEmisorLugarExped", "Pais"): "MEX",
            # ── Receptor ──
            ("ExReceptor", "RFCRecep"): _texto(d.receptor_rfc),
            ("ExReceptor", "NmbRecep"): _texto(d.receptor_nombre),
            ("ExReceptor", "RegimenFiscal"): _texto(d.regimen_fiscal_receptor),
            **_domicilio_valores(
                "ExReceptorDomFiscal", d.receptor_domicilio, d.receptor_direccion
            ),
            # ── Totales ──
            ("Totales", "Moneda"): _texto(d.moneda),
            ("Totales", "FctConv"): "1",
            ("Totales", "SubTotal"): _monto(d.subtotal),
            ("Totales", "MntBase"): _monto(d.subtotal),
            ("Totales", "MntImp"): _monto(d.iva),
            ("Totales", "VlrPagar"): _monto(d.total),
            # `VlrPalabras` (importe con letra) se deja vacío: el ejemplo lo trae, pero
            # convertir a letras es una función de negocio que no existe todavía y que el
            # PAC normalmente recalcula. Se reporta como pendiente en la ficha, no aquí,
            # porque no bloquea el timbrado.
            # ── Impuestos (IVA trasladado) ──
            ("ExImpuestos", "TipoImp2"): _IMPUESTO_IVA,
            ("ExImpuestos", "TasaImp2"): f"{d.tasa_iva:.6f}",
            ("ExImpuestos", "MontoImp2"): _monto(d.iva),
            ("ExImpuestos", "TipoFact2"): _TIPO_FACTOR_TASA,
            ("ExImpuestos", "Baseiva1"): _monto(d.subtotal),
            # ── Personalizados (referencias comerciales de OIR) ──
            ("Personalizados", "Campaña"): _texto(d.orden_producto),
            ("Personalizados", "Solicitud"): _texto(d.orden_numero_cliente),
            ("Personalizados", "PeriodoTrans"): _periodo(d.periodo_inicio, d.periodo_fin),
            ("Personalizados", "Orden"): _texto(d.orden_folio),
            ("Personalizados", "PorcAgencia"): (
                f"{d.porcentaje_comision_agencia:.2f}"
                if d.porcentaje_comision_agencia is not None
                else ""
            ),
            ("Personalizados", "ImpAgencia"): _monto(d.importe_comision_agencia),
            # ── AGREGADOS ──
            ("AGREGADOS", "Regimen"): _texto(d.regimen_fiscal_emisor),
            ("AGREGADOS", "MedioPago"): _texto(d.forma_pago_clave),
            ("AGREGADOS", "NumCtaPago"): _texto(d.info_cuenta_pago),
            ("AGREGADOS", "LugarExpedicion"): _texto(d.codigo_postal_expedicion),
            ("AGREGADOS", "UsoCFDI"): _texto(d.uso_cfdi),
        }
        for i, tramo in enumerate(descripciones, start=1):
            v[("Personalizados", f"Descripcion{i}")] = tramo
        return v
