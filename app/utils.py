"""Utilidades de fecha/edad, en la zona horaria configurada (TIMEZONE)."""

from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings

ZONA = ZoneInfo(settings.timezone)


def hoy() -> date:
    """La fecha de HOY en la zona de la familia (no la del servidor, que va en UTC)."""
    return datetime.now(ZONA).date()


def edad_texto(nacimiento: date, ref: Optional[date] = None) -> str:
    """Edad legible: '3 meses', '14 meses', '2 años y 1 mes'."""
    ref = ref or hoy()
    meses = (ref.year - nacimiento.year) * 12 + (ref.month - nacimiento.month)
    if ref.day < nacimiento.day:
        meses -= 1
    meses = max(meses, 0)
    if meses < 24:
        return f"{meses} mes" + ("es" if meses != 1 else "")
    años = meses // 12
    resto = meses % 12
    txt = f"{años} año" + ("s" if años != 1 else "")
    if resto:
        txt += f" y {resto} mes" + ("es" if resto != 1 else "")
    return txt
