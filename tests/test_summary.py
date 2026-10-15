"""Tests del resumen semanal (lógica pura y determinista, sin Gemini/red)."""

from datetime import date, datetime
from types import SimpleNamespace

from app.summary import componer_resumen_semanal, rango_semana

HOY = date(2026, 9, 24)


def _hito(d, desc):
    return SimpleNamespace(happened_on=d, description=desc)


def _ctrl(d, peso, talla, pc):
    return SimpleNamespace(fecha=d, peso_kg=peso, talla_cm=talla, perimetro_cm=pc)


def _cita(dt, titulo, lugar=None):
    return SimpleNamespace(scheduled_at=dt, title=titulo, location=lugar)


def test_rango_semana_son_los_ultimos_7_dias():
    assert rango_semana(HOY) == (date(2026, 9, 18), date(2026, 9, 24))


def test_resumen_completo():
    hitos = [
        _hito(date(2026, 9, 21), "Dio sus primeros pasos"),
        _hito(date(2026, 9, 23), "Probó aguacate"),
    ]
    ctrls = [_ctrl(date(2026, 9, 22), 8.2, 70, 44)]
    citas = [_cita(datetime(2026, 9, 27, 15, 0), "Pediatra")]
    txt = componer_resumen_semanal("Luna", hitos, ctrls, citas, HOY)
    assert "La semana de Luna" in txt
    assert "Del 18 al 24 de septiembre" in txt
    assert "21/09 — Dio sus primeros pasos" in txt
    assert "22/09 — 8.2 kg · 70 cm · PC 44 cm" in txt
    assert "27/09 15:00 — Pediatra" in txt
    assert "💛" in txt


def test_resumen_sin_hitos_omite_la_seccion():
    ctrls = [_ctrl(date(2026, 9, 22), 8.2, 70, 44)]
    txt = componer_resumen_semanal("Luna", [], ctrls, [], HOY)
    assert "Momentos para recordar" not in txt
    assert "Último control" in txt


def test_resumen_sin_citas_omite_la_seccion():
    hitos = [_hito(date(2026, 9, 21), "Gateó")]
    txt = componer_resumen_semanal("Luna", hitos, [], [], HOY)
    assert "Próximo" not in txt
    assert "Momentos para recordar" in txt


def test_resumen_sin_actividad_es_amable():
    txt = componer_resumen_semanal("Luna", [], [], [], HOY)
    assert "Momentos para recordar" not in txt
    assert "Último control" not in txt
    assert "Cuéntame" in txt or "no registramos" in txt


def test_resumen_respeta_el_nombre_multi_hijo():
    hitos = [_hito(date(2026, 9, 20), "Entró al colegio")]
    txt = componer_resumen_semanal("Sara", hitos, [], [], HOY)
    assert "La semana de Sara" in txt
    assert "20/09 — Entró al colegio" in txt


def test_hito_fuera_de_la_ventana_no_aparece():
    hitos = [_hito(date(2026, 9, 10), "Algo viejo")]
    txt = componer_resumen_semanal("Luna", hitos, [], [], HOY)
    assert "Algo viejo" not in txt


def test_cita_lejana_no_aparece():
    citas = [_cita(datetime(2026, 10, 20, 9, 0), "Vacuna")]
    txt = componer_resumen_semanal("Luna", [], [], citas, HOY)
    assert "Vacuna" not in txt


def test_control_con_medidas_faltantes_no_rompe():
    ctrls = [_ctrl(date(2026, 9, 22), 8.2, None, None)]
    txt = componer_resumen_semanal("Luna", [], ctrls, [], HOY)
    assert "22/09 — 8.2 kg" in txt
    assert "cm ·" not in txt  # no deja separadores colgando
