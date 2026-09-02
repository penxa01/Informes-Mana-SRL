"""Sección PEDIDOS — gestión de pedidos (PostgreSQL). Sync siempre activo en background."""
import PyQt5.QtWidgets as widget

from src.Views.Pedidos.programarPedido import VentanaProgramarPedido
from src.ui.paginas.base import PaginaBase


class PaginaPedidos(PaginaBase):
    def __init__(self, app):
        super().__init__(app)
        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # el sync_manager vive en el AppWindow (siempre activo)
        self._w = VentanaProgramarPedido(sync_manager=app.sync_pedidos)
        lay.addWidget(self._w)

    def acciones_barra(self):
        return self._w.acciones_toolbar
