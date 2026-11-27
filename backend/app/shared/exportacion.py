"""Exportación de reportes a Excel/CSV (transversal — ADR-025, F4-01).

Único punto que arma los bytes de `.xlsx`/`.csv` para cualquier vista exportable del
sistema. Los routers pasan las filas YA calculadas (sin lógica de negocio aquí) y
reciben bytes listos para responder con el `media_type` correcto.

Neutralización de CSV/formula-injection (ADR-025): un texto que empiece con `=`, `+`,
`-`, `@`, tab o retorno de carro puede ser interpretado por Excel/Sheets como fórmula,
o usarse para manipular la celda destino al pegar/importar. El mecanismo de defensa
difiere por formato:
- `.csv`: se antepone un apóstrofe — es el truco estándar para forzar texto al abrir
  el archivo en Excel/Sheets.
- `.xlsx`: el apóstrofe NO hace falta (ni se ve bien): openpyxl permite fijar el tipo
  de celda explícitamente a texto (`data_type = "s"`), que basta para que Excel nunca
  la evalúe como fórmula.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

_CARACTERES_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def neutralizar_formula(valor: str) -> str:
    """Antepone un apóstrofe si el texto empieza con un caracter peligroso."""
    if valor and valor[0] in _CARACTERES_PELIGROSOS:
        return "'" + valor
    return valor


def _es_numerico(valor: Any) -> bool:
    return isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool)


def construir_xlsx(hojas: dict[str, tuple[Sequence[str], Sequence[Sequence[Any]]]]) -> bytes:
    """Arma un `.xlsx` con una hoja por entrada de `hojas` (nombre -> (encabezados, filas)).

    Celdas numéricas (`Decimal`/`int`/`float`) se escriben como número real con 2
    decimales — nunca como texto. Celdas de texto peligrosas se fuerzan a tipo string
    explícito (sin modificar su contenido visible).
    """
    wb = Workbook()
    primera = True
    for nombre_hoja, (encabezados, filas) in hojas.items():
        ws = wb.active if primera else wb.create_sheet()
        primera = False
        ws.title = nombre_hoja[:31]  # límite de Excel para el nombre de hoja

        for col, encabezado in enumerate(encabezados, start=1):
            celda = ws.cell(row=1, column=col, value=encabezado)
            celda.font = Font(bold=True)

        for fila_idx, fila in enumerate(filas, start=2):
            for col_idx, valor in enumerate(fila, start=1):
                celda = ws.cell(row=fila_idx, column=col_idx)
                if _es_numerico(valor):
                    celda.value = float(valor)
                    celda.number_format = "#,##0.00"
                elif isinstance(valor, (date, datetime)):
                    celda.value = valor
                elif valor is None:
                    celda.value = ""
                else:
                    texto = str(valor)
                    celda.value = texto
                    if texto and texto[0] in _CARACTERES_PELIGROSOS:
                        celda.data_type = "s"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def construir_csv(encabezados: Sequence[str], filas: Sequence[Sequence[Any]]) -> bytes:
    """Arma un `.csv` (BOM utf-8-sig, para que Excel abra acentos correctamente)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(encabezados)
    for fila in filas:
        fila_neutralizada = []
        for valor in fila:
            if _es_numerico(valor):
                fila_neutralizada.append(f"{float(valor):.2f}")
            elif valor is None:
                fila_neutralizada.append("")
            else:
                fila_neutralizada.append(neutralizar_formula(str(valor)))
        writer.writerow(fila_neutralizada)
    return buffer.getvalue().encode("utf-8-sig")
