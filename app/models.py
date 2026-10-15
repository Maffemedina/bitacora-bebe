from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, UniqueConstraint
from sqlmodel import Field, SQLModel

# Los IDs de Telegram (chat_id / owner_id) superan el rango INTEGER de Postgres
# (32 bits). Deben guardarse como BIGINT (64 bits) o revientan al insertar/consultar.


class Rol(str, Enum):
    EDITOR = "editor"
    ADMIN = "admin"


# ---------- Familia compartida ----------

class Family(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FamilyMember(SQLModel, table=True):
    """Un usuario (chat_id) miembro de una familia, con su rol.

    Unicidad compuesta (family_id, chat_id): un usuario puede pertenecer a varias
    familias, pero solo una membresía por familia.
    """

    __table_args__ = (UniqueConstraint("family_id", "chat_id", name="uq_family_chat"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    family_id: int = Field(index=True)
    chat_id: int = Field(sa_type=BigInteger, index=True)
    display_name: Optional[str] = None
    role: str = Rol.EDITOR.value  # 'editor' | 'admin'
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Invite(SQLModel, table=True):
    """Invitación de un solo uso a una familia (deep link 'join_<token>')."""

    id: Optional[int] = Field(default=None, primary_key=True)
    family_id: int = Field(index=True)
    token_hash: str = Field(index=True, unique=True)  # SHA-256 del token
    created_by: int = Field(sa_type=BigInteger)
    role_to_grant: str = Rol.EDITOR.value
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Identidad / multi-usuario ----------

class UserProfile(SQLModel, table=True):
    """La persona que usa el bot. Puede tener varios hijos; guarda cuál está activo."""

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, index=True, unique=True)
    active_child_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Child(SQLModel, table=True):
    """Un hijo/bebé. 'status' puede ser 'activo' o 'memoria' (fallecido)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)  # creador histórico (NO autoriza)
    family_id: Optional[int] = Field(default=None, index=True)  # dueña de la autorización
    name: str
    birthdate: Optional[date] = None
    status: str = "activo"  # 'activo' | 'memoria'
    passed_on: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Mundo bebé 🍼 ----------

class Milestone(SQLModel, table=True):
    """Un hito de un hijo: 'habló', 'gateó'... con fecha y foto opcional."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    child_id: int = Field(index=True)
    description: str
    happened_on: date
    photo_ref: Optional[str] = None  # 's3:<key>' o 'tg:<file_id>'
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Appointment(SQLModel, table=True):
    """Una cita: pediatra, vacuna... con recordatorio opcional."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    child_id: int = Field(index=True)
    title: str
    scheduled_at: datetime
    location: Optional[str] = None
    remind: bool = True
    reminded: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Advice(SQLModel, table=True):
    """Una indicación del pediatra (por foto, audio o texto)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    child_id: int = Field(index=True)
    content: str
    source: str = "texto"  # 'foto' | 'audio' | 'texto'
    photo_ref: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Control(SQLModel, table=True):
    """Un control de crecimiento del pediatra: peso, talla, perímetro cefálico."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    child_id: int = Field(index=True)
    fecha: date
    peso_kg: Optional[float] = None
    talla_cm: Optional[float] = None
    perimetro_cm: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Mundo mamá-DS 💻 (fase futura) ----------

class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    content: str
    tag: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Reminder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_type=BigInteger, index=True)
    text: str
    due_at: datetime
    done: bool = False
    reminded: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
