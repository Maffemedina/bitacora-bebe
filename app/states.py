"""Estados de conversación (FSM de aiogram).

Sirven para 'recordar' pasos de una conversación de varios turnos, como cuando
registramos un hijo nuevo y esperamos su nombre y luego su fecha de nacimiento.
"""

from aiogram.fsm.state import State, StatesGroup


class ChildSetup(StatesGroup):
    name = State()
    birthdate = State()


class ControlMedidas(StatesGroup):
    datos = State()
