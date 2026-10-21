"""Sección CUENTAS CORRIENTES — deuda pendiente por cliente (carga lazy)."""
import PyQt5.QtWidgets as widget

from src.Views.CuentasCorrientes.CuentasCorrientesWindow import CuentasCorrientesWindow
from src.ui.paginas.base import PaginaBase


class PaginaCuentasCorrientes(PaginaBase):
    def __init__(self, app):
        super().__init__(app)
        self._cargado = False

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._w = CuentasCorrientesWindow()
        lay.addWidget(self._w)

    def on_activar(self):
        # Carga lazy: los DBF se leen la primera vez que se abre la pestaña.
        if not self._cargado:
            self._cargado = True
            self._w.cargar_datos()

    def abrir_reclamos(self):
        """Abre el modal de reclamos (esperando los datos si hace falta)."""
        self._cargado = True        # evita que on_activar vuelva a lanzar la carga
        self._w.abrir_reclamos_cuando_listo()

    def acciones_barra(self):
        return self._w.acciones_toolbar
