"""La demo de la charla: Emilia se crea, se reinicia y nunca toca datos reales."""

from datetime import date
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import crud, handlers
from app.config import settings
from app.demo import CONTROLES, HITOS, HITOS_SEMANA, NOMBRE, reiniciar_demo

DEMO, MAMA = 7000000001, 7000000002
HOY = date(2026, 11, 20)


class FakeMessage:
    def __init__(self, user_id):
        self.from_user = SimpleNamespace(id=user_id)
        self.respuestas = []

    async def answer(self, texto, reply_markup=None):
        self.respuestas.append(texto)


@pytest.fixture
def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=DEMO, user_id=DEMO))


async def test_crea_a_emilia_con_todo(monkeypatch):
    r = await reiniciar_demo(DEMO, HOY)

    assert r.ok
    activo = await crud.get_active_child(DEMO)
    assert activo.name == NOMBRE and activo.id == r.child_id
    assert (HOY - activo.birthdate).days == 300
    hitos = await crud.list_milestones(activo.id)
    assert len(hitos) == len(HITOS) + len(HITOS_SEMANA)
    assert any((HOY - h.happened_on).days <= 7 for h in hitos)
    assert len(await crud.list_controls(activo.id)) == len(CONTROLES)
    assert len(await crud.list_advice(activo.id)) == 2
    citas = await crud.list_appointments(activo.id)
    assert len(citas) == 1 and citas[0].scheduled_at.date() > HOY


async def test_reiniciar_borra_lo_del_ensayo_y_queda_igual():
    r1 = await reiniciar_demo(DEMO, HOY)
    await crud.add_milestone(DEMO, r1.child_id, "Dio sus primeros pasos", HOY)
    r2 = await reiniciar_demo(DEMO, HOY)

    assert len(await crud.list_children(DEMO)) == 1
    hitos = await crud.list_milestones(r2.child_id)
    assert len(hitos) == len(HITOS) + len(HITOS_SEMANA)
    assert all(h.description != "Dio sus primeros pasos" for h in hitos)


async def test_no_toca_una_cuenta_con_bebes_reales():
    joshua = await crud.add_child(MAMA, "Joshua")
    await crud.add_milestone(MAMA, joshua.id, "gateó", date(2026, 7, 5))
    r = await reiniciar_demo(MAMA, HOY)

    assert not r.ok
    assert [c.name for c in await crud.list_children(MAMA)] == ["Joshua"]
    assert len(await crud.list_milestones(joshua.id)) == 1


async def test_la_demo_no_borra_otras_familias():
    joshua = await crud.add_child(MAMA, "Joshua")
    await crud.add_control(MAMA, joshua.id, date(2026, 5, 1), 9.0)
    await reiniciar_demo(DEMO, HOY)
    await reiniciar_demo(DEMO, HOY)

    assert await crud.get_child(joshua.id) is not None
    assert len(await crud.list_controls(joshua.id)) == 1


async def test_comando_solo_para_cuentas_de_demo(state, monkeypatch):
    monkeypatch.setattr(settings, "demo_chat_ids", str(DEMO))
    ajena = FakeMessage(MAMA)
    await handlers.cmd_demo(ajena, state)
    assert "no está disponible" in ajena.respuestas[-1]
    assert await crud.list_children(MAMA) == []

    msg = FakeMessage(DEMO)
    await handlers.cmd_demo(msg, state)
    assert "Demo lista" in msg.respuestas[-1]


async def test_comando_apagado_por_defecto(state, monkeypatch):
    monkeypatch.setattr(settings, "demo_chat_ids", "")
    msg = FakeMessage(DEMO)
    await handlers.cmd_demo(msg, state)
    assert "no está disponible" in msg.respuestas[-1]
    assert await crud.list_children(DEMO) == []


async def test_recap_de_la_demo_funciona(state):
    await reiniciar_demo(DEMO, HOY)
    msg = FakeMessage(DEMO)
    await handlers.cmd_recap(msg, state)

    assert any("Gateó por toda la sala" in r for r in msg.respuestas)
