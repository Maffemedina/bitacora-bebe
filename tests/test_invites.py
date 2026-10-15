"""Fase D — invitaciones (TDD estricto): crear, redimir atómica, un solo uso,
vencimiento. Sin red ni mocks de Telegram.
"""

from app import crud
from app.models import Rol

A, C, D = 100, 300, 400


async def _familia_de_a() -> int:
    luna = await crud.add_child(A, "Luna")  # A queda admin de su familia
    return luna.family_id


async def test_crear_y_redimir_agrega_miembro_editor():
    fam = await _familia_de_a()
    token = await crud.crear_invitacion(fam, created_by=A)

    assert await crud.redimir_invitacion(token, C, "Carla") == fam
    assert await crud.member_role(C, fam) == Rol.EDITOR.value
    # C ahora ve al hijo de la familia
    assert {c.name for c in await crud.list_children(C)} == {"Luna"}


async def test_un_solo_uso_doble_redencion():
    fam = await _familia_de_a()
    token = await crud.crear_invitacion(fam, created_by=A)

    assert await crud.redimir_invitacion(token, C) == fam      # primera vale
    assert await crud.redimir_invitacion(token, D) is None     # segunda NO
    # D no quedó como miembro
    assert await crud.member_role(D, fam) is None


async def test_invitacion_vencida_no_se_redime():
    fam = await _familia_de_a()
    token = await crud.crear_invitacion(fam, created_by=A, horas=-1)  # ya vencida
    assert await crud.redimir_invitacion(token, C) is None
    assert await crud.member_role(C, fam) is None


async def test_token_invalido_no_se_redime():
    await _familia_de_a()
    assert await crud.redimir_invitacion("token-que-no-existe", C) is None
