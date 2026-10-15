from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la Bitácora Bebé.

    Lee variables de entorno (o del archivo .env en local). Solo TELEGRAM_BOT_TOKEN
    es obligatoria; GEMINI_API_KEY hace falta para que el agente entienda mensajes.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str
    telegram_bot_username: str = ""  # para los deep links de /compartir (sin @)

    # Quién puede usar el bot: IDs numéricos de Telegram separados por coma.
    # Vacío = abierto a cualquiera (cada mensaje gasta TU cuota de Gemini).
    # Los familiares que entren con un enlace de /compartir quedan permitidos.
    allowed_user_ids: str = ""

    # Nivel de logs: INFO muestra cada mensaje atendido y qué entendió el agente.
    log_level: str = "INFO"

    # Recordatorios de citas: cuántas horas antes avisar (0 = apagados).
    reminder_hours: int = 24

    # Gemini: el cerebro del agente
    gemini_api_key: str = ""
    # Modelo FIJO (no un alias): 'gemini-flash-latest' se mueve solo y puede caer
    # en un modelo con free tier diminuto. Pinéalo para tener cuota estable.
    gemini_model: str = "gemini-2.5-flash"

    # Zona horaria de la familia: define qué es "hoy" (el servidor corre en UTC).
    timezone: str = "America/Bogota"

    # Base de datos: sqlite en local, Postgres en Railway (DATABASE_URL)
    database_url: str = "sqlite+aiosqlite:///./bitacora.db"

    # Carpeta de un volumen persistente (Railway) para guardar fotos/videos.
    # Vacío = se usan las referencias de Telegram (no duraderas).
    media_dir: str = ""

    # S3 para fotos de los hitos (alternativa al volumen)
    s3_bucket: str = ""
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""


settings = Settings()
