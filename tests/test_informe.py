"""Informe PDF para el pediatra (lógica pura, sin red)."""

from datetime import date, datetime
from types import SimpleNamespace as NS

from app.informe import _limpio, generar_informe_pdf

HOY = date(2026, 11, 9)
LUNA = NS(name="Luna 🌙", birthdate=date(2025, 12, 1))


def _control(f, p, t, pc):
    return NS(fecha=f, peso_kg=p, talla_cm=t, perimetro_cm=pc)


def test_pdf_completo():
    pdf = generar_informe_pdf(
        LUNA,
        "11 meses",
        [_control(date(2026, 8, 1), 7.9, 68, 43), _control(date(2026, 11, 1), 8.6, 72, None)],
        [NS(created_at=datetime(2026, 11, 1), content="Vitamina D 400 UI diarias 💊")],
        [
            NS(happened_on=date(2026, 10, 20), description="Dijo «papá» 🥹"),
            NS(happened_on=date(2025, 12, 1), description="Nació"),  # fuera de los 4 meses
        ],
        [NS(scheduled_at=datetime(2026, 11, 27, 15, 0), title="Vacunas", location="Clínica")],
        HOY,
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 10_000  # incluye la curva


def test_pdf_sin_datos_no_falla():
    bebe = NS(name="Mateo", birthdate=None)
    assert generar_informe_pdf(bebe, None, [], [], [], [], HOY).startswith(b"%PDF")


def test_quita_emojis_pero_no_tildes():
    assert _limpio("Dijo «papá» 🥹 ñ") == "Dijo «papá»  ñ"
