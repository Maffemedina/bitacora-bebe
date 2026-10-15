"""Prueba de migración de familia: corre Alembic REAL sobre una SQLite temporal
desde el esquema previo (0001) y valida el backfill (no `create_all`).
"""

import os
import tempfile

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BIG_A = 6000000001  # > int32, como chat_id real
BIG_B = 7000000001


def _cfg(async_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", async_url)
    return cfg


def _nueva_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # que aiosqlite la cree limpia
    return path


def test_migracion_familia_backfill_desde_esquema_previo():
    path = _nueva_db()
    cfg = _cfg(f"sqlite+aiosqlite:///{path}")
    eng = sa.create_engine(f"sqlite:///{path}")
    try:
        command.upgrade(cfg, "0001")  # esquema PREVIO, sin familia
        with eng.begin() as c:
            for owner, nombre in [(BIG_A, "Luna"), (BIG_A, "Sara"), (BIG_B, "Mateo")]:
                c.execute(
                    sa.text(
                        "INSERT INTO child (owner_id, name, status, created_at) "
                        "VALUES (:o, :n, 'activo', '2024-01-01')"
                    ),
                    {"o": owner, "n": nombre},
                )

        command.upgrade(cfg, "head")  # crea familia + backfill

        with eng.connect() as c:
            familias = c.execute(sa.text("SELECT COUNT(*) FROM family")).scalar()
            miembros = {
                tuple(row)
                for row in c.execute(sa.text("SELECT chat_id, role FROM familymember"))
            }
            sin_familia = c.execute(
                sa.text("SELECT COUNT(*) FROM child WHERE family_id IS NULL")
            ).scalar()
            fams_a = c.execute(
                sa.text("SELECT DISTINCT family_id FROM child WHERE owner_id = :o"),
                {"o": BIG_A},
            ).scalars().all()

        assert familias == 2                      # una familia por owner
        assert (BIG_A, "admin") in miembros       # owner queda admin
        assert (BIG_B, "admin") in miembros
        assert sin_familia == 0                   # todos con familia (idempotente en NULLs)
        assert len(fams_a) == 1                   # Luna y Sara en la MISMA familia
    finally:
        eng.dispose()
        if os.path.exists(path):
            os.remove(path)


def test_db_previa_pasa_a_head_y_es_usable_con_child_actual():
    from app.models import Child

    path = _nueva_db()
    cfg = _cfg(f"sqlite+aiosqlite:///{path}")
    eng = sa.create_engine(f"sqlite:///{path}")
    try:
        command.upgrade(cfg, "0001")  # esquema previo
        command.upgrade(cfg, "head")  # hasta familia

        cols = {c["name"] for c in sa.inspect(eng).get_columns("child")}
        esperadas = set(Child.__table__.columns.keys())
        assert esperadas <= cols          # el esquema migrado tiene TODAS las columnas del modelo
        assert "family_id" in cols

        with eng.begin() as c:            # y es usable: insertar con family_id
            c.execute(
                sa.text(
                    "INSERT INTO child (owner_id, family_id, name, status, created_at) "
                    "VALUES (99, 1, 'Nuevo', 'activo', '2024-01-01')"
                )
            )
            fid = c.execute(
                sa.text("SELECT family_id FROM child WHERE name = 'Nuevo'")
            ).scalar()
        assert fid == 1
    finally:
        eng.dispose()
        if os.path.exists(path):
            os.remove(path)
