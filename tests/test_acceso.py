"""Lista de acceso: quién puede hablarle al bot."""

from app import crud
from app.acceso import ids_permitidos, mensaje_rechazo, puede_usar

DUENA = 5000000001
EXTRANA = 5000000002
INVITADA = 5000000003


def test_ids_permitidos_parsea_lista():
    assert ids_permitidos("") == set()
    assert ids_permitidos(" 123, 456 ;789,abc,") == {123, 456, 789}


async def test_sin_lista_el_bot_es_abierto():
    assert await puede_usar(EXTRANA, "hola", set())


async def test_con_lista_solo_entran_los_permitidos():
    permitidos = {DUENA}
    assert await puede_usar(DUENA, "hola", permitidos)
    assert not await puede_usar(EXTRANA, "hola", permitidos)


async def test_enlace_de_invitacion_deja_pasar():
    assert await puede_usar(EXTRANA, "/start join_abc123", {DUENA})
    assert not await puede_usar(EXTRANA, "/start", {DUENA})


async def test_familiar_invitado_queda_permitido():
    hijo = await crud.add_child(DUENA, "Luna")
    token = await crud.crear_invitacion(hijo.family_id, DUENA)
    assert not await puede_usar(INVITADA, "hola", {DUENA})
    assert await crud.redimir_invitacion(token, INVITADA, "Abuela") == hijo.family_id
    assert await puede_usar(INVITADA, "hola", {DUENA})


async def test_revocado_pierde_acceso():
    hijo = await crud.add_child(DUENA, "Luna")
    token = await crud.crear_invitacion(hijo.family_id, DUENA)
    await crud.redimir_invitacion(token, INVITADA, "Tía")
    await crud.revocar_miembro(hijo.family_id, INVITADA)
    assert not await puede_usar(INVITADA, "hola", {DUENA})


def test_rechazo_muestra_el_id():
    assert "5000000002" in mensaje_rechazo(EXTRANA)
