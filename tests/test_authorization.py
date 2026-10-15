"""Fase C — autorización defensiva.

Prueba el núcleo `resolver_hijo` (que gatea mutaciones y callbacks) y la política
de roles. Sin mocks de Telegram: validamos la regla de seguridad directamente.
"""

from datetime import date

from app import crud, roles
from app.db import SessionLocal
from app.models import FamilyMember, Rol

A, B, C = 100, 200, 300


async def _add_member(family_id: int, chat_id: int, rol: Rol) -> None:
    async with SessionLocal() as s:
        s.add(FamilyMember(family_id=family_id, chat_id=chat_id, role=rol.value))
        await s.commit()


async def test_ajeno_no_resuelve_hijo():
    luna = await crud.add_child(A, "Luna")
    assert await crud.resolver_hijo(B, luna.id) is None  # B no es de la familia


async def test_miembro_editor_resuelve_hijo():
    luna = await crud.add_child(A, "Luna")
    await _add_member(luna.family_id, C, Rol.EDITOR)
    child = await crud.resolver_hijo(C, luna.id)
    assert child is not None and child.id == luna.id


async def test_editor_no_alcanza_rol_admin():
    luna = await crud.add_child(A, "Luna")  # A queda admin
    await _add_member(luna.family_id, C, Rol.EDITOR)
    assert await crud.resolver_hijo(C, luna.id, rol_min=Rol.ADMIN) is None
    assert await crud.resolver_hijo(A, luna.id, rol_min=Rol.ADMIN) is not None


async def test_ajeno_no_puede_borrar_hito_de_otra_familia():
    # Hito de la familia de A; B (ajeno) no puede resolver → no puede borrar.
    luna = await crud.add_child(A, "Luna")
    m = await crud.add_milestone(A, luna.id, "gateó", date(2024, 1, 1))
    assert await crud.resolver_hijo(B, m.child_id) is None
    # el hito sigue existiendo (no se borró)
    assert len(await crud.list_milestones(luna.id)) == 1


def test_politica_de_roles():
    assert roles.puede_editar("editor") and roles.puede_editar("admin")
    assert not roles.puede_gestionar_miembros("editor")
    assert roles.puede_gestionar_miembros("admin")
    assert not roles.puede_editar("desconocido")
