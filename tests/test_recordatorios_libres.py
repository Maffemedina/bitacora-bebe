"""«Recuérdame...»: se guarda, avisa a quien lo pidió cuando llega la hora y una sola vez."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import agent, crud, handlers
from app.agent import Extraccion
from app.demo import reiniciar_demo
from app.reminders import enviar_recordatorios_libres

MAMA, PAPA = 5100000001, 5100000002
AHORA = datetime(2026, 11, 20, 10, 0)


class FakeMessage:
    def __init__(self, user_id=MAMA, text="recuérdame algo"):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.respuestas = []

    async def answer(self, texto, reply_markup=None):
        self.respuestas.append(texto)


class BotFalso:
    def __init__(self):
        self.enviados = []

    async def send_message(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


@pytest.fixture
def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=MAMA, user_id=MAMA))


@pytest.fixture
async def bebe(monkeypatch):
    monkeypatch.setattr(handlers, "ahora", lambda: AHORA)
    child = await crud.add_child(MAMA, "Emilia")
    return child


def _planea(monkeypatch, ext):
    vistos = {}

    async def planear(mensaje, hoy_iso, baby_name, contexto=""):
        vistos["hoy"] = hoy_iso
        return [ext]

    monkeypatch.setattr(agent, "planear", planear)
    return vistos


async def _pendientes():
    return await crud.recordatorios_vencidos(AHORA + timedelta(days=365))


async def test_en_minutos(state, bebe, monkeypatch):
    vistos = _planea(monkeypatch, Extraccion(
        intent="crear_recordatorio", recordatorio="darle agua a Emilia", en_minutos=2))
    msg = FakeMessage(text="recuérdame en 2 minutos darle agua a Emilia")
    await handlers.on_text(msg, state)

    assert "son las 10:00" in vistos["hoy"]  # Gemini necesita la hora para «en 2 minutos»
    [r] = await _pendientes()
    assert r.due_at == AHORA + timedelta(minutes=2) and r.owner_id == MAMA
    assert "hoy a las 10:02" in msg.respuestas[-1]


async def test_hora_exacta(state, bebe, monkeypatch):
    _planea(monkeypatch, Extraccion(
        intent="crear_recordatorio", recordatorio="darle la vitamina",
        fecha_hora_recordatorio="2026-11-20T20:00"))
    msg = FakeMessage()
    await handlers.on_text(msg, state)

    [r] = await _pendientes()
    assert r.due_at == datetime(2026, 11, 20, 20, 0)


@pytest.mark.parametrize("ext, esperado", [
    (Extraccion(intent="crear_recordatorio", en_minutos=5), "Qué quieres"),
    (Extraccion(intent="crear_recordatorio", recordatorio="x"), "Para cuándo"),
    (Extraccion(intent="crear_recordatorio", recordatorio="x",
                fecha_hora_recordatorio="2026-11-20T08:00"), "ya pasó"),
])
async def test_si_falta_algo_pregunta_y_no_guarda(state, bebe, monkeypatch, ext, esperado):
    _planea(monkeypatch, ext)
    msg = FakeMessage()
    await handlers.on_text(msg, state)

    assert esperado in msg.respuestas[-1]
    assert await _pendientes() == []


async def test_avisa_solo_a_quien_lo_pidio_y_una_vez():
    await crud.add_reminder(MAMA, "darle agua", AHORA + timedelta(minutes=2))
    await crud.add_reminder(PAPA, "comprar pañales", AHORA + timedelta(hours=3))
    bot = BotFalso()

    assert await enviar_recordatorios_libres(bot, AHORA) == 0
    assert await enviar_recordatorios_libres(bot, AHORA + timedelta(minutes=3)) == 1
    assert await enviar_recordatorios_libres(bot, AHORA + timedelta(minutes=4)) == 0
    assert bot.enviados == [(MAMA, "⏰ <b>Recordatorio</b>: darle agua")]


async def test_si_llega_tarde_lo_dice():
    await crud.add_reminder(MAMA, "darle agua", AHORA)
    bot = BotFalso()
    await enviar_recordatorios_libres(bot, AHORA + timedelta(hours=2))

    assert "era para las 10:00" in bot.enviados[0][1]


async def test_demo_borra_los_recordatorios_de_ensayos():
    demo = 5100000009
    await reiniciar_demo(demo, AHORA.date())
    await crud.add_reminder(demo, "darle agua", AHORA + timedelta(minutes=2))
    await crud.add_reminder(MAMA, "lo de mamá", AHORA + timedelta(minutes=2))
    await reiniciar_demo(demo, AHORA.date())

    assert [r.owner_id for r in await _pendientes()] == [MAMA]
