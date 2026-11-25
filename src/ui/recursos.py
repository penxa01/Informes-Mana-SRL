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


def _chevron(color="#64748b"):
    """Ruta a un PNG con la flechita ▾ de los combos (QSS no dibuja flechas sin una imagen). Se genera una vez en
    la carpeta temporal: así no hay un archivo más que agregar al .exe."""
    import tempfile

    from PyQt5 import QtCore, QtGui

    ruta = os.path.join(tempfile.gettempdir(), f"mana_chevron_{color.lstrip('#')}.png")
    if not os.path.exists(ruta):
        pix = QtGui.QPixmap(24, 24)           # 2x: se ve nítido en pantallas de alta densidad
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        lapiz = QtGui.QPen(QtGui.QColor(color), 3.2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        p.setPen(lapiz)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(6, 9), QtCore.QPointF(12, 15), QtCore.QPointF(18, 9)]))
        p.end()
        pix.save(ruta, "PNG")
    return ruta.replace(chr(92), "/")


def leer_estilos():
    """Contenido de `estilos.qss` listo para `setStyleSheet` (con las rutas de imágenes resueltas)."""
    qss = resource_path(os.path.join("src", "ui", "estilos.qss"))
    with open(qss, encoding="utf-8") as fh:
        return fh.read().replace("@CHEVRON@", _chevron())
