"""Resumen semanal de un bebé — lógica pura, determinista, SIN Gemini ni red.

Recibe los datos crudos del hijo y arma un texto cálido y factual:
  - hitos de los últimos 7 días,
  - el control de crecimiento más reciente de esa semana (si hay),
  - las citas de los próximos 7 días (si hay).
Omite las secciones vacías y nunca inventa datos.
"""

from datetime import date, timedelta
from typing import Optional, Sequence

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def rango_semana(hoy_: date) -> tuple:
    """Ventana de los últimos 7 días (inclusive): (hoy-6, hoy)."""
    return (hoy_ - timedelta(days=6), hoy_)


def _num(v: float) -> str:
    return f"{v:g}"


def _rango_texto(desde: date, hasta: date) -> str:
    if desde.month == hasta.month:
        return f"Del {desde.day} al {hasta.day} de {_MESES[hasta.month - 1]}"
    return (
        f"Del {desde.day} de {_MESES[desde.month - 1]} "
        f"al {hasta.day} de {_MESES[hasta.month - 1]}"
    )


def _control_texto(c) -> str:
    partes = []
    if c.peso_kg is not None:
        partes.append(f"{_num(c.peso_kg)} kg")
    if c.talla_cm is not None:
        partes.append(f"{_num(c.talla_cm)} cm")
    if c.perimetro_cm is not None:
        partes.append(f"PC {_num(c.perimetro_cm)} cm")
    return " · ".join(partes)


def componer_resumen_semanal(
    nombre: str,
    hitos: Sequence,
    controles: Sequence,
    citas: Sequence,
    hoy_: date,
) -> str:
    desde, hasta = rango_semana(hoy_)
    fin_proximo = hoy_ + timedelta(days=7)

    hitos_semana = sorted(
        (h for h in hitos if desde <= h.happened_on <= hasta),
        key=lambda h: h.happened_on,
    )
    controles_semana = [c for c in controles if desde <= c.fecha <= hasta]
    control: Optional[object] = (
        max(controles_semana, key=lambda c: c.fecha) if controles_semana else None
    )
    citas_prox = sorted(
        (c for c in citas if hoy_ <= c.scheduled_at.date() <= fin_proximo),
        key=lambda c: c.scheduled_at,
    )

    control_txt = _control_texto(control) if control is not None else ""

    # Sin ninguna actividad → mensaje amable que invita a registrar
    if not hitos_semana and not control_txt and not citas_prox:
        return (
            f"✨ <b>La semana de {nombre}</b>\n\n"
            "Esta semana aún no hay nada registrado 🙂\n"
            f"Cuéntame un momento (ej. «{nombre} sonrió hoy») y lo guardo con cariño. 💛"
        )

    lineas = [f"✨ <b>La semana de {nombre}</b>", f"📅 {_rango_texto(desde, hasta)}"]

    if hitos_semana:
        lineas += ["", "🍼 <b>Momentos para recordar</b>"]
        lineas += [f"• {h.happened_on:%d/%m} — {h.description}" for h in hitos_semana]

    if control_txt:
        lineas += ["", "📏 <b>Último control</b>", f"• {control.fecha:%d/%m} — {control_txt}"]

    if citas_prox:
        lineas += ["", "🗓️ <b>Próximo</b>"]
        for c in citas_prox:
            lugar = f" — {c.location}" if c.location else ""
            lineas.append(f"• {c.scheduled_at:%d/%m %H:%M} — {c.title}{lugar}")

    lineas.append("")
    if hitos_semana:
        lineas.append("💛 Una semana llena de pequeños grandes momentos.")
    else:
        lineas.append(f"💛 Aquí estoy para guardar cada recuerdo de {nombre}.")
    return "\n".join(lineas)
