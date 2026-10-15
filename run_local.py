"""Corre el bot en tu computador (modo polling), sin URL pública ni servidor web.

El esquema de la base se gestiona con Alembic ('alembic upgrade head'), igual que
en producción.

Uso:  python run_local.py
En Railway arranca app/main.py (ver railway.json / Procfile).

Ojo: Telegram solo entrega los mensajes a UNA instancia a la vez. Si tu bot ya
corre en Railway, apágalo allá (o usa otro token) antes de correrlo en local.
"""

import asyncio

from alembic import command
from alembic.config import Config


async def main() -> None:
    # Importar aquí (con el loop ya en marcha) evita el error de aiogram+uvloop en
    # Python 3.9, que al crear el Dispatcher al importar busca un event loop inexistente.
    from app.bot import bot, dp, registrar_comandos

    await bot.delete_webhook(drop_pending_updates=True)
    await registrar_comandos()
    print("🍼 Bitácora Bebé corriendo en modo polling.")
    print("   Abre tu bot en Telegram y escríbele /start")
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Deja el esquema al día con Alembic antes de arrancar.
    command.upgrade(Config("alembic.ini"), "head")
    asyncio.run(main())
