"""Señales globales de la aplicación para que las pantallas se enteren de lo que pasa en otras
sin conocerse entre sí (p. ej. el modal de reclamos avisa a la ventana principal que algo cambió,
y esta refresca el indicador de alertas).

    from src.ui.eventos import bus
    bus.reclamos_modificados.connect(mi_slot)     # escuchar
    bus.reclamos_modificados.emit()               # avisar
"""
import PyQt5.QtCore as core


class _Bus(core.QObject):
    #: se creó un reclamo, cambió de estado o se marcó como revisado
    reclamos_modificados = core.pyqtSignal()


bus = _Bus()
