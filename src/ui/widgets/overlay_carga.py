"""Overlay semitransparente con un mensaje, centrado sobre su widget padre.

    self._ov = OverlayCarga(self, "Cargando base de ventas…")
    self._ov.mostrar()
    ...
    self._ov.ocultar()
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget


class OverlayCarga(widget.QFrame):
    def __init__(self, parent, mensaje="Cargando…"):
        super().__init__(parent)
        self.setObjectName("overlayCarga")
        self.setAttribute(core.Qt.WA_StyledBackground, True)

        self._label = widget.QLabel(mensaje, self)
        self._label.setObjectName("overlayCargaLabel")
        self._label.setAlignment(core.Qt.AlignCenter)

        lay = widget.QVBoxLayout(self)
        lay.addStretch()
        lay.addWidget(self._label, 0, core.Qt.AlignCenter)
        lay.addStretch()

        parent.installEventFilter(self)
        self._ajustar()
        self.hide()

    def setMensaje(self, texto):
        self._label.setText(texto)

    def mostrar(self):
        self._ajustar()
        self.show()
        self.raise_()

    def ocultar(self):
        self.hide()

    def _ajustar(self):
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())

    def eventFilter(self, obj, ev):
        if obj is self.parentWidget() and ev.type() == core.QEvent.Resize:
            self._ajustar()
        return super().eventFilter(obj, ev)
