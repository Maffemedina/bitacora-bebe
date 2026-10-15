"""Recordatorios proactivos: el agente escribe primero.

Un ciclo en segundo plano revisa cada pocos minutos las citas que ocurren dentro
de las próximas REMINDER_HOURS horas y avisa a TODOS los miembros de la familia
del bebé. Cada cita se avisa una sola vez (campo 'reminded'); si alguien corrige
la hora de la cita, se vuelve a avisar.

Las citas se guardan en hora local de la familia (TIMEZONE), así que se comparan
contra utils.ahora(), no contra la hora UTC del servidor.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app import crud
from app.config import settings
from app.utils import ahora

log = logging.getLogger(__name__)

INTERVALO_SEG = 300  # cada 5 minutos


def cuando_texto(cita_dt: datetime, ahora_: datetime) -> str:
    """'hoy a las 15:00' / 'mañana a las 09:30' / 'el 27/11 a las 15:00'."""
    dias = (cita_dt.date() - ahora_.date()).days
    hora = f"{cita_dt:%H:%M}"
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    return f"el {cita_dt:%d/%m} a las {hora}"


def texto_recordatorio(nombre: str, cita, ahora_: datetime) -> str:
    lugar = f"\n📍 {cita.location}" if cita.location else ""
    return (
        f"⏰ <b>Recordatorio</b>: {nombre} tiene <b>{cita.title}</b> "
        f"{cuando_texto(cita.scheduled_at, ahora_)}.{lugar}"
    )


def queda_dentro_de_la_ventana(cita_dt: datetime, ahora_: datetime, horas: int) -> bool:
    """¿La cita ya está tan cerca que un recordatorio llegaría 'de inmediato'?"""
    return horas > 0 and ahora_ < cita_dt <= ahora_ + timedelta(hours=horas)


async def enviar_pendientes(bot, ahora_: datetime = None, horas: int = None) -> int:
    """Envía los recordatorios que tocan. Devuelve cuántas citas avisó."""
    ahora_ = ahora_ or ahora()
    horas = settings.reminder_hours if horas is None else horas
    if horas <= 0:
        return 0
    avisadas = 0
    for cita in await crud.citas_por_recordar(ahora_, ahora_ + timedelta(hours=horas)):
        # Se marca ANTES de enviar: si Telegram falla, preferimos no avisar a
        # avisar en bucle cada 5 minutos.
        await crud.marcar_recordada(cita.id)
        hijo = await crud.get_child(cita.child_id)
        if hijo is None or hijo.status != "activo" or hijo.family_id is None:
            continue
        texto = texto_recordatorio(hijo.name, cita, ahora_)
        for miembro in await crud.list_members(hijo.family_id):
            try:
                await bot.send_message(miembro.chat_id, texto)
            except Exception:  # bloqueó el bot, chat borrado, etc.
                log.warning("No pude avisar a %s de la cita %s", miembro.chat_id, cita.id)
        avisadas += 1
        log.info("Recordatorio de la cita %s enviado a la familia %s", cita.id, hijo.family_id)
    return avisadas


async def ciclo_recordatorios(bot) -> None:
    """Corre para siempre junto al polling (ver main.py y run_local.py)."""
    while True:
        try:
            await enviar_pendientes(bot)
        except Exception:
            log.exception("Falló la revisión de recordatorios")
        await asyncio.sleep(INTERVALO_SEG)
