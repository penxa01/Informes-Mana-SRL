"""Contenedor con header clicable que muestra / oculta su contenido.

    barra = BarraColapsable("Filtros")
    barra.cuerpo_layout().addWidget(...)
    layout_pagina.addWidget(barra)
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget


class BarraColapsable(widget.QFrame):
    def __init__(self, titulo, colapsada=False, parent=None):
        super().__init__(parent)
        self.setObjectName("barraColapsable")

        self._boton = widget.QToolButton(self)
        self._boton.setObjectName("barraColapsableHeader")
        self._boton.setText("  " + titulo)
        self._boton.setCheckable(True)
        self._boton.setToolButtonStyle(core.Qt.ToolButtonTextBesideIcon)
        self._boton.setArrowType(core.Qt.DownArrow)
        self._boton.setSizePolicy(widget.QSizePolicy.Expanding, widget.QSizePolicy.Fixed)
        self._boton.clicked.connect(self._toggle)

        self._cuerpo = widget.QWidget(self)
        self._cuerpo_layout = widget.QHBoxLayout(self._cuerpo)
        self._cuerpo_layout.setContentsMargins(8, 6, 8, 8)
        self._cuerpo_layout.setSpacing(8)

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._boton)
        lay.addWidget(self._cuerpo)

        self.set_colapsada(colapsada)

    def cuerpo_layout(self):
        return self._cuerpo_layout

    def set_colapsada(self, colapsada):
        self._boton.setChecked(not colapsada)
        self._cuerpo.setVisible(not colapsada)
        self._boton.setArrowType(core.Qt.RightArrow if colapsada else core.Qt.DownArrow)

    def _toggle(self):
        self.set_colapsada(self._cuerpo.isVisible())
