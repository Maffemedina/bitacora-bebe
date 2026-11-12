"""Datos de prueba para la demo de la charla: una bebé ficticia, Emilia.

Con /demo, una cuenta de Telegram que esté en DEMO_CHAT_IDS borra y vuelve a crear
a Emilia con sus hitos, controles, indicaciones y una cita. Las fechas se calculan
desde hoy, así la demo se ve igual cada vez que se reinicia: tiene ~10 meses, hay
hitos de esta semana para /semana y la cita queda en unos días.

Seguridad: solo toca la familia marcada como demo. Si la cuenta pertenece a otra
familia con bebés reales, no hace nada: los datos reales nunca se mezclan ni se borran.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import (
    Advice,
    Appointment,
    Child,
    Control,
    Family,
    FamilyMember,
    Milestone,
    Rol,
    UserProfile,
)
from app.storage import delete_media
from app.utils import hoy

FAMILIA_DEMO = "DEMO charla"
NOMBRE = "Emilia"
DIAS_DE_VIDA = 300  # unos 10 meses

# (días desde el nacimiento, hito). «Caminó» no está: se registra en vivo.
HITOS = [
    (42, "Sonrió por primera vez"),
    (110, "Se rió a carcajadas con los abuelos"),
    (190, "Se sentó sola sin apoyo"),
    (215, "Le salió el primer diente"),
    (250, "Gateó por toda la sala"),
]
# (días antes de hoy, hito): para que /semana tenga algo que contar.
HITOS_SEMANA = [
    (5, "Aplaude cuando le cantan"),
    (2, "Dijo «mamá» por primera vez"),
]
# (días desde el nacimiento, peso kg, talla cm, perímetro cefálico cm): valores
# típicos de una niña sana, inventados para la demo.
CONTROLES = [
    (0, 3.2, 49.0, 34.0),
    (30, 4.2, 53.5, 36.5),
    (61, 5.1, 57.0, 38.3),
    (122, 6.4, 62.0, 40.6),
    (183, 7.3, 65.7, 42.2),
    (274, 8.2, 70.1, 43.8),
]
INDICACIONES = [
    "Vitamina D: 1 gota (400 UI) al día hasta el primer año.",
    "Ofrecer agua en vaso entre comidas y no dar miel antes del año.",
]
CITA = ("Control pediátrico de los 10 meses", 3, time(9, 0), "Consultorio de la pediatra")


@dataclass
class Resultado:
    ok: bool
    mensaje: str
    child_id: Optional[int] = None


async def _familias_de(chat_id: int) -> list[Family]:
    async with SessionLocal() as session:
        res = await session.execute(
            select(Family)
            .join(FamilyMember, FamilyMember.family_id == Family.id)
            .where(FamilyMember.chat_id == chat_id)
        )
        return list(res.scalars().all())


async def _hay_bebes(family_ids: list[int]) -> bool:
    if not family_ids:
        return False
    async with SessionLocal() as session:
        res = await session.execute(select(Child.id).where(Child.family_id.in_(family_ids)))
        return res.first() is not None


async def reiniciar_demo(chat_id: int, hoy_: Optional[date] = None) -> Resultado:
    """Deja la cuenta con Emilia recién creada. Se puede repetir las veces que haga falta."""
    hoy_ = hoy_ or hoy()
    familias = await _familias_de(chat_id)
    ajenas = [f.id for f in familias if f.name != FAMILIA_DEMO]
    if await _hay_bebes(ajenas):
        return Resultado(
            False,
            "🚫 Esta cuenta ya tiene bebés reales, así que no cargo la demo aquí: no quiero "
            "mezclar ni borrar sus datos. Usa una cuenta de Telegram solo para la demo.",
        )

    demo = next((f for f in familias if f.name == FAMILIA_DEMO), None)
    async with SessionLocal() as session:
        if demo is None:
            demo = Family(name=FAMILIA_DEMO)
            session.add(demo)
            await session.commit()
            await session.refresh(demo)
            session.add(FamilyMember(family_id=demo.id, chat_id=chat_id, role=Rol.ADMIN.value))
            await session.commit()

        # Borra lo que haya quedado de ensayos anteriores (solo de la familia demo).
        ids = list(
            (await session.execute(select(Child.id).where(Child.family_id == demo.id)))
            .scalars()
            .all()
        )
        if ids:
            refs = (
                await session.execute(
                    select(Milestone.photo_ref).where(
                        Milestone.child_id.in_(ids), Milestone.photo_ref.is_not(None)
                    )
                )
            ).scalars().all()
            for ref in refs:
                delete_media(ref)
            for modelo in (Milestone, Control, Appointment, Advice):
                await session.execute(delete(modelo).where(modelo.child_id.in_(ids)))
            await session.execute(delete(Child).where(Child.id.in_(ids)))
            await session.commit()

        nacimiento = hoy_ - timedelta(days=DIAS_DE_VIDA)
        bebe = Child(owner_id=chat_id, family_id=demo.id, name=NOMBRE, birthdate=nacimiento)
        session.add(bebe)
        await session.commit()
        await session.refresh(bebe)

        for dias, desc in HITOS:
            session.add(
                Milestone(owner_id=chat_id, child_id=bebe.id, description=desc,
                          happened_on=nacimiento + timedelta(days=dias))
            )
        for dias, desc in HITOS_SEMANA:
            session.add(
                Milestone(owner_id=chat_id, child_id=bebe.id, description=desc,
                          happened_on=hoy_ - timedelta(days=dias))
            )
        for dias, peso, talla, pc in CONTROLES:
            session.add(
                Control(owner_id=chat_id, child_id=bebe.id,
                        fecha=nacimiento + timedelta(days=dias),
                        peso_kg=peso, talla_cm=talla, perimetro_cm=pc)
            )
        for texto in INDICACIONES:
            session.add(Advice(owner_id=chat_id, child_id=bebe.id, content=texto, source="texto"))
        titulo, en_dias, hora, lugar = CITA
        session.add(
            Appointment(owner_id=chat_id, child_id=bebe.id, title=titulo,
                        scheduled_at=datetime.combine(hoy_ + timedelta(days=en_dias), hora),
                        location=lugar)
        )

        perfil = (
            await session.execute(select(UserProfile).where(UserProfile.chat_id == chat_id))
        ).scalars().first()
        if perfil is None:
            perfil = UserProfile(chat_id=chat_id)
        perfil.active_child_id = bebe.id
        session.add(perfil)
        await session.commit()

    cita = datetime.combine(hoy_ + timedelta(days=en_dias), hora)
    return Resultado(
        True,
        f"🎬 Demo lista: <b>{NOMBRE}</b> nació el {nacimiento:%d/%m/%Y} (unos 10 meses).\n"
        f"• {len(HITOS) + len(HITOS_SEMANA)} hitos, {len(CONTROLES)} controles y "
        f"{len(INDICACIONES)} indicaciones del pediatra\n"
        f"• Cita: {titulo}, {cita:%d/%m/%Y} a las {cita:%H:%M}\n\n"
        "Prueba /recap, /semana o <i>¿cuándo gateó Emilia?</i>. "
        "Repite /demo para dejarla como nueva.",
        bebe.id,
    )
