"""Fotos y videos: preguntar a qué hito va y moverlos por lenguaje natural.

Sin red: Telegram y Gemini se reemplazan por dobles; el video se guarda como
referencia 'tgv:' porque en los tests no hay MEDIA_DIR.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import agent, crud, handlers
from app.agent import Extraccion
from app.handlers import _elegir_origen_media, _sin_nombre, _tipo_media

A, B = 100, 200
RELLENO = "Un video para recordar"


class FakeMessage:
    def __init__(self, user_id=A, text=None, caption=None, video=None):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.caption = caption
        self.video = video
        self.respuestas = []
        self.teclados = []

    async def answer(self, texto, reply_markup=None):
        self.respuestas.append(texto)
        self.teclados.append(reply_markup)


def _video(file_id="abc"):
    return SimpleNamespace(file_id=file_id)


def _cb(data, message, user_id=A):
    async def answer():
        return None

    return SimpleNamespace(
        data=data, message=message, from_user=SimpleNamespace(id=user_id), answer=answer
    )


def _planea(monkeypatch, *acciones):
    async def planear(mensaje, hoy_iso, baby_name, contexto=""):
        return list(acciones)

    monkeypatch.setattr(agent, "planear", planear)


@pytest.fixture
def state():
    key = StorageKey(bot_id=1, chat_id=A, user_id=A)
    return FSMContext(storage=MemoryStorage(), key=key)


@pytest.fixture
async def joshua():
    child = await crud.add_child(A, "Joshua")
    await crud.set_active_child(A, child.id)
    return child


# ---------- Helpers puros ----------

def test_tipo_media():
    assert _tipo_media("tgv:abc") == "video"
    assert _tipo_media("vol:media/a.mp4") == "video"
    assert _tipo_media("vol:media/a.jpg") == "foto"
    assert _tipo_media("tg:abc") == "foto"


def test_origen_es_el_mas_reciente_del_tipo_pedido():
    viejo = SimpleNamespace(description="gateó", photo_ref="tgv:v", created_at=datetime(2026, 1, 1))
    nuevo = SimpleNamespace(description="rió", photo_ref="tg:f", created_at=datetime(2026, 2, 1))
    vacio = SimpleNamespace(description="habló", photo_ref=None, created_at=datetime(2026, 3, 1))
    assert _elegir_origen_media([viejo, nuevo, vacio], None) is nuevo
    assert _elegir_origen_media([viejo, nuevo, vacio], "video") is viejo
    assert _elegir_origen_media([vacio], None) is None


def test_origen_prefiere_el_relleno_aunque_sea_mas_viejo():
    relleno = SimpleNamespace(description=RELLENO, photo_ref="tgv:r", created_at=datetime(2026, 1, 1))
    real = SimpleNamespace(description="gateó", photo_ref="tgv:v", created_at=datetime(2026, 2, 1))
    assert _elegir_origen_media([relleno, real], "video") is relleno


def test_sin_nombre_quita_al_bebe_de_la_referencia():
    assert _sin_nombre("Joshua gateó", "Joshua") == "gateó"
    assert _sin_nombre(None, "Joshua") == ""


# ---------- Video sin descripción ----------

async def test_video_sin_descripcion_pregunta_y_no_crea_hito(state, joshua):
    await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)

    assert "A qué hito" in msg.respuestas[-1]
    assert len(await crud.list_milestones(joshua.id)) == 1
    assert (await state.get_data())["media_sin_hito"] == "tgv:abc"
    botones = [b.text for fila in msg.teclados[-1].inline_keyboard for b in fila]
    assert any("gateó" in b for b in botones)


async def test_boton_guarda_el_video_en_el_hito(state, joshua):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)
    await handlers.cb_mediahito(_cb(f"mediahito:{m.id}", msg), state)

    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:abc"
    assert (await state.get_data())["media_sin_hito"] is None


async def test_ajeno_no_usa_el_boton(state, joshua):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)
    await handlers.cb_mediahito(_cb(f"mediahito:{m.id}", msg, user_id=B), state)

    assert (await crud.get_milestone(m.id)).photo_ref is None


async def test_segundo_video_no_pisa_al_pendiente(state, joshua):
    await handlers.on_video(FakeMessage(video=_video("uno")), state)
    msg = FakeMessage(video=_video("dos"))
    await handlers.on_video(msg, state)

    assert "archivo anterior" in msg.respuestas[-1]
    assert (await state.get_data())["media_sin_hito"] == "tgv:uno"


async def test_responder_con_momento_nuevo_lo_guarda_con_el_video(state, joshua, monkeypatch):
    await handlers.on_video(FakeMessage(video=_video()), state)
    _planea(monkeypatch, Extraccion(intent="guardar_hito", descripcion="gateó", fecha="2026-07-05"))
    msg = FakeMessage(text="gateó el 5 de julio")
    await handlers.on_text(msg, state)

    hitos = await crud.list_milestones(joshua.id)
    assert [(h.description, h.happened_on, h.photo_ref) for h in hitos] == [
        ("gateó", date(2026, 7, 5), "tgv:abc")
    ]
    assert (await state.get_data())["media_sin_hito"] is None


async def test_responder_con_hito_existente_no_lo_duplica(state, joshua, monkeypatch):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    await handlers.on_video(FakeMessage(video=_video()), state)
    _planea(monkeypatch, Extraccion(intent="adjuntar_media", referencia="gateó"))
    await handlers.on_text(FakeMessage(text="al de gateó"), state)

    assert [h.id for h in await crud.list_milestones(joshua.id)] == [m.id]
    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:abc"


async def test_descartar_no_guarda_nada(state, joshua):
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)
    await handlers.cb_mediadescartar(_cb("mediadescartar", msg), state)

    assert await crud.list_milestones(joshua.id) == []
    assert (await state.get_data())["media_sin_hito"] is None


# ---------- «El video que te envié pásalo al hito de...» ----------

async def test_mueve_el_video_y_borra_el_relleno(state, joshua, monkeypatch):
    """El caso real: un video quedó en un hito de relleno y se pide pasarlo a «gateó»."""
    relleno = await crud.add_milestone(A, joshua.id, RELLENO, date(2026, 11, 3), "vol:media/a.mp4")
    gateo = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(
        monkeypatch,
        Extraccion(intent="adjuntar_media", referencia="Joshua gateó", tipo_media="video"),
    )
    msg = FakeMessage(text="el video que te envié pásalo al hito de joshua gateó")
    await handlers.on_text(msg, state)

    assert (await crud.get_milestone(gateo.id)).photo_ref == "vol:media/a.mp4"
    assert await crud.get_milestone(relleno.id) is None
    assert "pasé el video" in msg.respuestas[-1]


async def test_crea_el_hito_si_no_existe(state, joshua, monkeypatch):
    relleno = await crud.add_milestone(A, joshua.id, RELLENO, date(2026, 11, 3), "tgv:abc")
    _planea(
        monkeypatch,
        Extraccion(
            intent="adjuntar_media", referencia="gateó", descripcion="gateó",
            fecha="2026-07-05", tipo_media="video",
        ),
    )
    await handlers.on_text(FakeMessage(text="guárdalo como evidencia de que gateó"), state)

    hitos = await crud.list_milestones(joshua.id)
    assert [(h.description, h.happened_on, h.photo_ref) for h in hitos] == [
        ("gateó", date(2026, 7, 5), "tgv:abc")
    ]
    assert await crud.get_milestone(relleno.id) is None


async def test_si_el_origen_es_un_hito_real_pide_confirmar(state, joshua, monkeypatch):
    real = await crud.add_milestone(A, joshua.id, "sonrió", date(2026, 6, 1), "tgv:abc")
    gateo = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    _planea(monkeypatch, Extraccion(intent="adjuntar_media", referencia="gateó"))
    msg = FakeMessage(text="pasa el video al hito de que gateó")
    await handlers.on_text(msg, state)

    assert (await crud.get_milestone(gateo.id)).photo_ref is None  # aún no se movió
    data = msg.teclados[-1].inline_keyboard[0][0].callback_data
    assert data == f"movmedia:{real.id}:{gateo.id}"

    await handlers.cb_movmedia(_cb(data, msg))
    assert (await crud.get_milestone(gateo.id)).photo_ref == "tgv:abc"
    origen = await crud.get_milestone(real.id)
    assert origen is not None and origen.photo_ref is None  # el hito real se conserva


async def test_ajeno_no_mueve_media(state, joshua):
    real = await crud.add_milestone(A, joshua.id, "sonrió", date(2026, 6, 1), "tgv:abc")
    gateo = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5))
    await handlers.cb_movmedia(_cb(f"movmedia:{real.id}:{gateo.id}", FakeMessage(), user_id=B))

    assert (await crud.get_milestone(real.id)).photo_ref == "tgv:abc"
    assert (await crud.get_milestone(gateo.id)).photo_ref is None


async def test_no_pisa_un_hito_que_ya_tiene_archivo(state, joshua, monkeypatch):
    await crud.add_milestone(A, joshua.id, RELLENO, date(2026, 11, 3), "tgv:nuevo")
    gateo = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:viejo")
    _planea(monkeypatch, Extraccion(intent="adjuntar_media", referencia="gateó"))
    msg = FakeMessage(text="pasa el video al hito de que gateó")
    await handlers.on_text(msg, state)

    assert (await crud.get_milestone(gateo.id)).photo_ref == "tgv:viejo"
    assert "ya tiene un video" in msg.respuestas[-1]


async def test_sin_archivos_lo_dice(state, joshua, monkeypatch):
    _planea(monkeypatch, Extraccion(intent="adjuntar_media", referencia="gateó"))
    msg = FakeMessage(text="pasa el video al hito de que gateó")
    await handlers.on_text(msg, state)

    assert "No encontré ningún archivo" in msg.respuestas[-1]


# ---------- Hito esperando archivo: que no se pegue al equivocado ----------

async def _hito_esperando(state, joshua, descripcion="gateó"):
    m = await crud.add_milestone(A, joshua.id, descripcion, date(2026, 7, 5))
    await state.update_data(pending_media_hito=m.id)
    return m


def _clasifica(monkeypatch, **plan):
    vistos = {}

    async def clasificar(caption, hoy_iso, baby_name, hito_esperando=None):
        vistos["hito_esperando"] = hito_esperando
        return agent.MediaPlan(**plan)

    monkeypatch.setattr(agent, "clasificar_media", clasificar)
    return vistos


async def test_sin_descripcion_va_al_hito_esperando_y_dice_cual(state, joshua):
    m = await _hito_esperando(state, joshua)
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)

    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:abc"
    assert "gateó" in msg.respuestas[-1]
    assert (await state.get_data())["pending_media_hito"] is None
    botones = [b.callback_data for fila in msg.teclados[-1].inline_keyboard for b in fila]
    assert f"mediaotro:{m.id}" in botones


async def test_la_descripcion_manda_sobre_el_hito_esperando(state, joshua, monkeypatch):
    gateo = await _hito_esperando(state, joshua)
    papa = await crud.add_milestone(A, joshua.id, "dijo papá", date(2026, 1, 15))
    vistos = _clasifica(monkeypatch, accion="adjuntar", referencia="dijo papá")
    msg = FakeMessage(video=_video(), caption="cuando dijo papá")
    await handlers.on_video(msg, state)

    assert (await crud.get_milestone(gateo.id)).photo_ref is None
    assert (await crud.get_milestone(papa.id)).photo_ref == "tgv:abc"
    assert vistos["hito_esperando"] == "gateó"
    assert "dijo papá" in msg.respuestas[-1]


async def test_seguir_conversando_cancela_la_oferta(state, joshua, monkeypatch):
    m = await _hito_esperando(state, joshua)
    _planea(monkeypatch, Extraccion(intent="otro"))
    await handlers.on_text(FakeMessage(text="hola"), state)
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)

    assert (await crud.get_milestone(m.id)).photo_ref is None
    assert "A qué hito" in msg.respuestas[-1]


async def test_no_era_ese_saca_el_archivo_y_pregunta(state, joshua):
    m = await _hito_esperando(state, joshua)
    msg = FakeMessage(video=_video())
    await handlers.on_video(msg, state)
    await handlers.cb_mediaotro(_cb(f"mediaotro:{m.id}", msg), state)

    assert (await crud.get_milestone(m.id)).photo_ref is None
    assert (await state.get_data())["media_sin_hito"] == "tgv:abc"
    assert "A qué hito" in msg.respuestas[-1]


async def test_ajeno_no_usa_no_era_ese(state, joshua):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:v")
    msg = FakeMessage()
    await handlers.cb_mediaotro(_cb(f"mediaotro:{m.id}", msg, user_id=B), state)

    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:v"


async def test_si_gemini_falla_con_descripcion_pregunta_sin_crear_hito(state, joshua, monkeypatch):
    _clasifica(monkeypatch, accion="error")
    msg = FakeMessage(video=_video(), caption="gateó")
    await handlers.on_video(msg, state)

    assert await crud.list_milestones(joshua.id) == []
    assert "A qué hito" in msg.respuestas[-1]


# ---------- Hito que ya tiene archivo ----------

async def test_descripcion_no_pisa_y_ofrece_reemplazar(state, joshua, monkeypatch):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:viejo")
    _clasifica(monkeypatch, accion="adjuntar", referencia="gateó")
    msg = FakeMessage(video=_video(), caption="del día que gateó")
    await handlers.on_video(msg, state)

    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:viejo"
    assert "ya tiene un video" in msg.respuestas[-1]
    botones = [b.callback_data for fila in msg.teclados[-1].inline_keyboard for b in fila]
    assert f"mediareemp:{m.id}" in botones

    await handlers.cb_mediareemp(_cb(f"mediareemp:{m.id}", msg), state)
    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:abc"
    assert (await state.get_data())["media_sin_hito"] is None


async def test_ajeno_no_reemplaza(state, joshua):
    m = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:viejo")
    await state.update_data(media_sin_hito="tgv:abc")
    await handlers.cb_mediareemp(_cb(f"mediareemp:{m.id}", FakeMessage(), user_id=B), state)

    assert (await crud.get_milestone(m.id)).photo_ref == "tgv:viejo"


async def test_mover_con_reemplazo_solo_si_se_confirma(state, joshua, monkeypatch):
    destino = await crud.add_milestone(A, joshua.id, "gateó", date(2026, 7, 5), "tgv:viejo")
    origen = await crud.add_milestone(A, joshua.id, "dijo papá", date(2026, 1, 15), "tgv:nuevo")
    _planea(monkeypatch, Extraccion(intent="adjuntar_media", referencia="gateó", tipo_media="video"))
    msg = FakeMessage(text="el video pásalo al hito de gateó")
    await handlers.on_text(msg, state)

    assert (await crud.get_milestone(destino.id)).photo_ref == "tgv:viejo"
    assert "lo reemplace" in msg.respuestas[-1]
    botones = [b.callback_data for fila in msg.teclados[-1].inline_keyboard for b in fila]
    assert f"movmedia:{origen.id}:{destino.id}:r" in botones

    await handlers.cb_movmedia(_cb(f"movmedia:{origen.id}:{destino.id}:r", msg))
    assert (await crud.get_milestone(destino.id)).photo_ref == "tgv:nuevo"
    assert (await crud.get_milestone(origen.id)).photo_ref is None
