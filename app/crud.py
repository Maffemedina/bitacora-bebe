"""Capa de acceso a datos (CRUD).

Funciones sencillas para guardar y consultar, separadas de los handlers para que
el agente (Gemini) pueda usarlas como 'herramientas'.
"""

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, update

from app import roles
from app.db import SessionLocal
from app.models import (
    Advice,
    Appointment,
    Child,
    Control,
    Family,
    FamilyMember,
    Invite,
    Milestone,
    Rol,
    UserProfile,
)
from app.utils import hoy


# ---------- Familia (membresía y scope) ----------

async def member_family_ids(chat_id: int) -> list:
    """IDs de las familias donde el usuario es miembro vigente."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(FamilyMember.family_id).where(FamilyMember.chat_id == chat_id)
        )
        return list(result.scalars().all())


async def is_member(chat_id: int, family_id: Optional[int]) -> bool:
    if family_id is None:
        return False
    async with SessionLocal() as session:
        result = await session.execute(
            select(FamilyMember.id).where(
                FamilyMember.chat_id == chat_id,
                FamilyMember.family_id == family_id,
            )
        )
        return result.scalars().first() is not None


async def member_role(chat_id: int, family_id: int) -> Optional[str]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(FamilyMember.role).where(
                FamilyMember.chat_id == chat_id,
                FamilyMember.family_id == family_id,
            )
        )
        return result.scalars().first()


async def resolver_hijo(
    chat_id: int, child_id: int, rol_min: Rol = Rol.EDITOR
) -> Optional[Child]:
    """Núcleo de autorización: devuelve el hijo SOLO si chat_id es miembro vigente
    de su familia con rol suficiente. Se usa en mutaciones y callbacks.
    """
    child = await get_child(child_id)
    if child is None or child.family_id is None:
        return None
    rol = await member_role(chat_id, child.family_id)
    if rol is None or not roles.alcanza(rol, rol_min):
        return None
    return child


async def family_children(family_id: int) -> Sequence[Child]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.family_id == family_id).order_by(Child.created_at)
        )
        return result.scalars().all()


# ---------- Invitaciones (familia compartida) ----------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def crear_invitacion(family_id: int, created_by: int, horas: int = 24) -> str:
    """Crea una invitación de un solo uso. Devuelve el TOKEN en claro (para el link);
    en la DB solo se guarda su hash SHA-256."""
    token = secrets.token_urlsafe(32)
    async with SessionLocal() as session:
        session.add(
            Invite(
                family_id=family_id,
                token_hash=_hash_token(token),
                created_by=created_by,
                role_to_grant=Rol.EDITOR.value,
                expires_at=datetime.utcnow() + timedelta(hours=horas),
            )
        )
        await session.commit()
    return token


async def redimir_invitacion(
    token: str, chat_id: int, display_name: Optional[str] = None
) -> Optional[int]:
    """Redención ATÓMICA: reclama la invitación (no usada y vigente) y crea la
    membresía en la MISMA transacción. Devuelve family_id si tuvo éxito, o None si
    es inválida/vencida/ya usada. A prueba de doble uso."""
    token_hash = _hash_token(token)
    now = datetime.utcnow()
    async with SessionLocal() as session:
        async with session.begin():
            claimed = await session.execute(
                update(Invite)
                .where(
                    Invite.token_hash == token_hash,
                    Invite.used_at.is_(None),
                    Invite.expires_at > now,
                )
                .values(used_at=now)
            )
            if claimed.rowcount != 1:
                return None  # inexistente / vencida / ya usada
            inv = (
                await session.execute(
                    select(Invite).where(Invite.token_hash == token_hash)
                )
            ).scalars().first()
            ya_miembro = (
                await session.execute(
                    select(FamilyMember.id).where(
                        FamilyMember.family_id == inv.family_id,
                        FamilyMember.chat_id == chat_id,
                    )
                )
            ).scalars().first()
            if ya_miembro is None:
                session.add(
                    FamilyMember(
                        family_id=inv.family_id,
                        chat_id=chat_id,
                        display_name=display_name,
                        role=inv.role_to_grant,
                    )
                )
            family_id = inv.family_id
    return family_id


async def list_members(family_id: int) -> Sequence[FamilyMember]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(FamilyMember)
            .where(FamilyMember.family_id == family_id)
            .order_by(FamilyMember.created_at)
        )
        return result.scalars().all()


async def revocar_miembro(family_id: int, chat_id: int) -> bool:
    """Quita a un miembro de la familia. El revocado pierde el acceso de inmediato."""
    async with SessionLocal() as session:
        m = (
            await session.execute(
                select(FamilyMember).where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.chat_id == chat_id,
                )
            )
        ).scalars().first()
        if m is None:
            return False
        await session.delete(m)
        await session.commit()
        return True


async def ensure_family_for(chat_id: int, display_name: Optional[str] = None) -> int:
    """Familia donde el usuario es miembro; si no tiene ninguna, crea una con él
    como admin. Devuelve el family_id."""
    ids = await member_family_ids(chat_id)
    if ids:
        return ids[0]
    async with SessionLocal() as session:
        family = Family()
        session.add(family)
        await session.commit()
        await session.refresh(family)
        session.add(
            FamilyMember(
                family_id=family.id,
                chat_id=chat_id,
                display_name=display_name,
                role=Rol.ADMIN.value,
            )
        )
        await session.commit()
        return family.id


async def reparar_family_id(chat_id: int) -> None:
    """Asigna family_id a hijos huérfanos (creados durante la transición) del owner."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Child.id).where(Child.owner_id == chat_id, Child.family_id.is_(None))
        )
        huerfanos = list(result.scalars().all())
    if not huerfanos:
        return
    family_id = await ensure_family_for(chat_id)
    async with SessionLocal() as session:
        for cid in huerfanos:
            obj = await session.get(Child, cid)
            obj.family_id = family_id
            session.add(obj)
        await session.commit()


# ---------- Perfil ----------

async def get_profile(chat_id: int) -> Optional[UserProfile]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.chat_id == chat_id)
        )
        return result.scalars().first()


async def ensure_profile(chat_id: int) -> UserProfile:
    profile = await get_profile(chat_id)
    if profile:
        return profile
    async with SessionLocal() as session:
        profile = UserProfile(chat_id=chat_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


# ---------- Hijos ----------

async def add_child(chat_id: int, name: str, birthdate: Optional[date] = None) -> Child:
    """Crea un hijo (con family_id) y lo deja como el activo.

    Familia destino: la del hijo activo si el usuario es miembro; si no, la suya
    (creándola con el usuario como admin si aún no tiene ninguna).
    """
    await ensure_profile(chat_id)
    family_id: Optional[int] = None
    activo = await get_active_child(chat_id)
    if activo is not None and await is_member(chat_id, activo.family_id):
        family_id = activo.family_id
    if family_id is None:
        family_id = await ensure_family_for(chat_id)

    async with SessionLocal() as session:
        child = Child(owner_id=chat_id, family_id=family_id, name=name, birthdate=birthdate)
        session.add(child)
        await session.commit()
        await session.refresh(child)
        profile = (
            await session.execute(
                select(UserProfile).where(UserProfile.chat_id == chat_id)
            )
        ).scalars().first()
        profile.active_child_id = child.id
        session.add(profile)
        await session.commit()
        return child


async def get_child(child_id: int) -> Optional[Child]:
    async with SessionLocal() as session:
        return await session.get(Child, child_id)


async def get_active_child(chat_id: int) -> Optional[Child]:
    """Hijo activo, SOLO si el usuario es miembro vigente de su familia.

    Revocado o hijo de otra familia → None (validación de acceso inmediata).
    """
    await reparar_family_id(chat_id)
    profile = await get_profile(chat_id)
    if not profile or not profile.active_child_id:
        return None
    child = await get_child(profile.active_child_id)
    if child is None or not await is_member(chat_id, child.family_id):
        return None
    return child


async def set_active_child(chat_id: int, child_id: int) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.chat_id == chat_id)
        )
        profile = result.scalars().first()
        if profile:
            profile.active_child_id = child_id
            session.add(profile)
            await session.commit()


async def list_children(chat_id: int) -> Sequence[Child]:
    """Hijos de TODAS las familias donde el usuario es miembro (multi-familia)."""
    await reparar_family_id(chat_id)
    fam_ids = await member_family_ids(chat_id)
    if not fam_ids:
        return []
    async with SessionLocal() as session:
        result = await session.execute(
            select(Child)
            .where(Child.family_id.in_(fam_ids))
            .order_by(Child.created_at)
        )
        return result.scalars().all()


async def find_child_by_name(chat_id: int, name: str) -> Optional[Child]:
    name = name.strip().lower()
    for child in await list_children(chat_id):
        if child.name.lower() == name:
            return child
    # coincidencia parcial como respaldo
    for child in await list_children(chat_id):
        if name in child.name.lower():
            return child
    return None


async def set_child_birthdate(child_id: int, birthdate: date) -> Optional[Child]:
    async with SessionLocal() as session:
        child = await session.get(Child, child_id)
        if not child:
            return None
        child.birthdate = birthdate
        session.add(child)
        await session.commit()
        await session.refresh(child)
        return child


async def mark_child_memoria(child_id: int, passed_on: date) -> Optional[Child]:
    async with SessionLocal() as session:
        child = await session.get(Child, child_id)
        if not child:
            return None
        child.status = "memoria"
        child.passed_on = passed_on
        session.add(child)
        await session.commit()
        await session.refresh(child)
        return child


# ---------- Hitos ----------

async def add_milestone(
    owner_id: int,
    child_id: int,
    description: str,
    happened_on: date,
    photo_ref: Optional[str] = None,
) -> Milestone:
    async with SessionLocal() as session:
        m = Milestone(
            owner_id=owner_id,
            child_id=child_id,
            description=description,
            happened_on=happened_on,
            photo_ref=photo_ref,
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)
        return m


async def list_milestones(child_id: int) -> Sequence[Milestone]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Milestone)
            .where(Milestone.child_id == child_id)
            .order_by(Milestone.happened_on)
        )
        return result.scalars().all()


async def get_milestone(milestone_id: int) -> Optional[Milestone]:
    async with SessionLocal() as session:
        return await session.get(Milestone, milestone_id)


async def update_milestone_date(milestone_id: int, new_date: date) -> Optional[Milestone]:
    async with SessionLocal() as session:
        m = await session.get(Milestone, milestone_id)
        if not m:
            return None
        m.happened_on = new_date
        session.add(m)
        await session.commit()
        await session.refresh(m)
        return m


async def update_milestone_media(milestone_id: int, media_ref: str) -> Optional[Milestone]:
    async with SessionLocal() as session:
        m = await session.get(Milestone, milestone_id)
        if not m:
            return None
        m.photo_ref = media_ref
        session.add(m)
        await session.commit()
        await session.refresh(m)
        return m


async def delete_milestone(milestone_id: int) -> bool:
    async with SessionLocal() as session:
        m = await session.get(Milestone, milestone_id)
        if not m:
            return False
        await session.delete(m)
        await session.commit()
        return True


# ---------- Citas ----------

async def add_appointment(
    owner_id: int,
    child_id: int,
    title: str,
    scheduled_at: datetime,
    location: Optional[str] = None,
) -> Appointment:
    async with SessionLocal() as session:
        appt = Appointment(
            owner_id=owner_id,
            child_id=child_id,
            title=title,
            scheduled_at=scheduled_at,
            location=location,
        )
        session.add(appt)
        await session.commit()
        await session.refresh(appt)
        return appt


async def list_upcoming_appointments(child_id: int) -> Sequence[Appointment]:
    inicio = datetime.combine(hoy(), datetime.min.time())
    async with SessionLocal() as session:
        result = await session.execute(
            select(Appointment)
            .where(Appointment.child_id == child_id)
            .where(Appointment.scheduled_at >= inicio)
            .order_by(Appointment.scheduled_at)
        )
        return result.scalars().all()


async def list_appointments(child_id: int) -> Sequence[Appointment]:
    """Todas las citas del hijo (incluidas pasadas), para poder corregirlas."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Appointment)
            .where(Appointment.child_id == child_id)
            .order_by(Appointment.scheduled_at)
        )
        return result.scalars().all()


async def update_appointment_datetime(
    appointment_id: int, new_dt: datetime
) -> Optional[Appointment]:
    async with SessionLocal() as session:
        c = await session.get(Appointment, appointment_id)
        if not c:
            return None
        c.scheduled_at = new_dt
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c


# ---------- Controles de crecimiento ----------

async def add_control(
    owner_id: int,
    child_id: int,
    fecha: date,
    peso_kg: Optional[float] = None,
    talla_cm: Optional[float] = None,
    perimetro_cm: Optional[float] = None,
) -> Control:
    async with SessionLocal() as session:
        c = Control(
            owner_id=owner_id,
            child_id=child_id,
            fecha=fecha,
            peso_kg=peso_kg,
            talla_cm=talla_cm,
            perimetro_cm=perimetro_cm,
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c


async def list_controls(child_id: int) -> Sequence[Control]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Control).where(Control.child_id == child_id).order_by(Control.fecha)
        )
        return result.scalars().all()


# ---------- Recomendaciones del pediatra ----------

async def add_advice(
    owner_id: int,
    child_id: int,
    content: str,
    source: str = "texto",
    photo_ref: Optional[str] = None,
) -> Advice:
    async with SessionLocal() as session:
        a = Advice(
            owner_id=owner_id,
            child_id=child_id,
            content=content,
            source=source,
            photo_ref=photo_ref,
        )
        session.add(a)
        await session.commit()
        await session.refresh(a)
        return a


async def list_advice(child_id: int, limit: Optional[int] = None) -> Sequence[Advice]:
    async with SessionLocal() as session:
        stmt = (
            select(Advice)
            .where(Advice.child_id == child_id)
            .order_by(Advice.created_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()
