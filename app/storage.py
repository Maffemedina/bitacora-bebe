"""Dónde se guardan las fotos y videos: volumen persistente (MEDIA_DIR) o S3.

Opcional. Si no hay bucket configurado, las funciones
avisan con una excepción clara en vez de fallar de forma rara.
"""

import os
import uuid

from app.config import settings


# ---------- Volumen persistente (Railway) ----------

def save_media(data: bytes, ext: str) -> str:
    """Guarda bytes en el volumen y devuelve una referencia 'vol:media/<archivo>'."""
    folder = os.path.join(settings.media_dir, "media")
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return f"vol:media/{name}"


def media_fullpath(ref: str) -> str:
    """Ruta absoluta de una referencia 'vol:...'."""
    return os.path.join(settings.media_dir, ref[len("vol:"):])


def _client():
    if not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET no está configurado (ver .env).")
    import boto3  # import perezoso: solo se necesita si usas S3

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


def upload_photo(data: bytes, content_type: str = "image/jpeg") -> str:
    """Sube una foto y devuelve su 'key' (lo que guardamos en la DB)."""
    key = f"hitos/{uuid.uuid4().hex}.jpg"
    _client().put_object(
        Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
    )
    return key


def presigned_url(key: str, expires: int = 3600) -> str:
    """URL temporal para mostrar la foto (ej. en el recap)."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )
