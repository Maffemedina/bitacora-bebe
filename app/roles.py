"""Política de roles — explícita, no comparar strings sueltos.

editor: leer y editar datos familiares (incluye crear hijos).
admin:  editor + invitar, revocar y gestionar miembros.
"""

from app.models import Rol

_RANGO = {Rol.EDITOR.value: 1, Rol.ADMIN.value: 2}


def alcanza(rol: str, rol_min: Rol) -> bool:
    """¿El rol del miembro alcanza el rol mínimo requerido?"""
    return _RANGO.get(rol, 0) >= _RANGO[rol_min.value]


def puede_editar(rol: str) -> bool:
    return alcanza(rol, Rol.EDITOR)


def puede_gestionar_miembros(rol: str) -> bool:
    return alcanza(rol, Rol.ADMIN)
