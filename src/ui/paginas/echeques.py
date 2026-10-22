"""Sección E-CHEQUES — control de cheques electrónicos (carga lazy)."""
import PyQt5.QtWidgets as widget

from src.Views.Echeq.EcheqDBF import EcheqWindow
from src.ui.paginas.base import PaginaBase


class PaginaEcheques(PaginaBase):
    def __init__(self, app):
        super().__init__(app)
        self._cargado = False

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._w = EcheqWindow()
        lay.addWidget(self._w)

    def on_activar(self):
        # Carga lazy: los Excel de e-cheques se leen la primera vez que se abre
        # la pestaña, no al iniciar la app.
        if not self._cargado:
            self._cargado = True
            self._w.cargar_datos_iniciales()

    def acciones_barra(self):
        return self._w.acciones_toolbar
