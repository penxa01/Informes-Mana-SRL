"""Gráficos del panel de control, dibujados con QPainter: barras apiladas, anillo de porcentaje y barra de
proporciones. Replican `movil/pwa/js/graficos.js` (mismas medidas y colores) y, como allá, se dibujan con una
animación de entrada que arranca la primera vez que se ven.

Cada gráfico se estira con su tarjeta: no hace falta calcular anchos ni volver a armarlo al cambiar el tamaño.
"""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

COLOR_TEXTO = gui.QColor("#566377")
COLOR_TEXTO_TENUE = gui.QColor("#cbd5e1")
COLOR_BASE = gui.QColor("#e3e8f3")
COLOR_TINTA = gui.QColor("#0f172a")
COLOR_HOVER = gui.QColor("#f1f5f9")

_SALIDA_SUAVE = core.QEasingCurve(core.QEasingCurve.OutCubic)


def _fuente(px, negrita=False):
    f = gui.QFont()
    f.setPixelSize(px)
    f.setBold(negrita)
    return f


class _Animado(widget.QWidget):
    """Base: un reloj en milisegundos (`_t`) que corre una vez, al aparecer por primera vez."""

    def __init__(self, total_ms, parent=None):
        super().__init__(parent)
        self._total = float(total_ms)
        self._t = self._total          # sin animar: queda completo
        self._arrancado = False
        self._anim = core.QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(self._total)
        self._anim.setDuration(int(total_ms))
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, valor):
        self._t = float(valor)
        self.update()

    def showEvent(self, evento):
        if not self._arrancado:
            self._arrancado = True
            self._t = 0.0
            self._anim.start()
        super().showEvent(evento)

    def _avance(self, retraso, duracion):
        """0..1 con salida suave, para una pieza que arranca en `retraso` ms y dura `duracion`."""
        x = max(0.0, min(1.0, (self._t - retraso) / duracion))
        return _SALIDA_SUAVE.valueForProgress(x)


class GraficoBarras(_Animado):
    """Una columna por dato, apiladas si el dato trae varias partes (la primera abajo).

    datos: [{"etiqueta"?, "partes": [(valor, "#color"), ...], "titulo"?, "valor_visible"?, "tenue"?}]
      etiqueta       texto bajo la barra
      titulo         tooltip al pasar el mouse
      valor_visible  texto sobre la barra
      tenue          el dato todavía no ocurrió (un día futuro): se dibuja un puntito gris
    """
    _MARGEN_SUP = 14
    _MARGEN_INF = 16
    _ENTRADA_MS = 600
    _ESCALON_MS = 14

    def __init__(self, datos, alto=130, parent=None):
        super().__init__(self._ENTRADA_MS + len(datos) * self._ESCALON_MS, parent)
        self._datos = datos
        self._hover = -1
        self.setMinimumHeight(alto)
        self.setFixedHeight(alto)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setSizePolicy(widget.QSizePolicy.Expanding, widget.QSizePolicy.Fixed)

    def _geometria(self):
        n = max(1, len(self._datos))
        hueco = self.width() / n
        grosor = max(3.0, min(34.0, hueco * 0.62))
        return hueco, grosor

    def mouseMoveEvent(self, evento):
        hueco, _ = self._geometria()
        i = int(evento.x() // hueco) if hueco else -1
        i = i if 0 <= i < len(self._datos) else -1
        if i != self._hover:
            self._hover = i
            self.setToolTip((self._datos[i].get("titulo") or "") if i >= 0 else "")
            self.update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(evento)

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        ancho, alto = self.width(), self.height()
        area = alto - self._MARGEN_SUP - self._MARGEN_INF
        y0 = self._MARGEN_SUP + area
        hueco, grosor = self._geometria()
        maximo = max([0.0] + [sum(max(0.0, v) for v, _ in d["partes"]) for d in self._datos])

        if self._hover >= 0:
            p.setPen(core.Qt.NoPen)
            p.setBrush(COLOR_HOVER)
            p.drawRoundedRect(core.QRectF(self._hover * hueco + 1, self._MARGEN_SUP - 8, hueco - 2, area + 8), 5, 5)

        p.setPen(gui.QPen(COLOR_BASE, 1))
        p.drawLine(core.QPointF(0, y0 + 0.5), core.QPointF(ancho, y0 + 0.5))

        for i, d in enumerate(self._datos):
            x = i * hueco + (hueco - grosor) / 2
            avance = self._avance(i * self._ESCALON_MS, self._ENTRADA_MS)
            acumulado = 0.0
            p.setPen(core.Qt.NoPen)
            for valor, color in d["partes"]:
                valor = max(0.0, valor)
                if valor <= 0 or maximo <= 0:
                    continue
                h = max(1.0, valor / maximo * area)
                p.setBrush(gui.QColor(color))
                alto_vivo = h * avance
                p.drawRoundedRect(core.QRectF(x, y0 - acumulado * avance - alto_vivo, grosor, alto_vivo), 3, 3)
                acumulado += h
            if acumulado == 0:
                c = gui.QColor(COLOR_BASE)
                if d.get("tenue"):
                    c.setAlphaF(0.6)
                p.setBrush(c)
                p.drawRoundedRect(core.QRectF(x, y0 - 2, grosor, 2), 1, 1)
            if d.get("valor_visible") and acumulado > 0:
                p.setPen(COLOR_TEXTO)
                p.setFont(_fuente(9))
                p.setOpacity(avance)
                p.drawText(core.QRectF(x - 12, y0 - acumulado * avance - 17, grosor + 24, 13), core.Qt.AlignCenter, d["valor_visible"])
                p.setOpacity(1.0)
            if d.get("etiqueta"):
                p.setPen(COLOR_TEXTO_TENUE if d.get("tenue") else COLOR_TEXTO)
                p.setFont(_fuente(10))
                p.drawText(core.QRectF(x - 14, alto - 14, grosor + 28, 13), core.Qt.AlignCenter, d["etiqueta"])


class Anillo(_Animado):
    """Porcentaje (0-100) en el color dado y el resto en gris; el texto va en el centro."""
    _GROSOR = 12

    def __init__(self, porcentaje, color, texto, tamano=112, parent=None):
        super().__init__(1000, parent)
        self._pct = max(0.0, min(100.0, float(porcentaje)))
        self._color = gui.QColor(color)
        self._texto = texto
        self.setFixedSize(tamano, tamano)

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        m = self._GROSOR / 2 + 1
        rect = core.QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(gui.QPen(COLOR_BASE, self._GROSOR))
        p.drawEllipse(rect)

        avance = self._avance(100, 900)
        barrido = self._pct / 100 * 360 * avance
        if barrido > 0:
            p.setPen(gui.QPen(self._color, self._GROSOR, core.Qt.SolidLine, core.Qt.RoundCap))
            p.drawArc(rect, 90 * 16, int(-barrido * 16))   # desde arriba, en sentido horario

        p.setPen(COLOR_TINTA)
        p.setFont(_fuente(19, True))
        p.drawText(self.rect(), core.Qt.AlignCenter, self._texto)


class BarraProporcion(_Animado):
    """Barra horizontal repartida en tramos (cómo se compone un total). Los tramos en 0 no se dibujan.

    partes: [(valor, "#color"), ...]
    """

    def __init__(self, partes, alto=12, parent=None):
        super().__init__(900, parent)
        self._partes = partes
        self.setFixedHeight(alto)
        self.setMinimumWidth(120)
        self.setSizePolicy(widget.QSizePolicy.Expanding, widget.QSizePolicy.Fixed)

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        ancho, alto = self.width(), self.height()

        forma = gui.QPainterPath()
        forma.addRoundedRect(core.QRectF(0, 0, ancho, alto), alto / 2, alto / 2)
        p.setClipPath(forma)
        p.fillRect(core.QRectF(0, 0, ancho, alto), COLOR_BASE)

        total = sum(max(0.0, v) for v, _ in self._partes)
        if total > 0:
            # el recorte avanza de izquierda a derecha, como el `clip-path` del celular
            p.setClipRect(core.QRectF(0, 0, ancho * self._avance(100, 800), alto), core.Qt.IntersectClip)
            x = 0.0
            for valor, color in self._partes:
                valor = max(0.0, valor)
                if valor <= 0:
                    continue
                w = valor / total * ancho
                p.fillRect(core.QRectF(x, 0, w, alto), gui.QColor(color))
                if x > 0:
                    p.fillRect(core.QRectF(x - 1, 0, 2, alto), gui.QColor("#ffffff"))   # costura entre tramos
                x += w
