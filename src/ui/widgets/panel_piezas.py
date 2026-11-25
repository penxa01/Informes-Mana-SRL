"""Piezas visuales del panel de control: tarjeta con sombra suave, cifra que cuenta hasta su valor, chip de
variación, leyenda, pestañas tipo píldora con indicador deslizante y la sección «Cómo se cobró».

Los colores y tamaños de texto viven en `estilos.qss` (sección «Panel de control»); acá solo la estructura y
lo que se dibuja a mano.
"""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

from src.controllers import panel_vista as pv
from src.ui.widgets.graficos import BarraProporcion
from src.ui.widgets.tarjeta import TarjetaPintada

_SOMBRA = 10      # lugar que se reserva alrededor de la tarjeta para su sombra
_RADIO = 14


def vaciar(layout):
    """Saca y destruye todo lo que hay en un layout."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            vaciar(item.layout())


def etiqueta(texto, nombre, parent=None):
    lbl = widget.QLabel(texto, parent)
    lbl.setObjectName(nombre)
    return lbl


def nota(texto, alerta=False):
    lbl = etiqueta(texto, "panelNota")
    lbl.setWordWrap(True)
    if alerta:
        lbl.setProperty("alerta", True)
    return lbl


class TarjetaPanel(TarjetaPintada):
    """Tarjeta blanca con encabezado (título a la izquierda, subtítulo a la derecha) y un cuerpo vertical.

    El fondo, el borde y la sombra los pinta `TarjetaPintada` (sin `QGraphicsDropShadowEffect`, ver `widgets/tarjeta.py`).
    """

    def __init__(self, titulo, subtitulo="", fondo="#ffffff", borde="#eef1f8", parent=None):
        super().__init__(sombra=_SOMBRA, radio=_RADIO, fondo=fondo, borde=borde, parent=parent)
        self.setObjectName("panelTarjeta")
        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(_SOMBRA + 18, _SOMBRA + 16, _SOMBRA + 18, _SOMBRA + 16)
        lay.setSpacing(6)
        if titulo or subtitulo:     # sin ninguno, una tarjeta pelada (los tiles de la cartera)
            cab = widget.QHBoxLayout()
            cab.setSpacing(8)
            self.lbl_titulo = etiqueta(titulo, "panelTitulo")
            cab.addWidget(self.lbl_titulo)
            cab.addStretch(1)
            if subtitulo:
                cab.addWidget(etiqueta(subtitulo[:1].upper() + subtitulo[1:], "panelSubtitulo"))
            lay.addLayout(cab)
        self.cuerpo = lay

    def agregar(self, w, alineacion=None):
        if isinstance(w, widget.QLayout):
            self.cuerpo.addLayout(w)
        elif alineacion is not None:
            self.cuerpo.addWidget(w, 0, alineacion)
        else:
            self.cuerpo.addWidget(w)
        return w


class CifraAnimada(widget.QLabel):
    """Número grande que cuenta desde cero hasta su valor la primera vez que se ve.

    `formato(v)` devuelve el texto para el valor `v`; `unidad` (opcional) va al lado, más chica.
    """

    def __init__(self, valor, formato, unidad=None, nombre="panelCifra", tono=None, parent=None):
        super().__init__(parent)
        self.setObjectName(nombre)
        if tono:
            self.setProperty("tono", tono)
        self.setTextFormat(core.Qt.RichText)
        self._valor = valor
        self._formato = formato
        self._unidad = unidad
        self._arrancado = False
        self._poner(valor)
        self.setMinimumWidth(self.sizeHint().width())   # no se mueve nada mientras cuenta
        self._anim = core.QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(valor))
        self._anim.setDuration(800)
        self._anim.setEasingCurve(core.QEasingCurve.OutCubic)
        # Método y no lambda: un lambda no se desconecta al destruirse el label y la animación (su hija) puede emitir
        # una última vez cuando el label ya se destruyó -> acceso a memoria liberada.
        self._anim.valueChanged.connect(self._al_cambiar)

    def _al_cambiar(self, v):
        self._poner(float(v))

    def _poner(self, v):
        texto = self._formato(v)
        if self._unidad:
            texto += f' <span style="font-size:17px; font-weight:600; color:#566377;">{self._unidad}</span>'
        self.setText(texto)

    def showEvent(self, evento):
        if not self._arrancado:
            self._arrancado = True
            self._poner(0.0)
            self._anim.start()
        super().showEvent(evento)


class ChipDelta(widget.QLabel):
    """Variación contra el período anterior: verde si sube, rojo si baja, gris si no hay cambio."""

    def __init__(self, actual, anterior, texto_contra, puntos=False, parent=None):
        clase, texto = pv.chip_delta(actual, anterior, texto_contra, puntos)
        super().__init__(texto, parent)
        self.setObjectName("chipDelta")
        self.setProperty("delta", clase)
        self.setSizePolicy(widget.QSizePolicy.Maximum, widget.QSizePolicy.Fixed)


def fila_izquierda(w):
    """Una fila con `w` pegado a la izquierda (para que un chip no se estire a lo ancho)."""
    fila = widget.QHBoxLayout()
    fila.setContentsMargins(0, 4, 0, 4)
    fila.addWidget(w)
    fila.addStretch(1)
    return fila


def leyenda(items):
    """[(color, texto), ...] como puntitos de color con su nombre."""
    fila = widget.QHBoxLayout()
    fila.setSpacing(16)
    for color, texto in items:
        punto = widget.QLabel()
        punto.setFixedSize(10, 10)
        punto.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
        fila.addWidget(punto)
        fila.addWidget(etiqueta(texto, "panelLeyenda"))
        fila.addSpacing(4)
    fila.addStretch(1)
    return fila


class PestanasPildora(widget.QWidget):
    """Pestañas dentro de una píldora gris; la blanca que marca la activa se desliza hasta la nueva."""
    cambio = core.pyqtSignal(int)

    def __init__(self, nombres, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._botones = []
        self._actual = 0
        self._x = 0.0
        self._ancho = 0.0
        lay = widget.QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        for i, nombre in enumerate(nombres):
            b = widget.QPushButton(nombre)
            b.setObjectName("panelPestana")
            b.setCursor(core.Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setFocusPolicy(core.Qt.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self.elegir(idx))
            lay.addWidget(b)
            self._botones.append(b)
        self._botones[0].setChecked(True)
        self._anim = core.QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(core.QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._mover)

    def elegir(self, idx, avisar=True):
        for i, b in enumerate(self._botones):
            b.setChecked(i == idx)
        if idx != self._actual or self._ancho == 0:
            destino = self._botones[idx].geometry()
            self._anim.stop()
            self._anim.setStartValue(core.QPointF(self._x, self._ancho))
            self._anim.setEndValue(core.QPointF(destino.x(), destino.width()))
            self._anim.start()
        self._actual = idx
        if avisar:
            self.cambio.emit(idx)

    def _mover(self, v):
        self._x, self._ancho = v.x(), v.y()
        self.update()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        g = self._botones[self._actual].geometry()
        self._x, self._ancho = g.x(), g.width()

    def showEvent(self, evento):
        super().showEvent(evento)
        g = self._botones[self._actual].geometry()
        self._x, self._ancho = g.x(), g.width()

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        p.setPen(core.Qt.NoPen)
        p.setBrush(gui.QColor("#eef1f8"))
        r = self.height() / 2
        p.drawRoundedRect(core.QRectF(self.rect()), r, r)
        if self._ancho > 0:
            h = self.height() - 8
            ind = core.QRectF(self._x, 4, self._ancho, h)
            p.setBrush(gui.QColor(24, 36, 96, 14))
            p.drawRoundedRect(ind.adjusted(0, 1.5, 0, 1.5), h / 2, h / 2)   # sombrita
            p.setBrush(gui.QColor("#ffffff"))
            p.drawRoundedRect(ind, h / 2, h / 2)


def seccion_desglose(d, color_borde="#eef1f8"):
    """«Cómo se cobró»: barra de proporciones + una fila por medio de pago. `d` es el desglose de un período."""
    sec = widget.QWidget()
    lay = widget.QVBoxLayout(sec)
    lay.setContentsMargins(0, 8, 0, 0)
    lay.setSpacing(8)

    linea = widget.QFrame()
    linea.setFixedHeight(1)
    linea.setStyleSheet(f"background-color: {color_borde};")
    lay.addWidget(linea)
    lay.addSpacing(4)
    lay.addWidget(etiqueta("Cómo se cobró", "panelH4"))

    medios = pv.medios_de_cobro(d)
    lay.addWidget(BarraProporcion([(m["valor"], m["color"]) for m in medios]))
    lay.addSpacing(2)

    for m in medios:
        fila = widget.QHBoxLayout()
        fila.setSpacing(10)
        punto = widget.QLabel()
        punto.setFixedSize(10, 10)
        punto.setStyleSheet(f"background-color: {m['color']}; border-radius: 3px;")
        fila.addWidget(punto)
        fila.addWidget(etiqueta(m["nombre"], "panelMedio"), 1)
        monto = etiqueta(pv.dinero(m["valor"]), "panelMedioMonto")
        monto.setToolTip(f"$ {pv.numero(m['valor'], 2)}")
        fila.addWidget(monto)
        pct = etiqueta(m["porcentaje"], "panelMedioPct")
        pct.setFixedWidth(46)
        pct.setAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
        fila.addWidget(pct)
        lay.addLayout(fila)

    aviso = pv.aviso_diferencia(d)
    if aviso:
        lay.addWidget(nota(aviso, alerta=True))
    return sec
