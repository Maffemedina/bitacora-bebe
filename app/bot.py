import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.acceso import AccesoMiddleware
from app.config import settings
from app.handlers import router

# Logs legibles en la terminal y en Railway. Nunca se registra el CONTENIDO de los
# mensajes (son datos de una familia), solo qué acción se ejecutó.
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# MemoryStorage guarda el estado del onboarding en memoria (suficiente para el
# piloto). En producción real se podría cambiar por Redis.
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# Lista de acceso: corre ANTES de cualquier handler (mensajes y botones).
_acceso = AccesoMiddleware()
dp.message.outer_middleware(_acceso)
dp.callback_query.outer_middleware(_acceso)

# El menú "/" que ve la persona en Telegram. Se registra al arrancar, así no hay
# que configurarlo a mano en @BotFather.
COMANDOS = [
    BotCommand(command="start", description="Empezar o ver qué puedo hacer"),
    BotCommand(command="recap", description="Todos los hitos del bebé"),
    BotCommand(command="semana", description="Resumen de la semana"),
    BotCommand(command="compartir", description="Invitar a alguien de la familia"),
    BotCommand(command="mi_familia", description="Miembros y permisos"),
    BotCommand(command="informe", description="PDF para llevar al pediatra"),
    BotCommand(command="mi_id", description="Tu ID de Telegram"),
]


async def registrar_comandos() -> None:
    try:
        await bot.set_my_commands(COMANDOS)
    except Exception:
        pass  # sin red o token inválido: el bot igual funciona sin el menú
