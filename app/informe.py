"""Informe PDF para llevar a la consulta con el pediatra (lógica pura, sin IA ni red).

Junta lo que la familia registró: datos del bebé, controles de crecimiento (tabla y
curva), indicaciones del pediatra, hitos recientes y próximas citas, más un espacio
para anotar preguntas. Es determinista: nunca resume ni interpreta con IA, porque
es un documento que va a leer un médico.
"""

import io
import os
import re
from datetime import date, timedelta
from typing import Optional, Sequence

import matplotlib
from fpdf import FPDF
from fpdf.fonts import FontFace

from app.charts import generar_curva_crecimiento

# DejaVu viene con matplotlib (ya es dependencia): tildes, ñ y símbolos sin
# instalar fuentes extra.
_FUENTES = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")

# Colores (RGB)
_TINTA = (27, 20, 32)
_SUAVE = (92, 74, 88)
_ACENTO = (142, 27, 122)
_FONDO = (241, 228, 239)
_LINEA = (231, 211, 222)

# Los emojis no existen en la fuente del PDF: se quitan para no imprimir cuadritos.
_FUERA_DE_FUENTE = re.compile(r"[\U00010000-\U0010FFFF☀-➿️‍]")

HITOS_DIAS = 120  # hitos de los últimos ~4 meses


def _limpio(texto: Optional[str]) -> str:
    return _FUERA_DE_FUENTE.sub("", texto or "").strip()


def _medida(v, unidad: str) -> str:
    return f"{v:g} {unidad}" if v is not None else "-"


class _PDF(FPDF):
    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*_SUAVE)
        self.cell(
            0, 5,
            "Información registrada por la familia en Bitácora Bebé. "
            "No reemplaza la valoración del profesional de salud.",
            align="C",
        )
        self.ln(4)
        self.cell(0, 5, f"Página {self.page_no()}", align="C")


def _titulo_seccion(pdf: FPDF, texto: str) -> None:
    pdf.ln(4)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*_ACENTO)
    pdf.cell(0, 8, texto, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_LINEA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*_TINTA)


def _vacio(pdf: FPDF, texto: str) -> None:
    pdf.set_text_color(*_SUAVE)
    pdf.multi_cell(0, 6, texto, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_TINTA)


def _vineta(pdf: FPDF, texto: str) -> None:
    pdf.multi_cell(0, 6, f"•  {texto}", new_x="LMARGIN", new_y="NEXT")


def generar_informe_pdf(
    child,
    edad: Optional[str],
    controles: Sequence,
    consejos: Sequence,
    hitos: Sequence,
    citas: Sequence,
    hoy_: date,
) -> bytes:
    """Devuelve el PDF (bytes). 'citas' deben ser las próximas (ya filtradas)."""
    pdf = _PDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_font("DejaVu", "", os.path.join(_FUENTES, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(_FUENTES, "DejaVuSans-Bold.ttf"))
    pdf.set_title(f"Informe para el pediatra - {_limpio(child.name)}")
    pdf.add_page()

    # Encabezado
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*_TINTA)
    pdf.cell(0, 10, "Informe para el pediatra", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*_SUAVE)
    pdf.cell(0, 6, f"Generado el {hoy_:%d/%m/%Y}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Ficha del bebé
    pdf.set_fill_color(*_FONDO)
    pdf.set_text_color(*_TINTA)
    nacimiento = f"{child.birthdate:%d/%m/%Y}" if child.birthdate else "sin registrar"
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 9, f"  {_limpio(child.name)}", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(
        0, 7, f"  Nacimiento: {nacimiento}     Edad: {edad or 'sin registrar'}",
        fill=True, new_x="LMARGIN", new_y="NEXT",
    )

    # Crecimiento
    _titulo_seccion(pdf, "Controles de crecimiento")
    if not controles:
        _vacio(pdf, "Aún no hay controles registrados.")
    else:
        with pdf.table(
            col_widths=(30, 30, 30, 40),
            headings_style=FontFace(emphasis="BOLD", color=_ACENTO, fill_color=_FONDO),
            line_height=7,
            text_align="CENTER",
            borders_layout="HORIZONTAL_LINES",
        ) as tabla:
            enc = tabla.row()
            for t in ("Fecha", "Peso", "Talla", "Perímetro cefálico"):
                enc.cell(t)
            for c in sorted(controles, key=lambda c: c.fecha):
                fila = tabla.row()
                fila.cell(f"{c.fecha:%d/%m/%Y}")
                fila.cell(_medida(c.peso_kg, "kg"))
                fila.cell(_medida(c.talla_cm, "cm"))
                fila.cell(_medida(c.perimetro_cm, "cm"))
        if len(controles) >= 2:
            png = generar_curva_crecimiento(_limpio(child.name), controles)
            pdf.ln(3)
            pdf.image(io.BytesIO(png), x="C", w=150)

    # Indicaciones del pediatra
    _titulo_seccion(pdf, "Indicaciones registradas del pediatra")
    if not consejos:
        _vacio(pdf, "No hay indicaciones registradas.")
    for a in sorted(consejos, key=lambda a: a.created_at):
        _vineta(pdf, f"{a.created_at:%d/%m/%Y}: {_limpio(a.content)}")

    # Hitos recientes
    desde = hoy_ - timedelta(days=HITOS_DIAS)
    recientes = sorted(
        (h for h in hitos if h.happened_on >= desde), key=lambda h: h.happened_on
    )
    _titulo_seccion(pdf, "Hitos de los últimos 4 meses")
    if not recientes:
        _vacio(pdf, "No hay hitos registrados en este periodo.")
    for h in recientes:
        _vineta(pdf, f"{h.happened_on:%d/%m/%Y}: {_limpio(h.description)}")

    # Próximas citas
    _titulo_seccion(pdf, "Próximas citas")
    if not citas:
        _vacio(pdf, "No hay citas próximas.")
    for c in citas:
        lugar = f" ({_limpio(c.location)})" if c.location else ""
        _vineta(pdf, f"{c.scheduled_at:%d/%m/%Y %H:%M}: {_limpio(c.title)}{lugar}")

    # Espacio para la consulta
    _titulo_seccion(pdf, "Preguntas para la consulta")
    pdf.set_draw_color(*_LINEA)
    for _ in range(5):
        pdf.ln(8)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())

    return bytes(pdf.output())
