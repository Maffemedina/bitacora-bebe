"""Curva de crecimiento como imagen PNG (lógica pura, sin red ni DB).

Usa matplotlib con backend 'Agg' (sin pantalla) → seguro en servidor y en tests.
Recibe objetos con atributos: fecha, peso_kg, talla_cm, perimetro_cm.
"""

import io
from typing import Sequence

import matplotlib

matplotlib.use("Agg")  # sin display; DEBE ir antes de importar pyplot

import matplotlib.pyplot as plt  # noqa: E402

_METRICAS = (
    ("Peso (kg)", "peso_kg", "tab:blue"),
    ("Talla (cm)", "talla_cm", "tab:green"),
    ("Perímetro cefálico (cm)", "perimetro_cm", "tab:orange"),
)


def generar_curva_crecimiento(nombre: str, controles: Sequence) -> bytes:
    """Devuelve un PNG (bytes) con la evolución de peso/talla/perímetro cefálico."""
    presentes = [
        m for m in _METRICAS if any(getattr(c, m[1]) is not None for c in controles)
    ]
    filas = len(presentes) or 1
    fig, axes = plt.subplots(filas, 1, figsize=(7, 2.4 * filas), squeeze=False)
    fig.suptitle(f"Crecimiento de {nombre}", fontweight="bold")

    for ax, (titulo, attr, color) in zip(axes[:, 0], presentes):
        puntos = sorted(
            (c.fecha, getattr(c, attr))
            for c in controles
            if getattr(c, attr) is not None
        )
        ax.plot([p[0] for p in puntos], [p[1] for p in puntos], marker="o", color=color)
        ax.set_ylabel(titulo)
        ax.grid(True, alpha=0.3)

    if not presentes:
        axes[0, 0].text(0.5, 0.5, "Sin datos aún", ha="center", va="center")
        axes[0, 0].axis("off")

    fig.autofmt_xdate()
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    plt.close(fig)
    return buffer.getvalue()
