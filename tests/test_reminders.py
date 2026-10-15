"""Recordatorios proactivos de citas (sin red: un bot falso guarda lo enviado)."""

from datetime import datetime, timedelta

from app import crud
from app.reminders import cuando_texto, enviar_pendientes, queda_dentro_de_la_ventana

MAMA = 5000000001
PAPA = 5000000002
AHORA = datetime(2026, 11, 9, 10, 0)


class BotFalso:
    def __init__(self, falla_para=()):
        self.enviados = []
        self.falla_para = set(falla_para)

    async def send_message(self, chat_id, texto):
        if chat_id in self.falla_para:
            raise RuntimeError("bot bloqueado")
        self.enviados.append((chat_id, texto))


async def _familia_con_cita(cuando: datetime):
    hijo = await crud.add_child(MAMA, "Luna")
    token = await crud.crear_invitacion(hijo.family_id, MAMA)
    await crud.redimir_invitacion(token, PAPA, "Papá")
    cita = await crud.add_appointment(MAMA, hijo.id, "Pediatra", cuando, "Clínica Norte")
    return hijo, cita


def test_cuando_texto():
    assert cuando_texto(datetime(2026, 11, 9, 15, 0), AHORA) == "hoy a las 15:00"
    assert cuando_texto(datetime(2026, 11, 10, 9, 30), AHORA) == "mañana a las 09:30"
    assert cuando_texto(datetime(2026, 11, 27, 15, 0), AHORA) == "el 27/11 a las 15:00"


def test_ventana():
    assert queda_dentro_de_la_ventana(AHORA + timedelta(hours=3), AHORA, 24)
    assert not queda_dentro_de_la_ventana(AHORA + timedelta(hours=30), AHORA, 24)
    assert not queda_dentro_de_la_ventana(AHORA - timedelta(hours=1), AHORA, 24)
    assert not queda_dentro_de_la_ventana(AHORA + timedelta(hours=3), AHORA, 0)


async def test_avisa_a_toda_la_familia_una_sola_vez():
    await _familia_con_cita(AHORA + timedelta(hours=20))
    bot = BotFalso()
    assert await enviar_pendientes(bot, AHORA, 24) == 1
    assert {c for c, _ in bot.enviados} == {MAMA, PAPA}
    assert "Pediatra" in bot.enviados[0][1] and "mañana a las 06:00" in bot.enviados[0][1]
    assert "Clínica Norte" in bot.enviados[0][1]
    assert await enviar_pendientes(bot, AHORA, 24) == 0  # no repite
    assert len(bot.enviados) == 2


async def test_no_avisa_citas_lejanas_ni_pasadas():
    hijo, _ = await _familia_con_cita(AHORA + timedelta(days=3))
    await crud.add_appointment(MAMA, hijo.id, "Vacuna", AHORA - timedelta(hours=2))
    bot = BotFalso()
    assert await enviar_pendientes(bot, AHORA, 24) == 0
    assert bot.enviados == []


async def test_corregir_la_hora_vuelve_a_avisar():
    _, cita = await _familia_con_cita(AHORA + timedelta(hours=5))
    bot = BotFalso()
    await enviar_pendientes(bot, AHORA, 24)
    await crud.update_appointment_datetime(cita.id, AHORA + timedelta(hours=8))
    assert await enviar_pendientes(bot, AHORA, 24) == 1


async def test_si_un_miembro_bloqueo_el_bot_los_demas_igual_reciben():
    await _familia_con_cita(AHORA + timedelta(hours=2))
    bot = BotFalso(falla_para=[PAPA])
    assert await enviar_pendientes(bot, AHORA, 24) == 1
    assert [c for c, _ in bot.enviados] == [MAMA]


async def test_apagados_con_cero_horas():
    await _familia_con_cita(AHORA + timedelta(hours=2))
    assert await enviar_pendientes(BotFalso(), AHORA, 0) == 0
