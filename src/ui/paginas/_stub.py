"""Página placeholder para F1. Cada `PaginaXxx` real la reemplaza en su fase F2x."""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.ui.paginas.base import PaginaBase


class PaginaStub(PaginaBase):
    titulo = "Sección"
    fase = "F2"

    def __init__(self, app):
        super().__init__(app)
        lay = widget.QVBoxLayout(self)
        lay.setAlignment(core.Qt.AlignCenter)
        t = widget.QLabel(self.titulo)
        t.setObjectName("stubTitulo")
        t.setAlignment(core.Qt.AlignCenter)
        sub = widget.QLabel(f"En construcción — {self.fase}")
        sub.setObjectName("stubSub")
        sub.setAlignment(core.Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(sub)

    def on_ventas_listas(self, df):
        # F1: solo deja constancia de que los datos llegaron
        if hasattr(self, "app") and getattr(self.app, "df_ventas", None) is not None:
            pass
