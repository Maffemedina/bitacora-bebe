"""«¿Cuándo caminó?» con edad y medidas, y lectura de la cartilla de crecimiento.

Sin red: Telegram y Gemini se reemplazan por dobles.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import agent, crud, handlers
from app.agent import Extraccion, FotoAnalisis, MedidaCartilla
from app.handlers import _control_mas_cercano, _fmt_detalle_hito, _validar_cartilla

A, B = 100, 200
HOY = date(2026, 11, 3)
NACIO = date(2025, 6, 25)


class FakeMessage:
    def __init__(self, user_id=A, text=None, caption=None):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.caption = caption
        self.photo = [SimpleNamespace(file_id="foto")]
        self.respuestas = []
        self.teclados = []
        self.videos = []

    async def answer(self, texto, reply_markup=None):
        self.respuestas.append(texto)
        self.teclados.append(reply_markup)

    async def answer_video(self, video, caption=None):
        self.videos.append(video)
        self.respuestas.append(caption)


def _cb(data, message, user_id=A):
    async def answer():
        return None

    return SimpleNamespace(
        data=data, message=message, from_user=SimpleNamespace(id=user_id), answer=answer
    )


def _control(fecha, peso=None, talla=None, perimetro=None):
    return SimpleNamespace(fecha=fecha, peso_kg=peso, talla_cm=talla, perimetro_cm=perimetro)


def _fila(fecha, peso=None, talla=None, perimetro=None):
    return MedidaCartilla(fecha=fecha, peso=peso, talla=talla, perimetro=perimetro)


@pytest.fixture
def state():
    key = StorageKey(bot_id=1, chat_id=A, user_id=A)
    return FSMContext(storage=MemoryStorage(), key=key)


@pytest.fixture
async def joshua():
    child = await crud.add_child(A, "Joshua", NACIO)
    await crud.set_active_child(A, child.id)
    return child


def _planea(monkeypatch, *acciones):
    async def planear(mensaje, hoy_iso, baby_name, contexto=""):
        return list(acciones)

    monkeypatch.setattr(agent, "planear", planear)


def _elige(monkeypatch, id_):
    async def elegir_hito(pregunta, hitos):
        return id_

    monkeypatch.setattr(agent, "elegir_hito", elegir_hito)


def _lee_cartilla(monkeypatch, *filas):
    async def guardar(message):
        return "tg:foto"

    async def bajar(message):
        return b"bytes"

    async def analizar(imagen, mime, hoy_iso, nombre):
        return FotoAnalisis(tipo="cartilla", controles=list(filas))

    monkeypatch.setattr(handlers, "_save_photo_ref", guardar)
    monkeypatch.setattr(handlers, "_download_photo_bytes", bajar)
    monkeypatch.setattr(agent, "analizar_foto", analizar)


# ---------- Control más cercano y detalle ----------

def test_control_mas_cercano_ignora_los_vacios():
    vacio = _control(date(2026, 7, 5))
    lejos = _control(date(2026, 1, 1), peso=7)
    cerca = _control(date(2026, 8, 1), peso=9)
    assert _control_mas_cercano([vacio, lejos, cerca], date(2026, 7, 5)) is cerca
    assert _control_mas_cercano([vacio], date(2026, 7, 5)) is None


def test_control_empatado_prefiere_el_anterior():
    antes = _control(date(2026, 7, 1), peso=8)
    despues = _control(date(2026, 7, 9), peso=9)
    assert _control_mas_cercano([despues, antes], date(2026, 7, 5)) is antes


def _hito(fecha=date(2026, 7, 5)):
    return SimpleNamespace(description="gateó", happened_on=fecha)


def test_detalle_con_control_del_mismo_dia():
    texto = _fmt_detalle_hito(_hito(), NACIO, _control(date(2026, 7, 5), peso=9.5, talla=72))
    assert "05/07/2026" in texto and "12 meses" in texto
    assert "Ese día le midieron: peso 9.5 kg, talla 72 cm" in texto


def test_detalle_no_da_por_medido_lo_de_otra_fecha():
    texto = _fmt_detalle_hito(_hito(), NACIO, _control(date(2026, 8, 27), peso=10.1))
    assert "Ese día" not in texto
    assert "27/08/2026 (53 días después)" in texto


def test_detalle_sin_nacimiento_ni_controles():
    texto = _fmt_detalle_hito(_hito(), None, None)
    assert "No tengo su fecha de nacimiento" in texto
    assert "No tengo controles" in texto


def test_detalle_sin_edad_si_la_fecha_es_anterior_al_nacimiento():
    assert "Tenía" not in _fmt_detalle_hito(_hito(date(2025, 1, 1)), NACIO, None)


# ---------- ¿Cuándo caminó? ----------

async def test_responde_fecha_edad_y_medidas(state, joshua, monkeypatch):
    m = await crud.add_milestone(A, joshua.id, "dio sus primeros pasos", date(2026, 7, 5))
    await crud.add_control(A, joshua.id, date(2026, 7, 5), 9.5, 72, 46)
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="caminó"))
    _elige(monkeypatch, m.id)
    msg = FakeMessage(text="¿cuándo caminó Joshua?")
    await handlers.on_text(msg, state)

    assert "05/07/2026" in msg.respuestas[-1]
    assert "12 meses" in msg.respuestas[-1]
    assert "peso 9.5 kg" in msg.respuestas[-1]


async def test_envia_el_video_del_hito(state, joshua, monkeypatch):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:abc")
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="gateó"))
    _elige(monkeypatch, m.id)
    msg = FakeMessage(text="¿cuándo gateó?")
    await handlers.on_text(msg, state)

    assert msg.videos == ["abc"]
    assert "12 meses" in msg.respuestas[-1]


async def test_no_confunde_gatear_con_caminar(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="caminó"))
    _elige(monkeypatch, None)
    msg = FakeMessage(text="¿cuándo caminó?")
    await handlers.on_text(msg, state)

    assert "No tengo eso registrado" in msg.respuestas[-1]


async def test_id_inventado_por_la_ia_no_vale(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="caminó"))
    _elige(monkeypatch, 9999)
    msg = FakeMessage(text="¿cuándo caminó?")
    await handlers.on_text(msg, state)

    assert "No tengo eso registrado" in msg.respuestas[-1]


async def test_si_gemini_falla_no_dice_que_no_esta_registrado(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, "dio sus primeros pasos", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="caminó"))

    async def falla(pregunta, hitos):
        raise RuntimeError("429")

    monkeypatch.setattr(agent, "elegir_hito", falla)
    msg = FakeMessage(text="¿cuándo caminó?")
    await handlers.on_text(msg, state)

    assert "No pude revisar" in msg.respuestas[-1]


async def test_si_gemini_falla_usa_la_coincidencia_de_texto(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="consultar_hito", referencia="gateó"))

    async def falla(pregunta, hitos):
        raise RuntimeError("429")

    monkeypatch.setattr(agent, "elegir_hito", falla)
    msg = FakeMessage(text="¿cuándo gateó?")
    await handlers.on_text(msg, state)

    assert "12 meses" in msg.respuestas[-1]


# ---------- Validación de la cartilla ----------

def test_valida_fechas_y_medidas():
    filas = [
        _fila("2026-03-01", peso=8.2),
        _fila(None, peso=8),                 # sin fecha
        _fila("2027-01-01", peso=8),         # futura
        _fila("2024-01-01", peso=8),         # antes de nacer
        _fila("2026-04-01"),                 # sin medidas
        _fila("2026-05-01", peso=820),       # gramos mal leídos
        _fila("2026-02-01", talla=60, perimetro=40),
    ]
    nuevas, descartadas, repetidas = _validar_cartilla(filas, NACIO, HOY, [])
    assert [f["fecha"] for f in nuevas] == ["2026-02-01", "2026-03-01"]  # en orden
    assert (descartadas, repetidas) == (5, 0)


def test_no_repite_fechas_ya_registradas_ni_dentro_de_la_foto():
    filas = [_fila("2026-08-27", peso=11), _fila("2026-09-01", peso=10), _fila("2026-09-01", peso=10)]
    nuevas, descartadas, repetidas = _validar_cartilla(
        filas, NACIO, HOY, [_control(date(2026, 8, 27), peso=10.1)]
    )
    assert [f["fecha"] for f in nuevas] == ["2026-09-01"]
    assert (descartadas, repetidas) == (0, 2)


# ---------- Foto de la cartilla ----------

async def test_cartilla_no_guarda_sin_confirmar(state, joshua, monkeypatch):
    _lee_cartilla(monkeypatch, _fila("2026-03-01", peso=8.2, talla=68))
    msg = FakeMessage()
    await handlers.on_photo(msg, state)

    assert "01/03/2026: peso 8.2 kg, talla 68 cm" in msg.respuestas[-1]
    assert await crud.list_controls(joshua.id) == []
    assert await crud.list_milestones(joshua.id) == []  # tampoco la vuelve un hito


async def test_confirmar_guarda_una_sola_vez(state, joshua, monkeypatch):
    _lee_cartilla(monkeypatch, _fila("2026-03-01", peso=8.2), _fila("2026-04-01", peso=8.9))
    msg = FakeMessage()
    await handlers.on_photo(msg, state)
    await handlers.cb_cartilla(_cb("cartilla:si", msg), state)
    await handlers.cb_cartilla(_cb("cartilla:si", msg), state)  # doble toque

    controles = await crud.list_controls(joshua.id)
    assert [(c.fecha, c.peso_kg) for c in controles] == [
        (date(2026, 3, 1), 8.2), (date(2026, 4, 1), 8.9)
    ]


async def test_cancelar_no_guarda(state, joshua, monkeypatch):
    _lee_cartilla(monkeypatch, _fila("2026-03-01", peso=8.2))
    msg = FakeMessage()
    await handlers.on_photo(msg, state)
    await handlers.cb_cartilla(_cb("cartilla:no", msg), state)
    await handlers.cb_cartilla(_cb("cartilla:si", msg), state)

    assert await crud.list_controls(joshua.id) == []


async def test_ajeno_no_guarda_la_cartilla(state, joshua, monkeypatch):
    _lee_cartilla(monkeypatch, _fila("2026-03-01", peso=8.2))
    msg = FakeMessage()
    await handlers.on_photo(msg, state)
    await handlers.cb_cartilla(_cb("cartilla:si", msg, user_id=B), state)

    assert await crud.list_controls(joshua.id) == []


async def test_cartilla_ilegible_lo_dice(state, joshua, monkeypatch):
    _lee_cartilla(monkeypatch, _fila(None, peso=8))
    msg = FakeMessage()
    await handlers.on_photo(msg, state)

    assert "no hay medidas nuevas" in msg.respuestas[-1]
    assert msg.teclados[-1] is None


# ---------- ¿Ese hito tiene foto o video? ----------

async def test_ese_hito_usa_el_ultimo_de_la_conversacion(state, joshua, monkeypatch):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    await state.update_data(ultimo_hito=m.id)
    _planea(monkeypatch, Extraccion(intent="consultar_hito"))
    msg = FakeMessage(text="¿ese hito tiene video?")
    await handlers.on_text(msg, state)

    assert "gateó" in msg.respuestas[-1]
    assert "aún no tiene foto ni video" in msg.respuestas[-1]


async def test_ese_hito_sin_contexto_pregunta_cual(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="consultar_hito"))
    msg = FakeMessage(text="¿ese hito tiene video?")
    await handlers.on_text(msg, state)

    assert "De cuál hito" in msg.respuestas[-1]


# ---------- Errores de Gemini ----------

@pytest.mark.parametrize(
    "error, esperado, prohibido",
    [
        ("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier", "cuota gratis de hoy", "un minuto"),
        ("429 RESOURCE_EXHAUSTED per minute", "un minuto", "de hoy"),
        ("503 UNAVAILABLE overloaded", "saturado", "cuota"),
        ("otra cosa", "No pude conectarme", "cuota"),
    ],
)
def test_el_mensaje_depende_del_error_y_lo_registra(error, esperado, prohibido, caplog):
    with caplog.at_level("WARNING", logger="bitacora"):
        texto = agent.fallo("planear", RuntimeError(error))

    assert esperado in texto
    assert prohibido not in texto
    assert "unos segundos" not in texto
    assert error[:20] in caplog.text


async def test_cuota_agotada_se_le_dice_a_la_persona(state, joshua, monkeypatch):
    _planea(monkeypatch, Extraccion(intent="_error", descripcion="⏳ Se acabó la cuota"))
    msg = FakeMessage(text="hola")
    await handlers.on_text(msg, state)

    assert msg.respuestas[-1] == "⏳ Se acabó la cuota"
