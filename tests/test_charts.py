"""Tests de la curva de crecimiento (lógica pura, sin red)."""

from datetime import date
from types import SimpleNamespace

from app.charts import generar_curva_crecimiento

PNG_MAGIC = b"\x89PNG"


def _c(fecha, peso, talla, pc):
    return SimpleNamespace(fecha=fecha, peso_kg=peso, talla_cm=talla, perimetro_cm=pc)


def test_curva_devuelve_png_valido():
    controles = [_c(date(2026, 1, 3), 7.5, 68, 43), _c(date(2026, 2, 3), 8.2, 70, 44)]
    png = generar_curva_crecimiento("Luna", controles)
    assert isinstance(png, (bytes, bytearray))
    assert bytes(png[:4]) == PNG_MAGIC
    assert len(png) > 100  # no es una imagen vacía


def test_curva_con_un_solo_control():
    png = generar_curva_crecimiento("Luna", [_c(date(2026, 1, 3), 7.5, 68, 43)])
    assert bytes(png[:4]) == PNG_MAGIC


def test_curva_tolera_campos_vacios():
    # Solo peso; talla y perímetro en None → no debe romper.
    controles = [_c(date(2026, 1, 3), 7.5, None, None), _c(date(2026, 2, 3), 8.0, None, None)]
    png = generar_curva_crecimiento("Luna", controles)
    assert bytes(png[:4]) == PNG_MAGIC
