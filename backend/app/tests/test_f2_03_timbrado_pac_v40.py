"""Pruebas del adaptador real del archivo plano del PAC (layout V40).

La prueba que de verdad importa es `test_reproduce_la_fila_del_archivo_de_referencia`:
regenera la línea de detalle del ejemplo de producción **byte a byte** desde sus valores.
Los anchos del detalle se midieron sobre una sola fila, así que esa comparación es la
única evidencia dura de que el layout está bien; si alguien lo toca, falla.

`test_estructura_igual_a_la_referencia` hace lo propio con las 20 secciones y sus campos:
detecta una errata de transcripción sin que nadie tenga que revisarla a ojo.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.integrations.timbrado.adapter_pac_v40 import (
    CRLF,
    ErrorCodificacionTimbrado,
    TimbradoExportPacV40,
)
from app.integrations.timbrado.port import DatosTimbrado, DomicilioFiscal

REFERENCIA = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "referencias"
    / "ejemplo_archivo_plano_FACTURA_33_NPG_D_28_11757_V40 (2).txt"
)


def _lineas_referencia() -> list[str]:
    return open(REFERENCIA, encoding="utf-8", newline="").read().split(CRLF)


def _estructura(lineas: list[str]) -> list[tuple[str, list[str]]]:
    """Secciones y campos, con la gramática REAL del layout.

    La clave se separa del valor por **dos o más espacios**, no por uno. Es la única regla
    que explica las dos rarezas del archivo de referencia a la vez:
    - existe un campo llamado `Residencia Fiscal`, con un espacio DENTRO del nombre;
    - `UsoCFDI` trae su valor en la columna 13 mientras el resto de `AGREGADOS` usa la 19.
    Con esa regla ambos casos se leen bien, y el PAC puede tolerar el desalineado que el
    propio generador del ejemplo produjo.

    Los nombres se comparan sin acentos: el archivo llegó corrupto y trae `Campa?a` (con
    U+FFFD) donde el layout real dice `Campaña`.
    """
    salida: list[tuple[str, list[str]]] = []
    seccion: str | None = None
    for ln in lineas:
        if ln.startswith("================"):
            seccion = ln[len("================") :].strip()
            salida.append((seccion, []))
            continue
        if seccion in (None, "Detalle", "Documentos Relacionados"):
            continue
        if not ln.strip() or ln.startswith(("XXX", "xxx")):
            continue
        clave = re.split(r"[ 	]{2,}", ln.strip(), maxsplit=1)[0]
        clave = "".join(c for c in clave if c.isascii())  # normaliza acentos y U+FFFD
        if clave:
            salida[-1][1].append(clave)
    return salida


def _datos_completos(**extra: object) -> DatosTimbrado:
    base = {
        "numero_factura": "A-1041",
        "fecha_emision": datetime(2026, 6, 4, 15, 6, 48),
        "fecha_factura": date(2026, 6, 4),
        "periodo_inicio": date(2026, 4, 14),
        "periodo_fin": date(2026, 4, 30),
        "descripcion": "Servicios de transmisión publicitaria",
        "subtotal": Decimal("101209.10"),
        "iva": Decimal("16193.46"),
        "total": Decimal("117402.56"),
        "emisor_nombre": "RADIO PUBLICIDAD XHMEXICO",
        "emisor_rfc": "RPX200812C8A",
        "emisor_direccion": "AV. CONSTITUYENTES 1154, CDMX",
        "receptor_nombre": "TULOTERO MEXICO",
        "receptor_rfc": "TME16062728A",
        "receptor_direccion": "IGNACIO RAMIREZ 20, CDMX",
        "orden_folio": "OC-2025-0046",
        "orden_numero_cliente": "298231",
        "orden_producto": "MENCION TULOTERO",
        "metodo_pago_clave": "PPD",
        "info_cuenta_pago": "NO IDENTIFICADO",
        "serie": "D",
        "regimen_fiscal_emisor": "601",
        "regimen_fiscal_receptor": "601",
        "uso_cfdi": "G03",
        "clave_prod_serv": "82101601",
        "clave_unidad": "E48",
        "codigo_postal_expedicion": "11950",
        "forma_pago_clave": "99",
    }
    base.update(extra)
    return DatosTimbrado(**base)  # type: ignore[arg-type]


@pytest.fixture
def datos() -> DatosTimbrado:
    """Como los llenaría HOY el sistema: sin las constantes fiscales que no tiene."""
    return DatosTimbrado(
        numero_factura="A-1041",
        fecha_emision=datetime(2026, 6, 4, 15, 6, 48),
        fecha_factura=date(2026, 6, 4),
        periodo_inicio=date(2026, 4, 14),
        periodo_fin=date(2026, 4, 30),
        descripcion="Servicios de transmisión publicitaria",
        subtotal=Decimal("101209.10"),
        iva=Decimal("16193.46"),
        total=Decimal("117402.56"),
        emisor_nombre="RADIO PUBLICIDAD XHMEXICO",
        emisor_rfc="RPX200812C8A",
        emisor_direccion="AV. CONSTITUYENTES 1154, CDMX",
        receptor_nombre="TULOTERO MEXICO",
        receptor_rfc="TME16062728A",
        receptor_direccion="IGNACIO RAMIREZ 20, CDMX",
        orden_folio="OC-2025-0046",
        orden_numero_cliente="298231",
        orden_producto="MENCION TULOTERO",
        metodo_pago_clave="PPD",
    )


# ── La evidencia dura del layout ──────────────────────────────────────────────
def test_reproduce_la_fila_del_archivo_de_referencia() -> None:
    """Regenera la línea de detalle del ejemplo real, carácter por carácter."""
    lineas = _lineas_referencia()
    fila_real = lineas[lineas.index("================ Detalle") + 2]

    # El acento de MENCIÓN llegó ya corrupto en el archivo: se toma tal cual, porque lo
    # que se compara aquí es el LAYOUT, no el texto.
    fila_generada = TimbradoExportPacV40.formatear_detalle(
        {
            "concepto": fila_real[:49].rstrip(),
            "cantidad": "1",
            "unidad": "E48",
            "costo": "101209.10",
            "importe": "101209.10",
            "clave_prod_serv": "82101601",
            "clave_unidad": "E48",
            "impuesto2": "002",
            "tipo_fact2": "Tasa",
            "tasa_o_cuota2": "0.160000",
            "importe2": "16193.46",
            "base_imp2": "101209.10",
            "objeto_imp": "02",
        }
    )
    assert fila_generada == fila_real


def test_estructura_igual_a_la_referencia(datos: DatosTimbrado) -> None:
    """Mismas secciones, en el mismo orden, con los mismos campos y en el mismo orden."""
    generado = TimbradoExportPacV40().exportar(datos).decode("cp1252").split(CRLF)
    assert _estructura(generado) == _estructura(_lineas_referencia())


def test_marcas_de_control_y_fin_de_linea(datos: DatosTimbrado) -> None:
    crudo = TimbradoExportPacV40().exportar(datos)
    texto = crudo.decode("cp1252")
    assert texto.startswith("XXXINICIO" + CRLF)
    assert texto.rstrip(CRLF).endswith("XXXFINDO")
    for marca in ("XXXFINDETA", "xxxFinRelaciones"):
        assert marca in texto
    # CRLF en todo el archivo: ni un solo LF suelto.
    assert b"\n" in crudo and crudo.count(b"\n") == crudo.count(b"\r\n")


def test_la_clave_va_en_la_columna_17_y_19_en_agregados() -> None:
    """La columna del valor es 17 en todas las secciones y 19 en AGREGADOS (medido).

    Se exporta con TODOS los campos llenos: una línea sin valor no dice nada sobre dónde
    empieza la columna.
    """
    lineas = TimbradoExportPacV40().exportar(_datos_completos()).decode("cp1252").split(CRLF)
    seccion, revisadas = None, 0
    for ln in lineas:
        if ln.startswith("================"):
            seccion = ln[len("================") :].strip()
            continue
        if seccion in (None, "Detalle", "Documentos Relacionados") or not ln.strip():
            continue
        if ln.startswith(("XXX", "xxx")):
            continue
        ancho = 19 if seccion == "AGREGADOS" else 17
        if ln[ancho:].strip():
            # El valor arranca EXACTAMENTE en la columna: ni un espacio de más.
            assert not ln[ancho:].startswith(" "), (seccion, ln)
            assert ln[:ancho].strip(), (seccion, ln)
            revisadas += 1
    assert revisadas > 20  # se ejercitaron campos de varias secciones


# ── Mapeo del dominio ─────────────────────────────────────────────────────────
def test_mapea_los_datos_de_la_factura(datos: DatosTimbrado) -> None:
    texto = TimbradoExportPacV40().exportar(datos).decode("cp1252")
    assert "RFCEmisor        RPX200812C8A" in texto
    assert "RFCRecep         TME16062728A" in texto
    assert "SubTotal         101209.10" in texto
    assert "MntImp           16193.46" in texto
    assert "VlrPagar         117402.56" in texto
    # El layout llama `FormaPago` al MÉTODO de pago del SAT (PUE/PPD).
    assert "FormaPago        PPD" in texto
    # Periodo transmitido con el formato del ejemplo (dos espacios alrededor de "Al").
    assert "PeriodoTrans     14/04/2026  Al  30/04/2026" in texto
    assert "Orden            OC-2025-0046" in texto


def test_documento_relacionado_solo_si_sustituye_a_otro(datos: DatosTimbrado) -> None:
    sin_relacion = TimbradoExportPacV40().exportar(datos).decode("cp1252")
    assert "04               " not in sin_relacion

    uuid_previo = "71c9ab6e-0018-4010-9f6f-5b1c80aa8540"
    con_relacion = (
        TimbradoExportPacV40()
        .exportar(_datos_completos(folios_fiscales_relacionados=(uuid_previo,)))
        .decode("cp1252")
    )
    # TipoRelacion 04 = "Sustitución de los CFDI previos".
    assert f"04               {uuid_previo}" in con_relacion


def test_documento_relacionado_admite_varios_uuid(datos: DatosTimbrado) -> None:
    """ADR-062: selección múltiple en "Nueva factura" → una fila por UUID, mismo
    TipoRelacion 04 — CFDI 4.0 admite varios `CfdiRelacionado` bajo un mismo tipo."""
    uuid_a = "71c9ab6e-0018-4010-9f6f-5b1c80aa8540"
    uuid_b = "a2b3c4d5-6e7f-4081-9a0b-1c2d3e4f5061"
    texto = (
        TimbradoExportPacV40()
        .exportar(_datos_completos(folios_fiscales_relacionados=(uuid_a, uuid_b)))
        .decode("cp1252")
    )
    assert f"04               {uuid_a}" in texto
    assert f"04               {uuid_b}" in texto


# ── Lo que NO se puede llenar todavía ─────────────────────────────────────────
def test_reporta_los_campos_fiscales_que_faltan(datos: DatosTimbrado) -> None:
    faltantes = TimbradoExportPacV40().campos_faltantes(datos)
    assert "Detalle.ClaveProdServ" in faltantes
    assert "AGREGADOS.UsoCFDI" in faltantes
    assert "ExReceptor.RegimenFiscal" in faltantes
    # Los domicilios SÍ están (en texto libre), así que no se reportan.
    assert not [f for f in faltantes if "domicilio" in f]


def test_sin_faltantes_cuando_estan_todos() -> None:
    completos = _datos_completos()
    assert TimbradoExportPacV40().campos_faltantes(completos) == []
    texto = TimbradoExportPacV40().exportar(completos).decode("cp1252")
    assert "Regimen            601" in texto  # AGREGADOS: columna 19
    assert "UsoCFDI            G03" in texto
    assert TimbradoExportPacV40().nombre_archivo(completos) == "FACTURA_33_D_A-1041.txt"


def test_reporta_los_domicilios_cuando_faltan(datos: DatosTimbrado) -> None:
    sin_domicilios = _datos_completos(emisor_direccion=None, receptor_direccion=None)
    faltantes = TimbradoExportPacV40().campos_faltantes(sin_domicilios)
    assert any("domicilio del emisor" in f for f in faltantes)
    assert any("domicilio del receptor" in f for f in faltantes)


# ── Domicilio estructurado (ADR-059) ──────────────────────────────────────────
_DOMICILIO = DomicilioFiscal(
    calle="Av. Constituyentes",
    numero_exterior="1154",
    numero_interior="3",
    colonia="Lomas Altas",
    localidad="Ciudad de México",
    referencia="Entre Reforma y Palmas",
    municipio="Miguel Hidalgo",
    estado="Ciudad de México",
    pais="MEX",
    codigo_postal="11950",
)


def test_domicilio_estructurado_llena_los_campos_desglosados() -> None:
    """Con `emisor_domicilio`/`receptor_domicilio` (ADR-059), el layout deja de recibir
    todo apachurrado en `Referencia` y llena Calle/Colonia/Municipio/… de verdad."""
    datos = _datos_completos(emisor_domicilio=_DOMICILIO, receptor_domicilio=_DOMICILIO)
    texto = TimbradoExportPacV40().exportar(datos).decode("cp1252")
    assert "Calle            Av. Constituyentes" in texto
    assert "NroExterior      1154" in texto
    assert "Colonia          Lomas Altas" in texto
    assert "Municipio        Miguel Hidalgo" in texto
    assert "CodigoPostal     11950" in texto
    # `campos_faltantes()` ya no reporta ninguno de los dos domicilios.
    assert not [f for f in TimbradoExportPacV40().campos_faltantes(datos) if "domicilio" in f]


def test_domicilio_estructurado_incompleto_sin_legacy_sigue_faltante() -> None:
    """Si al domicilio desglosado le falta uno de los 5 campos mínimos (aquí `estado`) y
    NO hay texto libre de respaldo, se sigue reportando como faltante."""
    incompleto = DomicilioFiscal(
        calle="Av. Constituyentes", colonia="Lomas Altas", municipio="Miguel Hidalgo",
        codigo_postal="11950",
    )
    datos = _datos_completos(
        emisor_domicilio=incompleto, emisor_direccion=None,
        receptor_domicilio=None, receptor_direccion=None,
    )
    faltantes = TimbradoExportPacV40().campos_faltantes(datos)
    assert any("domicilio del emisor" in f for f in faltantes)


def test_domicilio_estructurado_incompleto_cae_al_texto_legacy() -> None:
    """Sin los 5 campos mínimos, pero CON texto libre de respaldo, no se reporta faltante
    — y el layout usa el texto libre en `Referencia` (mismo apaño de siempre)."""
    incompleto = DomicilioFiscal(calle="Av. Constituyentes")  # le faltan 4 de los 5
    datos = _datos_completos(
        emisor_domicilio=incompleto, emisor_direccion="AV. CONSTITUYENTES 1154, CDMX",
    )
    assert not [
        f for f in TimbradoExportPacV40().campos_faltantes(datos) if "domicilio del emisor" in f
    ]
    texto = TimbradoExportPacV40().exportar(datos).decode("cp1252")
    assert "Referencia       AV. CONSTITUYENTES 1154, CDMX" in texto


# ── Codificación: el punto abierto del layout ─────────────────────────────────
def test_falla_claro_si_un_caracter_no_cabe_en_la_codificacion(datos: DatosTimbrado) -> None:
    """Mejor fallar que mandar un nombre fiscal mutilado al PAC."""
    with pytest.raises(ErrorCodificacionTimbrado) as exc:
        TimbradoExportPacV40().exportar(_datos_completos(receptor_nombre="CLIENTE 🚀 SA"))
    assert "cp1252" in str(exc.value)


def test_los_acentos_del_espanol_si_caben_en_cp1252() -> None:
    crudo = TimbradoExportPacV40().exportar(
        _datos_completos(receptor_nombre="CAMPAÑA MENCIÓN ÁÉÍÓÚ SA DE CV")
    )
    assert "CAMPAÑA MENCIÓN ÁÉÍÓÚ SA DE CV" in crudo.decode("cp1252")
