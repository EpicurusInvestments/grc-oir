"""Pruebas de `app/shared/exportacion.py` — neutralización CSV/formula-injection
(ADR-025) y builders de `.xlsx`/`.csv`, usados por F4 y cualquier exportación futura.
"""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import load_workbook

from app.shared.exportacion import construir_csv, construir_xlsx, neutralizar_formula


def test_neutralizar_formula_antepone_apostrofe_a_caracteres_peligrosos() -> None:
    for peligroso in ("=SUMA(A1:A9)", "+1+1", "-cmd", "@SUM(1,2)", "\tmaligno", "\rmaligno"):
        assert neutralizar_formula(peligroso).startswith("'")
    assert neutralizar_formula("texto normal") == "texto normal"
    assert neutralizar_formula("") == ""


def test_construir_csv_neutraliza_y_formatea_numeros() -> None:
    contenido = construir_csv(
        ["Renglón", "Monto"], [["=HACK()", Decimal("1234.5")], ["Normal", None]]
    )
    texto = contenido.decode("utf-8-sig")
    assert "'=HACK()" in texto
    assert "1234.50" in texto
    assert "Normal" in texto


def test_construir_xlsx_celdas_numericas_son_numero_real_no_texto() -> None:
    contenido = construir_xlsx(
        {"Hoja": (["Renglón", "Monto"], [["=HACK()", Decimal("1234.56")], ["Normal", 0]])}
    )
    wb = load_workbook(io.BytesIO(contenido))
    ws = wb.active
    assert ws["A1"].value == "Renglón"
    celda_peligrosa = ws["A2"]
    assert celda_peligrosa.value == "=HACK()"  # el valor NO se altera visualmente...
    assert celda_peligrosa.data_type == "s"  # ...pero se fuerza tipo texto explícito
    celda_monto = ws["B2"]
    assert celda_monto.value == 1234.56
    assert isinstance(celda_monto.value, float)  # número real, nunca string
