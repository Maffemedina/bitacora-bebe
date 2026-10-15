"""Tests de helpers puros de app/handlers.py (sin aiogram real, sin red).

Importar app.handlers NO construye el bot ni inicia polling; solo registra el
router en memoria. Las variables de entorno fake ya están cargadas por conftest.
"""

from datetime import date, datetime
from types import SimpleNamespace

from app.handlers import (
    _elegir_registro,
    _fmt_control_linea,
    _fmt_medida,
    _parse_date,
    _parse_dt,
    _sin_acentos,
)


def _reg(desc: str, created: datetime):
    return SimpleNamespace(description=desc, created_at=created)


# ---------- _sin_acentos ----------

def test_sin_acentos_quita_tildes():
    assert _sin_acentos("último") == "ultimo"
    assert _sin_acentos("PAPÁ") == "PAPA"  # respeta mayúsculas, solo quita tilde
    assert _sin_acentos("gateó") == "gateo"


# ---------- _elegir_registro ----------

def test_elegir_el_ultimo_por_created_at():
    regs = [_reg("gateó", datetime(2024, 1, 1)), _reg("sonrió", datetime(2024, 2, 1))]
    r = _elegir_registro(regs, "el último", lambda x: x.description)
    assert r.description == "sonrió"


def test_elegir_por_descripcion():
    regs = [_reg("gateó", datetime(2024, 1, 1)), _reg("sonrió", datetime(2024, 2, 1))]
    r = _elegir_registro(regs, "el de que gateó", lambda x: x.description)
    assert r.description == "gateó"


def test_elegir_por_descripcion_ignora_acentos():
    regs = [_reg("comió papilla", datetime(2024, 1, 1))]
    r = _elegir_registro(regs, "lo de que comio", lambda x: x.description)
    assert r is not None and r.description == "comió papilla"


def test_elegir_sin_registros_devuelve_none():
    assert _elegir_registro([], "el último", lambda x: x.description) is None


def test_elegir_sin_coincidencia_devuelve_none():
    regs = [_reg("gateó", datetime(2024, 1, 1))]
    assert _elegir_registro(regs, "primer diente", lambda x: x.description) is None


# ---------- _parse_date / _parse_dt ----------

def test_parse_date_iso():
    assert _parse_date("2024-12-25") == date(2024, 12, 25)


def test_parse_date_recorta_datetime():
    assert _parse_date("2024-12-25T10:00") == date(2024, 12, 25)


def test_parse_date_invalida_o_none():
    assert _parse_date(None) is None
    assert _parse_date("no-es-fecha") is None


def test_parse_dt_iso():
    assert _parse_dt("2024-12-25T15:30") == datetime(2024, 12, 25, 15, 30)


def test_parse_dt_tolera_z():
    assert _parse_dt("2024-12-25T15:30Z") == datetime(2024, 12, 25, 15, 30)


def test_parse_dt_invalida_o_none():
    assert _parse_dt(None) is None
    assert _parse_dt("mañana") is None


# ---------- formato de medidas ----------

def test_fmt_medida_con_valor():
    assert _fmt_medida(8.2, "kg") == "8.2 kg"


def test_fmt_medida_sin_valor():
    assert _fmt_medida(None, "kg") == "—"


def test_fmt_control_linea():
    c = SimpleNamespace(fecha=date(2026, 1, 3), peso_kg=7.5, talla_cm=68, perimetro_cm=43)
    linea = _fmt_control_linea(c)
    assert "03/01/2026" in linea
    assert "peso 7.5 kg" in linea
    assert "PC 43 cm" in linea
