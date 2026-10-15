from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import settings
from app.handlers import router

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# MemoryStorage guarda el estado del onboarding en memoria (suficiente para el
# piloto). En producción real se podría cambiar por Redis.
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# El menú "/" que ve la persona en Telegram. Se registra al arrancar, así no hay
# que configurarlo a mano en @BotFather.
COMANDOS = [
    BotCommand(command="start", description="Empezar o ver qué puedo hacer"),
    BotCommand(command="recap", description="Todos los hitos del bebé"),
    BotCommand(command="semana", description="Resumen de la semana"),
    BotCommand(command="compartir", description="Invitar a alguien de la familia"),
    BotCommand(command="mi_familia", description="Miembros y permisos"),
]


async def registrar_comandos() -> None:
    try:
        await bot.set_my_commands(COMANDOS)
    except Exception:
        pass  # sin red o token inválido: el bot igual funciona sin el menú
