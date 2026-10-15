import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bot import bot, dp, registrar_comandos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema ya lo dejó al día 'alembic upgrade head' (comando de arranque).
    # Quita cualquier webhook viejo: polling y webhook no conviven.
    await bot.delete_webhook(drop_pending_updates=True)
    await registrar_comandos()
    # Arranca el POLLING en segundo plano: el bot le pregunta a Telegram por
    # mensajes. Sin webhook ni dominio, hay menos piezas que se puedan romper.
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()


# El servidor web solo existe para que Railway vea un puerto sano (healthcheck).
# El bot de verdad corre por polling en segundo plano.
app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health():
    return {"status": "ok", "app": "bitacora-bebe", "mode": "polling"}
