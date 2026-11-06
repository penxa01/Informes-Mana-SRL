"""Spinner circular (arco que gira) dibujado a mano; sin dependencias ni archivos .gif.

Solo gira mientras está visible: no gasta CPU oculto.
"""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget


class Spinner(widget.QWidget):
    def __init__(self, parent=None, diametro=36, grosor=4, color="#2640dc"):
        super().__init__(parent)
        self._angulo = 0
        self._grosor = grosor
        self._color = gui.QColor(color)
        self._pista = gui.QColor("#e2e8f0")   # slate-200: el anillo de fondo
        self.setFixedSize(diametro, diametro)
        self.setAttribute(core.Qt.WA_TransparentForMouseEvents, True)

        self._anim = core.QPropertyAnimation(self, b"angulo", self)
        self._anim.setStartValue(0)
        self._anim.setEndValue(360)
        self._anim.setDuration(900)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(core.QEasingCurve.Linear)

    def _get_angulo(self):
        return self._angulo

    def _set_angulo(self, valor):
        self._angulo = valor
        self.update()

    angulo = core.pyqtProperty(int, _get_angulo, _set_angulo)

    def showEvent(self, evento):
        self._anim.start()
        super().showEvent(evento)

    def hideEvent(self, evento):
        self._anim.stop()
        super().hideEvent(evento)

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        m = self._grosor / 2 + 1
        rect = core.QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

        lapiz = gui.QPen(self._pista, self._grosor)
        p.setPen(lapiz)
        p.drawEllipse(rect)

        lapiz = gui.QPen(self._color, self._grosor, core.Qt.SolidLine, core.Qt.RoundCap)
        p.setPen(lapiz)
        # Qt mide los ángulos en 1/16 de grado, antihorario; restamos para girar en sentido horario.
        p.drawArc(rect, int(-self._angulo * 16), 100 * 16)
