"""Botón cuadrado, solo ícono, ligado a una ``QAction`` (comparte su ícono, tooltip,
atajo y estado habilitado/deshabilitado). Pensado para ir al lado de otro botón
de una barra de filtros sin gastar espacio:

    fila.addWidget(boton_cuadrado(self.app.accion_actualizar_ventas, alto=self._btn.sizeHint().height()))
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

_ESTILO = (
    "QToolButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; }"
    "QToolButton:hover { background-color: #eff6ff; border-color: #2563eb; }"
    "QToolButton:pressed { background-color: #dbeafe; }"
    "QToolButton:disabled { background-color: #f1f5f9; border-color: #e2e8f0; }"
)


def boton_cuadrado(accion, alto=30):
    """``alto`` x ``alto`` px, ícono centrado, sin texto (el tooltip lo da la acción)."""
    alto = max(int(alto), 24)
    boton = widget.QToolButton()
    boton.setDefaultAction(accion)
    boton.setToolButtonStyle(core.Qt.ToolButtonIconOnly)
    boton.setFixedSize(alto, alto)
    boton.setIconSize(core.QSize(alto - 14, alto - 14))
    boton.setStyleSheet(_ESTILO)
    return boton
