"""Tests de lógica pura de fechas/edad (app/utils.py). Sin red, sin DB."""

from datetime import date

from app.utils import edad_texto, hoy


def test_edad_en_meses():
    assert edad_texto(date(2024, 1, 1), date(2024, 4, 1)) == "3 meses"


def test_edad_un_mes_es_singular():
    assert edad_texto(date(2024, 1, 1), date(2024, 2, 1)) == "1 mes"


def test_edad_ajusta_por_dia_del_mes():
    # Aún no cumple el mes (día de ref < día de nacimiento)
    assert edad_texto(date(2024, 1, 15), date(2024, 2, 10)) == "0 meses"


def test_edad_exacta_dos_anios():
    assert edad_texto(date(2022, 1, 1), date(2024, 1, 1)) == "2 años"


def test_edad_anios_y_meses():
    assert edad_texto(date(2022, 1, 1), date(2024, 3, 1)) == "2 años y 2 meses"


def test_edad_nunca_negativa():
    # Fecha de nacimiento futura → no rompe, devuelve 0 meses
    assert edad_texto(date(2030, 1, 1), date(2024, 1, 1)) == "0 meses"


def test_hoy_devuelve_un_date():
    assert isinstance(hoy(), date)
