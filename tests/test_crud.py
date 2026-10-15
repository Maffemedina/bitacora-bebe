"""Tests de la capa de datos (app/crud.py) contra SQLite temporal. Sin red.

Cada test corre con tablas recién creadas (fixture autouse en conftest).
"""

from datetime import date, datetime

from app import crud

# chat_id mayor que int32 (2.147.483.647), como los IDs reales de Telegram.
BIG = 6000000001


# ---------- Perfil e hijos ----------

async def test_ensure_profile_crea_y_es_idempotente():
    p1 = await crud.ensure_profile(BIG)
    p2 = await crud.ensure_profile(BIG)
    assert p1.chat_id == BIG == p2.chat_id
    assert (await crud.get_profile(BIG)).chat_id == BIG


async def test_add_child_queda_activo():
    child = await crud.add_child(BIG, "Luna", date(2024, 3, 10))
    activo = await crud.get_active_child(BIG)
    assert activo is not None
    assert activo.id == child.id and activo.name == "Luna"
    assert activo.birthdate == date(2024, 3, 10)


async def test_list_children_devuelve_todos():
    await crud.add_child(BIG, "Luna")
    await crud.add_child(BIG, "Mateo")
    nombres = {c.name for c in await crud.list_children(BIG)}
    assert nombres == {"Luna", "Mateo"}


async def test_find_child_por_nombre_exacto_y_parcial():
    await crud.add_child(BIG, "Luna")
    await crud.add_child(BIG, "Mateo")
    assert (await crud.find_child_by_name(BIG, "luna")).name == "Luna"
    assert (await crud.find_child_by_name(BIG, "Mat")).name == "Mateo"
    assert await crud.find_child_by_name(BIG, "Zoe") is None


async def test_cambiar_hijo_activo():
    await crud.add_child(BIG, "Luna")
    mateo = await crud.add_child(BIG, "Mateo")  # Mateo queda activo
    luna = await crud.find_child_by_name(BIG, "Luna")
    await crud.set_active_child(BIG, luna.id)
    assert (await crud.get_active_child(BIG)).name == "Luna"
    assert mateo.name == "Mateo"


async def test_set_birthdate_y_memoria():
    child = await crud.add_child(BIG, "Luna")
    actualizado = await crud.set_child_birthdate(child.id, date(2023, 4, 15))
    assert actualizado.birthdate == date(2023, 4, 15)
    memoria = await crud.mark_child_memoria(child.id, date(2024, 1, 1))
    assert memoria.status == "memoria" and memoria.passed_on == date(2024, 1, 1)


# ---------- Hitos ----------

async def test_hito_crear_listar_actualizar_borrar():
    child = await crud.add_child(BIG, "Luna")
    m = await crud.add_milestone(BIG, child.id, "gateó", date(2024, 12, 20))
    assert [h.description for h in await crud.list_milestones(child.id)] == ["gateó"]

    await crud.update_milestone_date(m.id, date(2024, 12, 25))
    await crud.update_milestone_media(m.id, "vol:media/x.jpg")
    hitos = await crud.list_milestones(child.id)
    assert hitos[0].happened_on == date(2024, 12, 25)
    assert hitos[0].photo_ref == "vol:media/x.jpg"

    assert await crud.delete_milestone(m.id) is True
    assert list(await crud.list_milestones(child.id)) == []
    assert await crud.delete_milestone(m.id) is False  # ya no existe


async def test_hitos_ordenados_por_fecha():
    child = await crud.add_child(BIG, "Luna")
    await crud.add_milestone(BIG, child.id, "b", date(2024, 5, 1))
    await crud.add_milestone(BIG, child.id, "a", date(2024, 1, 1))
    fechas = [h.happened_on for h in await crud.list_milestones(child.id)]
    assert fechas == sorted(fechas)


# ---------- Controles de crecimiento ----------

async def test_control_crear_y_listar():
    child = await crud.add_child(BIG, "Luna")
    await crud.add_control(BIG, child.id, date(2026, 1, 3), 7.5, 68, 43)
    await crud.add_control(BIG, child.id, date(2026, 2, 3), 8.2, 70, 44)
    ctrls = await crud.list_controls(child.id)
    assert len(ctrls) == 2
    assert ctrls[0].peso_kg == 7.5 and ctrls[1].talla_cm == 70
    assert [c.fecha for c in ctrls] == sorted(c.fecha for c in ctrls)
