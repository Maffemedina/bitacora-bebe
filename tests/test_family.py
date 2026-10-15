"""Fase B — lecturas por familia, aislamiento, hijo activo validado, reparación.

TDD selectivo: cubre aislamiento, multi-familia, acceso revocado y reparación.
"""

from datetime import date

from sqlalchemy import select

from app import crud
from app.db import SessionLocal
from app.models import Child, FamilyMember, Rol

A, B, C = 100, 200, 300  # chat_ids


async def _add_member(family_id: int, chat_id: int, rol: Rol) -> None:
    async with SessionLocal() as s:
        s.add(FamilyMember(family_id=family_id, chat_id=chat_id, role=rol.value))
        await s.commit()


async def _remove_member(family_id: int, chat_id: int) -> None:
    async with SessionLocal() as s:
        m = (
            await s.execute(
                select(FamilyMember).where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.chat_id == chat_id,
                )
            )
        ).scalars().first()
        if m:
            await s.delete(m)
            await s.commit()


async def _insert_orphan_child(owner_id: int, name: str) -> None:
    async with SessionLocal() as s:
        s.add(Child(owner_id=owner_id, family_id=None, name=name, status="activo"))
        await s.commit()


async def test_aislamiento_entre_familias():
    await crud.add_child(A, "Luna")
    await crud.add_child(B, "Mateo")

    assert {c.name for c in await crud.list_children(A)} == {"Luna"}
    assert {c.name for c in await crud.list_children(B)} == {"Mateo"}

    # A no puede activar a Mateo (no es miembro de su familia)
    mateo = (await crud.list_children(B))[0]
    await crud.ensure_profile(A)
    await crud.set_active_child(A, mateo.id)
    assert await crud.get_active_child(A) is None


async def test_dos_miembros_misma_familia_ven_el_mismo_hijo():
    luna = await crud.add_child(A, "Luna")
    await _add_member(luna.family_id, C, Rol.EDITOR)

    assert {c.name for c in await crud.list_children(C)} == {"Luna"}

    # C registra un hito → A lo ve (mismo child_id, misma familia)
    await crud.add_milestone(C, luna.id, "gateó", date(2024, 1, 1))
    assert [h.description for h in await crud.list_milestones(luna.id)] == ["gateó"]


async def test_usuario_en_dos_familias_ve_hijos_de_ambas():
    luna = await crud.add_child(A, "Luna")   # A admin de F1
    mateo = await crud.add_child(B, "Mateo")     # B admin de F2
    await _add_member(mateo.family_id, A, Rol.EDITOR)  # A también editor de F2

    assert {c.name for c in await crud.list_children(A)} == {"Luna", "Mateo"}


async def test_revocado_pierde_acceso_al_hijo_activo():
    luna = await crud.add_child(A, "Luna")
    await _add_member(luna.family_id, C, Rol.EDITOR)
    await crud.ensure_profile(C)
    await crud.set_active_child(C, luna.id)
    assert (await crud.get_active_child(C)).name == "Luna"

    await _remove_member(luna.family_id, C)  # revocación
    assert await crud.get_active_child(C) is None


async def test_repara_family_id_de_hijo_huerfano():
    await _insert_orphan_child(A, "Huerfano")
    hijos = await crud.list_children(A)  # dispara la reparación
    assert {c.name for c in hijos} == {"Huerfano"}
    assert all(c.family_id is not None for c in hijos)
