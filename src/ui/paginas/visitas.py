"""Sección VISITAS — registro de visitas de los vendedores (planilla de Google, carga lazy)."""
import PyQt5.QtWidgets as widget

from src.Views.Visitas.VisitasWindow import VisitasWindow
from src.ui.paginas.base import PaginaBase


class PaginaVisitas(PaginaBase):
    def __init__(self, app):
        super().__init__(app)
        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._w = VisitasWindow()
        lay.addWidget(self._w)

    def on_activar(self):
        # La primera vez lee la planilla; al volver a la pestaña la relee si pasaron un par de
        # minutos (los vendedores van cargando visitas durante el día).
        self._w.refrescar_si_corresponde()
