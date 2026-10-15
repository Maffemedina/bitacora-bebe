"""El cerebro del agente (Gemini).

Capacidades (todas con el mismo modelo multimodal):
  - entender()          -> clasifica el mensaje y extrae datos (JSON)
  - analizar_foto()     -> ¿es un momento del bebé o una indicación médica?
  - responder_pregunta()-> responde dudas con contexto de edad + pediatra
  - transcribir()       -> nota de voz a texto
  - fecha_en_texto()    -> saca una fecha de un texto libre

Diseño: el modelo solo ENTIENDE; el código (handlers.py) ejecuta las acciones.
"""

import json
from typing import Optional

from pydantic import BaseModel

from app.config import settings


class Extraccion(BaseModel):
    intent: str
    descripcion: Optional[str] = None       # guardar_hito
    fecha: Optional[str] = None             # YYYY-MM-DD (hito o fallecimiento)
    titulo_cita: Optional[str] = None
    fecha_hora_cita: Optional[str] = None   # YYYY-MM-DDTHH:MM
    lugar_cita: Optional[str] = None
    nombre_hijo: Optional[str] = None       # agregar/cambiar/fallecimiento
    recomendacion: Optional[str] = None     # guardar_recomendacion
    referencia: Optional[str] = None        # corregir_hito/corregir_cita: cuál registro
    peso: Optional[float] = None            # registrar_control: kg
    talla: Optional[float] = None           # registrar_control: cm
    perimetro: Optional[float] = None       # registrar_control: perímetro cefálico cm


class Plan(BaseModel):
    """Un mensaje puede traer varias acciones (para uno o varios hijos)."""

    acciones: list[Extraccion]


class FotoAnalisis(BaseModel):
    tipo: str                                # 'momento' | 'medico'
    descripcion: Optional[str] = None        # para momento
    fecha: Optional[str] = None              # YYYY-MM-DD si es visible
    contenido: Optional[str] = None          # para medico: texto extraído


class MediaPlan(BaseModel):
    accion: str                          # 'adjuntar' | 'nuevo'
    referencia: Optional[str] = None     # si adjuntar: cuál hito
    descripcion: Optional[str] = None    # si nuevo
    fecha: Optional[str] = None          # si nuevo: YYYY-MM-DD


class Medidas(BaseModel):
    peso: Optional[float] = None        # kg
    talla: Optional[float] = None       # cm
    perimetro: Optional[float] = None   # perímetro cefálico cm


class _SoloFecha(BaseModel):
    fecha: Optional[str] = None


_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY no está configurada (ver .env).")
        from google import genai

        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def planear(mensaje: str, hoy_iso: str, baby_name: str) -> list[Extraccion]:
    from google.genai import types

    sistema = (
        f"Eres el cerebro de un bot que ayuda a una mamá/papá a llevar la bitácora "
        f"de sus hijos (activo: {baby_name}). Hoy es {hoy_iso}.\n"
        "Clasifica el mensaje en UNO de estos intents y extrae datos:\n"
        "- guardar_hito: CUALQUIER logro, avance o suceso del bebé: caminó, dio sus "
        "primeros pasos, gateó, habló, primera palabra, primer diente, primera "
        "comida/papilla, sonrió, etc. Extrae 'descripcion' (breve, 3ª persona) "
        "y 'fecha' YYYY-MM-DD (si dice 'hoy' o no da fecha, usa hoy).\n"
        "- listar_hitos: pide ver hitos/recap/historia.\n"
        "- agendar_cita: agendar cita/evento con fecha-hora. Extrae 'titulo_cita', "
        "'fecha_hora_cita' YYYY-MM-DDTHH:MM y 'lugar_cita' si lo hay. Las citas son "
        "SIEMPRE futuras: si no dan año, usa la próxima fecha futura respecto a hoy "
        "(NUNCA una fecha pasada). Si no dan hora, usa las 09:00.\n"
        "- listar_citas: pregunta por citas próximas.\n"
        "- guardar_recomendacion: la persona comparte una indicación/recomendación "
        "del pediatra o médico (dosis, cuidados, alimentación...). Pon el texto en "
        "'recomendacion'.\n"
        "- listar_recomendaciones: pide ver lo que recomendó el pediatra.\n"
        "- pregunta_bebe: pregunta de crianza, salud o desarrollo.\n"
        "- agregar_hijo: quiere registrar/agregar OTRO hijo/bebé. Extrae 'nombre_hijo'. "
        "Si el mensaje dice cuándo nació ese bebé (ej. «agregar a Sara, mi otra hija "
        "nació el 15 de abril de 2023»), pon esa fecha de nacimiento en 'fecha' "
        "(2023-04-15) DENTRO de esta misma acción; NUNCA la conviertas en un hito "
        "'nació' aparte ni la dejes vacía.\n"
        "- cambiar_hijo: quiere cambiar al hijo activo o ver otro hijo. Extrae 'nombre_hijo'.\n"
        "- corregir_nacimiento: dice que la FECHA DE NACIMIENTO del bebé está mal y da "
        "la correcta (ej. 'escribí mal la fecha, nació el ...', 'la fecha de nacimiento "
        "correcta es ...', 'corrige su cumpleaños'). Pon la nueva fecha en 'fecha' YYYY-MM-DD.\n"
        "- corregir_hito: dice que un HITO ya guardado tiene la fecha mal y da la "
        "correcta. Extrae 'referencia' (cómo identifica el hito: parte de su "
        "descripción, o 'el último') y la nueva 'fecha' YYYY-MM-DD.\n"
        "- corregir_cita: dice que una CITA ya guardada tiene la fecha/hora mal y da "
        "la correcta. Extrae 'referencia' (ej. 'pediatra', 'la última') y la nueva "
        "'fecha_hora_cita' YYYY-MM-DDTHH:MM.\n"
        "- borrar_hito: quiere ELIMINAR/borrar un hito ya guardado. Extrae 'referencia' "
        "(cuál hito: parte de su descripción, o 'el último').\n"
        "- registrar_control: dice que el bebé fue al pediatra/médico/control (ej. «fue "
        "hoy al pediatra», «fue al médico el 3 de enero»). Extrae 'fecha' YYYY-MM-DD "
        "(si no dice, usa hoy) y, SI las menciona, 'peso' (kg), 'talla' (cm) y "
        "'perimetro' (perímetro cefálico en cm) como números.\n"
        "- ver_crecimiento: pide ver el control/crecimiento/medidas/peso/talla del bebé, "
        "o si está bien de peso/talla.\n"
        "- resumen_semanal: pide el resumen de la semana ('resumen semanal', '¿qué pasó "
        "esta semana?', 'la semana de X', 'cómo estuvo la semana').\n"
        "- informe_pediatra: pide el informe/resumen/PDF para llevar al pediatra o a "
        "la consulta ('prepárame el informe para el pediatra', 'pásame el PDF').\n"
        "- fallecimiento: la persona comunica que un hijo/bebé falleció, murió o se "
        "perdió. Extrae 'nombre_hijo' si lo menciona y 'fecha' YYYY-MM-DD. MUY "
        "IMPORTANTE: cualquier mensaje sobre la muerte o pérdida de un hijo va SIEMPRE "
        "aquí, JAMÁS en guardar_hito.\n"
        "- otro: SOLO saludos ('hola', 'buenas') o charla que no aporta información "
        "del bebé.\n"
        "Ante la duda entre guardar_hito y otro cuando el mensaje describe algo del "
        "bebé, elige guardar_hito.\n"
        "El mensaje puede contener UNA o VARIAS acciones (ej. algo de un hijo y algo "
        "de OTRO hijo). Devuelve una lista 'acciones' con una entrada por cada acción. "
        "En CADA acción, si se menciona el nombre de un hijo, ponlo en 'nombre_hijo'. "
        "Devuelve SOLO el JSON."
    )
    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=mensaje,
            config=types.GenerateContentConfig(
                system_instruction=sistema,
                response_mime_type="application/json",
                response_schema=Plan,
                temperature=0,
            ),
        )
        plan = resp.parsed
        if isinstance(plan, Plan):
            return plan.acciones or [Extraccion(intent="otro")]
        data = json.loads(resp.text)
        acciones = [Extraccion(**a) for a in data.get("acciones", [])]
        return acciones or [Extraccion(intent="otro")]
    except Exception:
        # Falla de red o cuota: intent especial para avisar sin confundir con 'otro'
        return [Extraccion(intent="_error")]


async def analizar_foto(
    image_bytes: bytes, mime: str, hoy_iso: str, baby_name: str
) -> FotoAnalisis:
    from google.genai import types

    sistema = (
        f"Hoy es {hoy_iso}. Analiza la imagen que envía una mamá de su bebé {baby_name}.\n"
        "Si es una foto del bebé o un momento/recuerdo: tipo='momento', 'descripcion' "
        "(qué se ve, breve y cálida) y 'fecha' YYYY-MM-DD solo si hay una fecha visible.\n"
        "Si es un documento, receta, fórmula médica o indicación del pediatra: "
        "tipo='medico' y en 'contenido' extrae en texto claro las recomendaciones o "
        "indicaciones (medicamentos, dosis, cuidados). Devuelve SOLO el JSON."
    )
    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                "Analiza esta imagen.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=sistema,
                response_mime_type="application/json",
                response_schema=FotoAnalisis,
                temperature=0,
            ),
        )
        res = resp.parsed
        if isinstance(res, FotoAnalisis):
            return res
        return FotoAnalisis(**json.loads(resp.text))
    except Exception:
        return FotoAnalisis(tipo="error")


async def clasificar_media(caption: str, hoy_iso: str, baby_name: str) -> MediaPlan:
    """Una foto/video con pie: ¿adjuntar a un hito existente o es un momento nuevo?"""
    from google.genai import types

    sistema = (
        f"Hoy es {hoy_iso}. Una mamá envió una FOTO o VIDEO de su bebé {baby_name} con "
        "este pie. Decide:\n"
        "- Si quiere ADJUNTARLO a un hito que YA existe (ej. «para el hito de que dijo "
        "papá», «esta es del día que gateó», «agrégala a ese hito»): accion='adjuntar' "
        "y 'referencia' = cómo identifica el hito (parte de su descripción, o 'el último').\n"
        "- Si es un momento NUEVO: accion='nuevo', 'descripcion' (breve) y 'fecha' "
        "YYYY-MM-DD si la menciona (si no, déjala vacía).\n"
        "Devuelve SOLO el JSON."
    )
    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=caption,
            config=types.GenerateContentConfig(
                system_instruction=sistema,
                response_mime_type="application/json",
                response_schema=MediaPlan,
                temperature=0,
            ),
        )
        mp = resp.parsed
        if isinstance(mp, MediaPlan):
            return mp
        return MediaPlan(**json.loads(resp.text))
    except Exception:
        return MediaPlan(accion="nuevo")


async def responder_pregunta(pregunta: str, contexto: str) -> str:
    from google.genai import types

    sistema = (
        "Eres un asistente amable para madres y padres. Responde en español, claro y "
        "breve (máx. 5 frases). " + contexto + ". "
        "Si el contexto incluye indicaciones del pediatra, tenlas en cuenta y guíate "
        "por ellas. Da información general de crianza/desarrollo, NUNCA un diagnóstico. "
        "Termina SIEMPRE recordando con cariño consultar al pediatra ante dudas."
    )
    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=pregunta,
            config=types.GenerateContentConfig(system_instruction=sistema, temperature=0.4),
        )
        return (resp.text or "").strip() or "No pude responder ahora mismo, intenta de nuevo 🙂"
    except Exception:
        return "⏳ Estoy saturada un momento (límite del plan gratis de Gemini). Reinténtalo en unos segundos 🙂"


async def parsear_medidas(texto: str) -> Medidas:
    """Extrae peso (kg), talla (cm) y perímetro cefálico (cm) de un texto libre."""
    from google.genai import types

    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Extrae del texto: 'peso' en kilogramos, 'talla' (estatura) en "
                    "centímetros y 'perimetro' (perímetro cefálico) en centímetros. "
                    "Solo los números; deja vacío lo que no aparezca."
                ),
                response_mime_type="application/json",
                response_schema=Medidas,
                temperature=0,
            ),
        )
        m = resp.parsed
        if isinstance(m, Medidas):
            return m
        return Medidas(**json.loads(resp.text))
    except Exception:
        return Medidas()


async def valorar_crecimiento(baby_name: str, edad: str, datos: str) -> str:
    """Comenta el crecimiento con contexto general — NUNCA un diagnóstico."""
    from google.genai import types

    sistema = (
        f"Eres un asistente amable para padres. El bebé {baby_name} tiene {edad}. "
        "Te doy sus controles de crecimiento (peso/talla/perímetro cefálico por fecha). "
        "Comenta en español, breve y cálido: menciona rangos TÍPICOS generales para su "
        "edad y si sus valores se ven dentro de lo esperado o conviene comentarlos con "
        "el pediatra. NUNCA des un diagnóstico ni digas categóricamente que algo 'está "
        "mal'; ante cualquier señal, sugiere consultarlo con el pediatra sin alarmar. "
        "Termina SIEMPRE recordando que el pediatra es quien evalúa el crecimiento."
    )
    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=datos,
            config=types.GenerateContentConfig(system_instruction=sistema, temperature=0.4),
        )
        return (resp.text or "").strip()
    except Exception:
        return "⏳ No pude analizar ahora mismo, intenta en unos segundos 🙂"


async def transcribir(audio_bytes: bytes, mime: str) -> str:
    from google.genai import types

    resp = await _get_client().aio.models.generate_content(
        model=settings.gemini_model,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
            "Transcribe este audio en español. Devuelve solo el texto, sin comillas.",
        ],
    )
    return (resp.text or "").strip()


async def fecha_en_texto(texto: str, hoy_iso: str) -> Optional[str]:
    if not texto.strip():
        return None
    from google.genai import types

    try:
        resp = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=(
                    f"Hoy es {hoy_iso}. Si el texto menciona una fecha, devuélvela en "
                    "YYYY-MM-DD. Si no menciona ninguna, deja 'fecha' vacío."
                ),
                response_mime_type="application/json",
                response_schema=_SoloFecha,
                temperature=0,
            ),
        )
        parsed = resp.parsed
        if isinstance(parsed, _SoloFecha):
            return parsed.fecha or None
        return (json.loads(resp.text) or {}).get("fecha") or None
    except Exception:
        return None
