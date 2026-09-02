"""Resolución de rutas de assets (dev y ejecutable PyInstaller)."""
import os
import sys


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        # .../src/ui/recursos.py -> raíz del proyecto
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)


def icono(nombre: str) -> str:
    """Ruta a un ícono de `src/Distribuidora/`."""
    return resource_path(os.path.join("src", "Distribuidora", nombre))
