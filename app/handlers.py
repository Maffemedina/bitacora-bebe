"""Manejadores de Telegram: reciben el mensaje, piden al agente que lo entienda
y ejecutan las acciones contra la base de datos.

- Onboarding con "hola" (no solo /start).
- Varios hijos + cambiar entre ellos.
- Duelo: condolencia con cuidado + recap-homenaje.
- Recomendaciones del pediatra por foto o audio, que el bot tiene en cuenta.
"""

import unicodedata
from datetime import date, datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app import agent, crud, reminders, roles
from app.config import settings
from app.states import ChildSetup, ControlMedidas
from app.storage import media_fullpath, save_media, upload_photo
from app.utils import ahora, edad_texto, hoy

router = Router()


# ---------- Helpers ----------

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        return None


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _elegir_registro(registros, referencia, get_text):
    """Decide CUÁL registro corregir: por 'el último' o por coincidencia de texto."""
    if not registros:
        return None
    ref = _sin_acentos((referencia or "").lower())
    if not ref or any(w in ref for w in ("ultim", "reciente", "acab", "ese", "esa")):
        return max(registros, key=lambda r: r.created_at)  # el más reciente
    palabras = [w for w in ref.split() if len(w) > 3]
    coincidencias = [
        r for r in registros
        if any(w in _sin_acentos(get_text(r).lower()) for w in palabras)
    ]
    if coincidencias:
        return max(coincidencias, key=lambda r: r.created_at)
    return None


async def _aviso_recordatorio(cita) -> str:
    """Decide si la cita tendrá recordatorio y devuelve la línea para contarlo.

    Si la cita ya está dentro de la ventana de aviso (ej. es en 3 horas), no tiene
    sentido "recordarla" 5 minutos después de agendarla: se marca como avisada.
    """
    horas = settings.reminder_hours
    if horas <= 0:
        return ""
    if reminders.queda_dentro_de_la_ventana(cita.scheduled_at, ahora(), horas):
        await crud.marcar_recordada(cita.id)
        return ""
    return f"\n⏰ Les aviso a todos en la familia {horas} h antes."


def _fmt_medida(v, unidad: str) -> str:
    return f"{v:g} {unidad}" if v is not None else "—"


def _fmt_control_linea(c) -> str:
    return (
        f"• {c.fecha:%d/%m/%Y}: peso {_fmt_medida(c.peso_kg, 'kg')}, "
        f"talla {_fmt_medida(c.talla_cm, 'cm')}, PC {_fmt_medida(c.perimetro_cm, 'cm')}"
    )


def _fmt_control_guardado(name: str, fecha, peso, talla, perimetro) -> str:
    return (
        f"📏 Control de <b>{name}</b> guardado ({fecha:%d/%m/%Y}):\n"
        f"peso {_fmt_medida(peso, 'kg')}, talla {_fmt_medida(talla, 'cm')}, "
        f"PC {_fmt_medida(perimetro, 'cm')}"
    )


async def _download_photo_bytes(message: Message) -> bytes:
    tg_file = await message.bot.get_file(message.photo[-1].file_id)
    buffer = await message.bot.download_file(tg_file.file_path)
    return buffer.read()


async def _save_photo_ref(message: Message) -> str:
    file_id = message.photo[-1].file_id
    if settings.media_dir:  # volumen persistente
        return save_media(await _download_photo_bytes(message), "jpg")
    if settings.s3_bucket:
        buffer = await message.bot.download_file(
            (await message.bot.get_file(file_id)).file_path
        )
        return f"s3:{upload_photo(buffer.read())}"
    return f"tg:{file_id}"


async def _save_video_ref(message: Message) -> str:
    if settings.media_dir:  # volumen persistente (solo archivos ≤ 20 MB)
        try:
            tg_file = await message.bot.get_file(message.video.file_id)
            buffer = await message.bot.download_file(tg_file.file_path)
            return save_media(buffer.read(), "mp4")
        except Exception:
            pass  # muy grande o error → referencia de Telegram
    return f"tgv:{message.video.file_id}"


async def _begin_setup(message: Message, state: FSMContext, primero: bool = True) -> None:
    """Arranca el registro de un hijo (el primero o uno nuevo)."""
    await crud.ensure_profile(message.from_user.id)
    await state.set_state(ChildSetup.name)
    if primero:
        await message.answer(
            "¡Hola! Voy a ser la bitácora de tu bebé 🍼\n\nPara empezar, <b>¿cómo se llama?</b>"
        )
    else:
        await message.answer("¡Qué lindo! 🍼 <b>¿Cómo se llama?</b>")


async def _enviar_recap(target: Message, child, memoria: bool = False) -> None:
    hitos = await crud.list_milestones(child.id)
    if memoria:
        encabezado = f"💛 <b>En memoria de {child.name}</b>"
    else:
        encabezado = f"📖 <b>Recap de {child.name}</b>"
    if not hitos:
        await target.answer(f"{encabezado}\n\nAún no hay momentos guardados.")
        return
    await target.answer(f"{encabezado} — {len(hitos)} momento(s):")
    for h in hitos:
        linea = f"• {h.happened_on:%d/%m/%Y} — {h.description}"
        ref = h.photo_ref or ""
        try:
            if ref.startswith("vol:"):
                archivo = FSInputFile(media_fullpath(ref))
                if ref.lower().endswith((".mp4", ".mov", ".webm")):
                    await target.answer_video(archivo, caption=linea)
                else:
                    await target.answer_photo(archivo, caption=linea)
            elif ref.startswith("tgv:"):
                await target.answer_video(ref[4:], caption=linea)
            elif ref.startswith("tg:"):
                await target.answer_photo(ref[3:], caption=linea)
            else:
                await target.answer(linea)
        except Exception:
            await target.answer(linea)  # si el archivo no está, al menos el texto


async def _enviar_informe(target: Message, child) -> None:
    from app.informe import generar_informe_pdf

    pdf = generar_informe_pdf(
        child,
        edad_texto(child.birthdate) if child.birthdate else None,
        await crud.list_controls(child.id),
        await crud.list_advice(child.id),
        await crud.list_milestones(child.id),
        await crud.list_upcoming_appointments(child.id),
        hoy(),
    )
    nombre = "".join(c for c in child.name if c.isalnum()) or "bebe"
    await target.answer_document(
        BufferedInputFile(pdf, filename=f"informe-{nombre}-{hoy():%Y-%m-%d}.pdf"),
        caption=f"🩺 Informe de <b>{child.name}</b> para llevar a la consulta.",
    )


async def _enviar_resumen_semanal(target: Message, child) -> None:
    from app.summary import componer_resumen_semanal

    hitos = await crud.list_milestones(child.id)
    controles = await crud.list_controls(child.id)
    citas = await crud.list_appointments(child.id)
    await target.answer(
        componer_resumen_semanal(child.name, hitos, controles, citas, hoy())
    )


# ---------- Onboarding ----------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext, command: CommandObject) -> None:
    args = command.args or ""
    if args.startswith("join_"):
        await _procesar_invitacion(message, state, args[len("join_"):])
        return
    child = await crud.get_active_child(message.from_user.id)
    if child:
        await state.clear()
        edad = f" ({edad_texto(child.birthdate)})" if child.birthdate else ""
        await message.answer(
            f"¡Hola de nuevo! Soy la <b>Bitácora de {child.name}</b>{edad} 🍼\n\n"
            "Háblame natural:\n"
            "• <i>«gateó por primera vez hoy»</i>\n"
            "• <i>«tiene cita con el pediatra el 27 de enero a las 3pm»</i>\n"
            "• <i>«¿cuándo tiene citas?»</i> · <i>«muéstrame el recap»</i>\n"
            "• Mándame una <b>foto</b> o una <b>nota de voz</b> 🎙️"
        )
    else:
        await _begin_setup(message, state, primero=True)


async def _procesar_invitacion(message: Message, state: FSMContext, token: str) -> None:
    family_id = await crud.redimir_invitacion(
        token, message.from_user.id, message.from_user.first_name
    )
    if family_id is None:
        await message.answer("Este enlace no es válido, ya se usó o venció 🙈")
        return
    await crud.ensure_profile(message.from_user.id)
    await state.clear()
    hijos = await crud.family_children(family_id)
    if hijos:
        await crud.set_active_child(message.from_user.id, hijos[0].id)
        nombres = ", ".join(h.name for h in hijos)
        await message.answer(
            f"💛 ¡Te uniste a la bitácora de <b>{nombres}</b>! Ya puedes ver y "
            "registrar momentos. Un <b>admin</b> puede revocar tu acceso cuando quiera."
        )
    else:
        await message.answer(
            "💛 ¡Te uniste a la familia! Aún no hay bebés registrados. "
            "Un admin puede revocar tu acceso cuando quiera."
        )


@router.message(ChildSetup.name)
async def ob_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Escríbeme el nombre de tu bebé 🙂")
        return
    await crud.add_child(message.from_user.id, name)
    await state.set_state(ChildSetup.birthdate)
    await message.answer(
        f"¡Encantada, {name}! 🎉\n\nY <b>¿cuándo nació?</b> "
        "Puedes escribirlo como quieras, ej. <i>«15 de abril de 2023»</i>."
    )


@router.message(ChildSetup.birthdate)
async def ob_birthdate(message: Message, state: FSMContext) -> None:
    fecha = _parse_date(await agent.fecha_en_texto(message.text or "", hoy().isoformat()))
    child = await crud.get_active_child(message.from_user.id)
    if not fecha:
        await message.answer(
            "No entendí la fecha 🙈. Prueba: <i>«15 de abril de 2023»</i> o <code>2023-04-15</code>."
        )
        return
    child = await crud.set_child_birthdate(child.id, fecha)
    await state.clear()
    await message.answer(
        f"¡Listo! <b>{child.name}</b> tiene <b>{edad_texto(fecha)}</b> 🎂\n\n"
        "Ahora háblame natural: <i>«sonrió hoy»</i>, <i>«tiene cita el 27 de enero 3pm»</i>, "
        "o mándame una foto/nota de voz."
    )


@router.message(ControlMedidas.datos)
async def recibir_medidas(message: Message, state: FSMContext) -> None:
    medidas = await agent.parsear_medidas(message.text or "")
    data = await state.get_data()
    await state.clear()
    child_id = data.get("control_child_id")
    if child_id is None:
        return
    fecha = date.fromisoformat(data.get("control_fecha"))
    await crud.add_control(
        message.from_user.id, child_id, fecha, medidas.peso, medidas.talla, medidas.perimetro
    )
    child = await crud.get_child(child_id)
    nombre = child.name if child else "el bebé"
    await message.answer(
        _fmt_control_guardado(nombre, fecha, medidas.peso, medidas.talla, medidas.perimetro)
        + "\n\nPídeme <i>«¿cómo va el crecimiento?»</i> cuando quieras verlo. 📈"
    )


# ---------- Duelo ----------

CONDOLENCIA = (
    "Lamento profundamente lo de <b>{nombre}</b>. 💛\n\n"
    "No hay palabras que llenen un vacío así, pero quiero que sepas que cada uno de "
    "sus momentos queda aquí, guardado con cariño. Tómate todo el tiempo que necesites.\n\n"
    "Si algún día quieres recordarle, puedo mostrarte sus hitos como un pequeño homenaje."
)


def _kb_homenaje(child_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💛 Ver sus recuerdos", callback_data=f"memrecap:{child_id}"
                ),
                InlineKeyboardButton(text="Ahora no", callback_data="memrecap:no"),
            ]
        ]
    )


@router.callback_query(F.data.startswith("memrecap:"))
async def cb_memrecap(cb: CallbackQuery) -> None:
    await cb.answer()
    val = cb.data.split(":", 1)[1]
    if val == "no":
        await cb.message.answer("Aquí estaré cuando quieras recordarle 💛")
        return
    child = await crud.resolver_hijo(cb.from_user.id, int(val))
    if child is None:
        await cb.message.answer("No tienes acceso a este bebé 🚫")
        return
    await _enviar_recap(cb.message, child, memoria=True)


def _kb_borrar_hito(milestone_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑️ Sí, borrar", callback_data=f"delhito:{milestone_id}"
                ),
                InlineKeyboardButton(text="Cancelar", callback_data="delhito:no"),
            ]
        ]
    )


@router.callback_query(F.data.startswith("delhito:"))
async def cb_delhito(cb: CallbackQuery) -> None:
    await cb.answer()
    val = cb.data.split(":", 1)[1]
    if val == "no":
        await cb.message.answer("Listo, no borré nada 🙂")
        return
    m = await crud.get_milestone(int(val))
    if m is None or await crud.resolver_hijo(cb.from_user.id, m.child_id) is None:
        await cb.message.answer("No puedes borrar este hito 🚫")
        return
    ok = await crud.delete_milestone(m.id)
    await cb.message.answer("🗑️ Hito borrado." if ok else "Ese hito ya no existe.")


@router.callback_query(F.data.startswith("revoke:"))
async def cb_revocar(cb: CallbackQuery) -> None:
    await cb.answer()
    _, fam, target = cb.data.split(":")
    family_id, target_chat = int(fam), int(target)
    rol = await crud.member_role(cb.from_user.id, family_id)
    if not roles.puede_gestionar_miembros(rol or ""):  # re-autoriza en el callback
        await cb.message.answer("Solo un admin puede revocar accesos 🔒")
        return
    ok = await crud.revocar_miembro(family_id, target_chat)
    await cb.message.answer("🚫 Acceso revocado." if ok else "Esa persona ya no estaba.")


@router.callback_query(F.data == "skipmedia")
async def cb_skipmedia(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.update_data(pending_media_hito=None)
    await cb.message.answer("Listo, lo dejé guardado sin foto 🙂")


# ---------- Procesamiento con el cerebro ----------

async def _procesar_texto(
    message: Message, child, texto: str, state: FSMContext, source: str = "texto"
) -> None:
    """Entiende el mensaje (puede traer VARIAS acciones) y ejecuta cada una,
    enrutando por el nombre del hijo mencionado en cada acción."""
    # Si un hito está esperando foto/video y escriben "omitir", se conserva sin media.
    data = await state.get_data()
    if data.get("pending_media_hito") is not None and texto.strip().lower() in (
        "omitir", "ahora no", "no", "no gracias",
    ):
        await state.update_data(pending_media_hito=None)
        await message.answer("Listo, lo dejé guardado sin foto 🙂")
        return

    acciones = await agent.planear(texto, hoy().isoformat(), child.name)
    chat_id = message.from_user.id
    activo = child
    hitos_creados = []
    for ext in acciones:
        if ext.intent == "_error":
            await message.answer(
                "⏳ Estoy saturada un momento (límite del plan gratis de Gemini). "
                "Reinténtalo en unos segundos 🙂"
            )
            return
        # Multi-hijo: si menciona el nombre de un hijo registrado, la acción va a
        # ESE hijo (y queda como activo), sin tener que "cambiar" manualmente.
        target = activo
        if ext.nombre_hijo:
            encontrado = await crud.find_child_by_name(chat_id, ext.nombre_hijo)
            if encontrado:
                target = encontrado
                if encontrado.id != activo.id:
                    await crud.set_active_child(chat_id, encontrado.id)
                    activo = encontrado
        creado = await _ejecutar_accion(message, ext, target, state, source, texto)
        if creado is not None:
            hitos_creados.append(creado)

    # Solo para UN hito registrado por texto/voz: sugerir foto/video (📸).
    if len(hitos_creados) == 1:
        await _sugerir_media(message, state, hitos_creados[0])


async def _ejecutar_accion(
    message: Message, ext, child, state: FSMContext, source: str = "texto", texto: str = ""
) -> Optional[int]:
    """Ejecuta una acción. Devuelve el id del hito creado (para sugerir media), o None."""
    chat_id = message.from_user.id

    if ext.intent == "fallecimiento":
        objetivo = child
        if ext.nombre_hijo:
            encontrado = await crud.find_child_by_name(chat_id, ext.nombre_hijo)
            if encontrado:
                objetivo = encontrado
        fecha = _parse_date(ext.fecha) or hoy()
        await crud.mark_child_memoria(objetivo.id, fecha)
        await message.answer(
            CONDOLENCIA.format(nombre=objetivo.name), reply_markup=_kb_homenaje(objetivo.id)
        )

    elif ext.intent == "guardar_hito":
        fecha = _parse_date(ext.fecha) or hoy()
        desc = ext.descripcion or texto
        m = await crud.add_milestone(chat_id, child.id, desc, fecha)
        await message.answer(f"📌 Hito guardado ({fecha:%d/%m/%Y}):\n<i>{desc}</i>")
        return m.id

    elif ext.intent == "listar_hitos":
        await _enviar_recap(message, child)

    elif ext.intent == "agendar_cita":
        dt = _parse_dt(ext.fecha_hora_cita)
        if not dt:
            await message.answer("¿Para qué fecha y hora es la cita? No la capté bien 🙈")
            return
        titulo = ext.titulo_cita or "Cita"
        appt = await crud.add_appointment(chat_id, child.id, titulo, dt, ext.lugar_cita)
        lugar = f"\n📍 {appt.location}" if appt.location else ""
        aviso = await _aviso_recordatorio(appt)
        await message.answer(
            f"📅 Cita agendada: <b>{titulo}</b>\n🗓 {dt:%d/%m/%Y} a las {dt:%H:%M}{lugar}{aviso}"
        )

    elif ext.intent == "listar_citas":
        citas = await crud.list_upcoming_appointments(child.id)
        if not citas:
            await message.answer(f"{child.name} no tiene citas próximas 🗓")
            return
        lineas = [
            f"• {c.scheduled_at:%d/%m/%Y %H:%M} — {c.title}"
            + (f" ({c.location})" if c.location else "")
            for c in citas
        ]
        await message.answer(
            f"📅 <b>Próximas citas de {child.name}:</b>\n" + "\n".join(lineas)
        )

    elif ext.intent == "guardar_recomendacion":
        contenido = ext.recomendacion or texto
        await crud.add_advice(chat_id, child.id, contenido, source=source)
        await message.answer(
            f"🩺 Anotado. Tendré en cuenta esta indicación para {child.name}:\n<i>{contenido}</i>"
        )

    elif ext.intent == "listar_recomendaciones":
        consejos = await crud.list_advice(child.id)
        if not consejos:
            await message.answer(f"Aún no tengo indicaciones del pediatra para {child.name}.")
            return
        lineas = [f"• {a.content}" for a in consejos]
        await message.answer(
            f"🩺 <b>Indicaciones del pediatra para {child.name}:</b>\n" + "\n".join(lineas)
        )

    elif ext.intent == "agregar_hijo":
        if ext.nombre_hijo:
            fnac = _parse_date(ext.fecha)
            if not fnac and texto:  # respaldo: buscar la fecha en el mensaje original
                fnac = _parse_date(await agent.fecha_en_texto(texto, hoy().isoformat()))
            nuevo = await crud.add_child(chat_id, ext.nombre_hijo, fnac)
            if fnac:
                await message.answer(
                    f"¡Registré a <b>{nuevo.name}</b>! 🎉 Nació el {fnac:%d/%m/%Y} "
                    f"— tiene <b>{edad_texto(fnac)}</b> 🎂\nYa puedes contarme sus hitos."
                )
            else:
                await message.answer(
                    f"¡Registré a <b>{nuevo.name}</b> y ahora es el bebé activo! 🎉\n"
                    f"Dime cuándo nació: <i>«{nuevo.name} nació el 3 de marzo de 2025»</i>"
                )
        else:
            await _begin_setup(message, state, primero=False)

    elif ext.intent == "cambiar_hijo":
        if ext.nombre_hijo:
            encontrado = await crud.find_child_by_name(chat_id, ext.nombre_hijo)
            if encontrado:
                await crud.set_active_child(chat_id, encontrado.id)
                await message.answer(
                    f"Listo, ahora estás en la <b>Bitácora de {encontrado.name}</b> 🍼"
                )
                return
        hijos = await crud.list_children(chat_id)
        nombres = ", ".join(h.name for h in hijos)
        await message.answer(f"¿A cuál quieres cambiar? Tienes: <b>{nombres}</b>")

    elif ext.intent == "corregir_nacimiento":
        fecha = _parse_date(ext.fecha)
        if not fecha:
            await message.answer("¿Cuál es la fecha de nacimiento correcta? 🙂")
            return
        actualizado = await crud.set_child_birthdate(child.id, fecha)
        await message.answer(
            f"¡Corregido! ✅ <b>{actualizado.name}</b> nació el {fecha:%d/%m/%Y} "
            f"— ahora tiene <b>{edad_texto(fecha)}</b> 🎂"
        )

    elif ext.intent == "corregir_hito":
        nueva = _parse_date(ext.fecha)
        if not nueva:
            await message.answer("¿Cuál es la fecha correcta del hito? 🙂")
            return
        hitos = await crud.list_milestones(child.id)
        h = _elegir_registro(hitos, ext.referencia, lambda r: r.description)
        if not h:
            await message.answer(
                "No encontré ese hito 🙈. Dime cuál (ej. «el hito de que gateó») o «el último»."
            )
            return
        antes = h.happened_on
        await crud.update_milestone_date(h.id, nueva)
        await message.answer(
            f"✏️ Corregido: <i>{h.description}</i>\n"
            f"{antes:%d/%m/%Y} → <b>{nueva:%d/%m/%Y}</b> ✅"
        )

    elif ext.intent == "corregir_cita":
        nueva_dt = _parse_dt(ext.fecha_hora_cita)
        if not nueva_dt:
            await message.answer("¿Cuál es la fecha y hora correcta de la cita? 🙂")
            return
        citas = await crud.list_appointments(child.id)
        c = _elegir_registro(citas, ext.referencia, lambda r: r.title)
        if not c:
            await message.answer(
                "No encontré esa cita 🙈. Dime cuál (ej. «la cita del pediatra») o «la última»."
            )
            return
        antes = c.scheduled_at
        c = await crud.update_appointment_datetime(c.id, nueva_dt)
        aviso = await _aviso_recordatorio(c)
        await message.answer(
            f"✏️ Corregido: <b>{c.title}</b>\n"
            f"{antes:%d/%m/%Y %H:%M} → <b>{nueva_dt:%d/%m/%Y %H:%M}</b> ✅{aviso}"
        )

    elif ext.intent == "borrar_hito":
        hitos = await crud.list_milestones(child.id)
        h = _elegir_registro(hitos, ext.referencia, lambda r: r.description)
        if not h:
            await message.answer(
                "No encontré ese hito 🙈. Dime cuál (ej. «el hito de que gateó») o «el último»."
            )
            return
        await message.answer(
            f"¿Borro este hito de <b>{child.name}</b>?\n"
            f"• {h.happened_on:%d/%m/%Y} — <i>{h.description}</i>",
            reply_markup=_kb_borrar_hito(h.id),
        )

    elif ext.intent == "registrar_control":
        fecha = _parse_date(ext.fecha) or hoy()
        if ext.peso or ext.talla or ext.perimetro:
            await crud.add_control(
                chat_id, child.id, fecha, ext.peso, ext.talla, ext.perimetro
            )
            await message.answer(
                _fmt_control_guardado(child.name, fecha, ext.peso, ext.talla, ext.perimetro)
            )
        else:
            await state.set_state(ControlMedidas.datos)
            await state.update_data(control_child_id=child.id, control_fecha=fecha.isoformat())
            await message.answer(
                f"📏 Anoté el control de <b>{child.name}</b> del {fecha:%d/%m/%Y}.\n"
                "¿Cuánto <b>pesó</b>, cuánto <b>midió</b> y su <b>perímetro cefálico</b>? "
                "(ej: <i>8.2 kg, 70 cm, 44 cm</i>)"
            )

    elif ext.intent == "ver_crecimiento":
        controles = await crud.list_controls(child.id)
        if not controles:
            await message.answer(
                f"Aún no tengo controles de {child.name}. Dime "
                f"<i>«{child.name} fue al pediatra hoy»</i> y anotamos sus medidas 📏"
            )
            return
        tabla = f"📈 <b>Crecimiento de {child.name}:</b>\n" + "\n".join(
            _fmt_control_linea(c) for c in controles
        )
        await message.answer(tabla)
        if any(
            c.peso_kg is not None or c.talla_cm is not None or c.perimetro_cm is not None
            for c in controles
        ):
            from app import charts

            png = charts.generar_curva_crecimiento(child.name, controles)
            await message.answer_photo(
                BufferedInputFile(png, filename="crecimiento.png")
            )
        edad = edad_texto(child.birthdate) if child.birthdate else "edad no registrada"
        datos = "; ".join(
            f"{c.fecha:%d/%m/%Y}: peso={c.peso_kg}kg talla={c.talla_cm}cm PC={c.perimetro_cm}cm"
            for c in controles
        )
        await message.answer("🩺 " + await agent.valorar_crecimiento(child.name, edad, datos))

    elif ext.intent == "resumen_semanal":
        await _enviar_resumen_semanal(message, child)

    elif ext.intent == "informe_pediatra":
        await _enviar_informe(message, child)

    elif ext.intent == "pregunta_bebe":
        contexto = f"El bebé se llama {child.name}"
        if child.birthdate:
            contexto += f" y tiene {edad_texto(child.birthdate)}"
        consejos = await crud.list_advice(child.id, limit=10)
        if consejos:
            contexto += ". Indicaciones que le ha dado su pediatra: " + "; ".join(
                a.content for a in consejos
            )
        await message.answer(await agent.responder_pregunta(texto, contexto))

    else:
        await message.answer(
            "Te leo 🙂 Puedo <b>guardar hitos</b>, <b>agendar citas</b>, anotar lo que "
            "dice tu <b>pediatra</b>, mostrarte el <b>recap</b> o responder <b>dudas de bebé</b>."
        )


# ---------- Entradas: voz, foto, texto ----------

async def _resolver_activo(message: Message, state: FSMContext):
    """Devuelve el hijo activo, o arranca el onboarding si no hay ninguno."""
    child = await crud.get_active_child(message.from_user.id)
    if child is None:
        await _begin_setup(message, state, primero=True)
    return child


@router.message(F.voice)
async def on_voice(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    await message.answer("🎙️ Escuchando...")
    tg_file = await message.bot.get_file(message.voice.file_id)
    buffer = await message.bot.download_file(tg_file.file_path)
    try:
        texto = await agent.transcribir(buffer.read(), message.voice.mime_type or "audio/ogg")
    except Exception:
        await message.answer("No pude escuchar la nota 🙈, ¿me la escribes?")
        return
    if not texto:
        await message.answer("No entendí la nota de voz 🙈, ¿me la escribes?")
        return
    await message.answer(f"📝 Te entendí: <i>{texto}</i>")
    await _procesar_texto(message, child, texto, state, source="audio")


async def _adjuntar_media(message: Message, child, referencia, media_ref: str) -> None:
    """Pega una foto/video a un hito que ya existe."""
    hitos = await crud.list_milestones(child.id)
    h = _elegir_registro(hitos, referencia, lambda r: r.description)
    if not h:
        await message.answer(
            "No encontré ese hito para adjuntarle el recuerdo 🙈. "
            "Dime cuál (ej. «el de que gateó») o «el último»."
        )
        return
    await crud.update_milestone_media(h.id, media_ref)
    tipo = "video" if media_ref.startswith("tgv:") else "foto"
    await message.answer(
        f"📎 Le adjunté la {tipo} al hito:\n• {h.happened_on:%d/%m/%Y} — <i>{h.description}</i> ✅"
    )


async def _sugerir_media(message: Message, state: FSMContext, milestone_id: int) -> None:
    """Tras guardar un hito por texto/voz, ofrece adjuntarle foto/video (por chat)."""
    await state.update_data(pending_media_hito=milestone_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Ahora no", callback_data="skipmedia")]]
    )
    await message.answer(
        "📸 ¿Quieres añadir una foto o video para recordar este momento?",
        reply_markup=kb,
    )


async def _adjuntar_media_pendiente(
    message: Message, state: FSMContext, media_ref: str
) -> bool:
    """Si en ESTE chat hay un hito esperando media, le adjunta esta foto/video
    (sin re-analizar ni crear otro hito). Devuelve True si lo hizo."""
    data = await state.get_data()
    pending = data.get("pending_media_hito")
    if pending is None:
        return False
    await state.update_data(pending_media_hito=None)
    m = await crud.get_milestone(pending)
    if m is None or await crud.resolver_hijo(message.from_user.id, m.child_id) is None:
        return False  # ya no existe o sin acceso → cae al flujo normal
    await crud.update_milestone_media(pending, media_ref)
    await message.answer("📎 ¡Listo! Lo guardé en ese momento ✅")
    return True


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    caption = (message.caption or "").strip()
    media_ref = await _save_photo_ref(message)

    # ¿Hay un hito recién creado esperando foto en este chat? → adjúntala ahí.
    if await _adjuntar_media_pendiente(message, state, media_ref):
        return

    # ¿Quiere adjuntar la foto a un hito que YA existe?
    mp = None
    if caption:
        mp = await agent.clasificar_media(caption, hoy().isoformat(), child.name)
        if mp.accion == "adjuntar":
            await _adjuntar_media(message, child, mp.referencia, media_ref)
            return

    # Análisis visual: ¿es una indicación médica?
    try:
        imagen = await _download_photo_bytes(message)
        analisis = await agent.analizar_foto(imagen, "image/jpeg", hoy().isoformat(), child.name)
    except Exception:
        analisis = None
    if analisis and analisis.tipo == "error":
        await message.answer(
            "⏳ No pude analizar la foto ahora mismo (límite del plan gratis de Gemini). "
            "Reenvíamela en unos segundos 🙂"
        )
        return
    if analisis and analisis.tipo == "medico" and analisis.contenido:
        await crud.add_advice(
            message.from_user.id, child.id, analisis.contenido, source="foto", photo_ref=media_ref
        )
        await message.answer(
            f"🩺 Guardé la indicación del pediatra para {child.name}:\n<i>{analisis.contenido}</i>"
        )
        return

    # Momento nuevo
    if mp is not None:  # había pie de foto
        fecha = _parse_date(mp.fecha) or hoy()
        desc = mp.descripcion or caption
    else:
        fecha = (_parse_date(analisis.fecha) if analisis else None) or hoy()
        desc = (analisis.descripcion if analisis else None) or "Un momento para recordar"
    await crud.add_milestone(message.from_user.id, child.id, desc, fecha, media_ref)
    await message.answer(f"📸 Hito con foto guardado ({fecha:%d/%m/%Y}):\n<i>{desc}</i>")


@router.message(F.video)
async def on_video(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    caption = (message.caption or "").strip()
    media_ref = await _save_video_ref(message)

    if await _adjuntar_media_pendiente(message, state, media_ref):
        return

    if caption:
        mp = await agent.clasificar_media(caption, hoy().isoformat(), child.name)
        if mp.accion == "adjuntar":
            await _adjuntar_media(message, child, mp.referencia, media_ref)
            return
        fecha = _parse_date(mp.fecha) or hoy()
        desc = mp.descripcion or caption
    else:
        fecha = hoy()
        desc = "Un video para recordar"
    await crud.add_milestone(message.from_user.id, child.id, desc, fecha, media_ref)
    await message.answer(f"🎥 Hito con video guardado ({fecha:%d/%m/%Y}):\n<i>{desc}</i>")


@router.message(Command("recap"))
async def cmd_recap(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if child:
        await _enviar_recap(message, child)


@router.message(Command("semana"))
async def cmd_semana(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if child:
        await _enviar_resumen_semanal(message, child)


@router.message(Command("informe"))
async def cmd_informe(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if child:
        await _enviar_informe(message, child)


@router.message(Command("compartir"))
async def cmd_compartir(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    rol = await crud.member_role(message.from_user.id, child.family_id)
    if not roles.puede_gestionar_miembros(rol or ""):
        await message.answer("Solo un <b>admin</b> puede compartir la bitácora 🔒")
        return
    token = await crud.crear_invitacion(child.family_id, message.from_user.id)
    link = f"https://t.me/{settings.telegram_bot_username}?start=join_{token}"
    await message.answer(
        "🔗 Comparte este enlace para que otra persona entre a la bitácora "
        "(válido <b>24h</b>, <b>un solo uso</b>, entra como editor):\n\n"
        f"{link}"
    )


@router.message(Command("mi_familia"))
async def cmd_mi_familia(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    family_id = child.family_id
    rol = await crud.member_role(message.from_user.id, family_id)
    miembros = await crud.list_members(family_id)
    hijos = await crud.family_children(family_id)

    lineas = ["👨‍👩‍👧 <b>Tu familia</b>"]
    lineas.append(
        "👶 Bebés: " + (", ".join(h.name for h in hijos) if hijos else "aún ninguno")
    )
    lineas.append("\n<b>Miembros:</b>")
    for m in miembros:
        nombre = m.display_name or f"chat {m.chat_id}"
        corona = " 👑" if roles.puede_gestionar_miembros(m.role) else ""
        lineas.append(f"• {nombre} — {m.role}{corona}")

    kb = None
    if roles.puede_gestionar_miembros(rol or ""):
        botones = [
            [
                InlineKeyboardButton(
                    text=f"🚫 Quitar a {m.display_name or m.chat_id}",
                    callback_data=f"revoke:{family_id}:{m.chat_id}",
                )
            ]
            for m in miembros
            if m.chat_id != message.from_user.id
        ]
        if botones:
            kb = InlineKeyboardMarkup(inline_keyboard=botones)
            lineas.append("\n<i>Como admin, puedes revocar accesos abajo.</i>")
    await message.answer("\n".join(lineas), reply_markup=kb)


@router.message(Command("mi_id"))
async def cmd_mi_id(message: Message) -> None:
    await message.answer(
        f"Tu ID de Telegram es <code>{message.from_user.id}</code>.\n"
        "Si administras el bot, ponlo en la variable <b>ALLOWED_USER_IDS</b>."
    )


@router.message(Command("ping"))
async def ping(message: Message) -> None:
    await message.answer("pong ✅ (Bitácora Bebé · agente Gemini)")


@router.message(F.text)
async def on_text(message: Message, state: FSMContext) -> None:
    child = await _resolver_activo(message, state)
    if not child:
        return
    await _procesar_texto(message, child, message.text, state)
