"""Overlay semitransparente con spinner y un mensaje, centrado sobre su widget padre.

    self._ov = OverlayCarga(self, "Cargando base de ventas…")
    self._ov.mostrar()
    ...
    self._ov.ocultar()
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.ui.widgets.spinner import Spinner


class OverlayCarga(widget.QFrame):
    def __init__(self, parent, mensaje="Cargando…"):
        super().__init__(parent)
        self.setObjectName("overlayCarga")
        self.setAttribute(core.Qt.WA_StyledBackground, True)

        self._spinner = Spinner(self)
        self._label = widget.QLabel(mensaje, self)
        self._label.setObjectName("overlayCargaLabel")
        self._label.setAlignment(core.Qt.AlignCenter)

        lay = widget.QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addStretch()
        lay.addWidget(self._spinner, 0, core.Qt.AlignCenter)
        lay.addWidget(self._label, 0, core.Qt.AlignCenter)
        lay.addStretch()

        # Aparece con un fundido corto en vez de saltar de golpe.
        self._efecto = widget.QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(1.0)
        self.setGraphicsEffect(self._efecto)
        self._anim = core.QPropertyAnimation(self._efecto, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(core.QEasingCurve.OutCubic)

        parent.installEventFilter(self)
        self._ajustar()
        self.hide()

    def setMensaje(self, texto):
        self._label.setText(texto)

    def mostrar(self):
        self._ajustar()
        if not self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._efecto.setOpacity(0.0)
            self._anim.start()
        self.show()
        self.raise_()

    def ocultar(self):
        self._anim.stop()
        self.hide()

    def _ajustar(self):
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())

    def eventFilter(self, obj, ev):
        if obj is self.parentWidget() and ev.type() == core.QEvent.Resize:
            self._ajustar()
        return super().eventFilter(obj, ev)
