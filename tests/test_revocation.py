"""Fase E — /mi_familia + revocación. El revocado pierde acceso de inmediato."""

from app import crud
from app.db import SessionLocal
from app.models import FamilyMember, Rol

A, C, D = 100, 300, 400


async def _add_member(family_id: int, chat_id: int, rol: Rol) -> None:
    async with SessionLocal() as s:
        s.add(FamilyMember(family_id=family_id, chat_id=chat_id, role=rol.value))
        await s.commit()


async def test_revocar_miembro_pierde_acceso_inmediato():
    luna = await crud.add_child(A, "Luna")  # A admin
    fam = luna.family_id
    await _add_member(fam, C, Rol.EDITOR)
    await crud.ensure_profile(C)
    await crud.set_active_child(C, luna.id)
    assert (await crud.get_active_child(C)).name == "Luna"  # antes: ve

    assert await crud.revocar_miembro(fam, C) is True

    assert await crud.member_role(C, fam) is None
    assert await crud.get_active_child(C) is None            # después: sin acceso
    assert list(await crud.list_children(C)) == []


async def test_revocar_no_miembro_devuelve_false():
    luna = await crud.add_child(A, "Luna")
    assert await crud.revocar_miembro(luna.family_id, D) is False


async def test_list_members_incluye_admin_y_editor():
    luna = await crud.add_child(A, "Luna")
    await _add_member(luna.family_id, C, Rol.EDITOR)
    miembros = {(m.chat_id, m.role) for m in await crud.list_members(luna.family_id)}
    assert (A, Rol.ADMIN.value) in miembros
    assert (C, Rol.EDITOR.value) in miembros
