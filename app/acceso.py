"""Quién puede usar el bot (lista de acceso).

Un bot de Telegram es público: cualquiera que encuentre su username puede
escribirle, y cada mensaje gasta la cuota de Gemini de quien lo despliega. Con
ALLOWED_USER_IDS el bot solo atiende a:
  - los IDs de la lista (la familia que lo despliega),
  - quien ya sea miembro de una familia (entró con un enlace de /compartir),
  - quien llega con un enlace de invitación ('/start join_<token>'): el token
    es la autorización, y crud.redimir_invitacion lo valida.
"""

from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app import crud
from app.config import settings


def ids_permitidos(raw: str) -> set:
    """'123, 456' -> {123, 456}. Ignora espacios y valores que no son números."""
    ids = set()
    for parte in (raw or "").replace(";", ",").split(","):
        parte = parte.strip()
        if parte.lstrip("-").isdigit():
            ids.add(int(parte))
    return ids


async def puede_usar(user_id: int, texto: Optional[str], permitidos: set) -> bool:
    if not permitidos or user_id in permitidos:
        return True
    if (texto or "").startswith("/start join_"):
        return True
    return bool(await crud.member_family_ids(user_id))


def mensaje_rechazo(user_id: int) -> str:
    return (
        "🔒 Esta bitácora es privada.\n\n"
        f"Tu ID de Telegram es <code>{user_id}</code>. Si eres de la familia, pide "
        "un enlace de invitación (/compartir) a quien administra el bot."
    )


class AccesoMiddleware(BaseMiddleware):
    """Filtra mensajes y botones antes de que lleguen a los handlers."""

    def __init__(self, permitidos: Optional[set] = None) -> None:
        self.permitidos = (
            permitidos if permitidos is not None else ids_permitidos(settings.allowed_user_ids)
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        texto = event.text if isinstance(event, Message) else None
        if await puede_usar(user.id, texto, self.permitidos):
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(mensaje_rechazo(user.id))
        elif isinstance(event, CallbackQuery):
            await event.answer("🔒 Esta bitácora es privada.", show_alert=True)
        return None
