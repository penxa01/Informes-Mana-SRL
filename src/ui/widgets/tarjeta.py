"""Tarjeta blanca reutilizable: encabezado (ícono + título + extra) + separador
+ cuerpo. Estilo común a las secciones (ver el panel de Inicio): bordes suaves, esquinas redondeadas y una sombra
pintada a mano (no `QGraphicsDropShadowEffect`: ese efecto obliga a re-renderizar toda la tarjeta en cada cuadro de
las animaciones de los gráficos que lleva adentro)."""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget
from PyQt5.QtGui import QColor

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.ui.animaciones import desplegar

COLOR_BORDE = "#eef1f8"
RADIO = 14


def aplicar_sombra(w, blur=18, offset=(0, 2), color=None):
    """Sombra suave para widgets que no son tarjetas (las tarjetas la pintan ellas)."""
    efecto = widget.QGraphicsDropShadowEffect(w)
    efecto.setBlurRadius(blur)
    efecto.setOffset(*offset)
    efecto.setColor(color or QColor(24, 36, 96, 30))
    w.setGraphicsEffect(efecto)


class TarjetaPintada(widget.QFrame):
    """QFrame que pinta su propio fondo redondeado con borde y sombra suave.

    `sombra` es el lugar (px) que se reserva alrededor para que la sombra se vea: el llamador lo suma a los márgenes
    de su layout (`tarjeta.margen_sombra`).
    """

    def __init__(self, sombra=8, radio=RADIO, fondo="#ffffff", borde=COLOR_BORDE, parent=None):
        super().__init__(parent)
        self.margen_sombra = sombra
        self._radio = radio
        self._fondo = QColor(fondo)
        self._borde = QColor(borde)

    def paintEvent(self, _evento):
        p = gui.QPainter(self)
        p.setRenderHint(gui.QPainter.Antialiasing)
        s = self.margen_sombra
        tarjeta = core.QRectF(self.rect()).adjusted(s, s, -s, -s)
        p.setPen(core.Qt.NoPen)
        for k in range(1, s):
            p.setBrush(QColor(24, 36, 96, 3))
            p.drawRoundedRect(tarjeta.adjusted(-k, -k + 3, k, k + 3), self._radio + k, self._radio + k)
        p.setPen(gui.QPen(self._borde, 1))
        p.setBrush(self._fondo)
        p.drawRoundedRect(tarjeta.adjusted(0.5, 0.5, -0.5, -0.5), self._radio, self._radio)


def _marcos(tarjeta, izq, arr, der, aba):
    """Márgenes del contenido de la tarjeta, más el lugar de la sombra."""
    s = tarjeta.margen_sombra
    return izq + s, arr + s, der + s, aba + s


def crear_kpi(titulo, color="#0f172a", icono=None):
    """Tarjeta KPI: título chico en mayúsculas, valor grande y una línea de
    contexto. Devuelve ``(frame, lbl_valor, lbl_sub)``; el llamador actualiza
    los textos con ``setText``. ``icono`` es un QLabel opcional (arriba a la derecha)."""
    frame = TarjetaPintada(sombra=7)
    frame.setObjectName("kpi")

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(*_marcos(frame, 14, 10, 14, 11))
    lay.setSpacing(2)

    fila = widget.QHBoxLayout()
    lbl_titulo = widget.QLabel(titulo.upper())
    lbl_titulo.setStyleSheet("font-size: 10px; font-weight: 700; color: #566377; letter-spacing: 0.5px; background: transparent;")
    fila.addWidget(lbl_titulo)
    fila.addStretch(1)
    if icono is not None:
        fila.addWidget(icono)
    lay.addLayout(fila)

    lbl_valor = widget.QLabel("—")
    lbl_valor.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {color}; background: transparent;")
    lay.addWidget(lbl_valor)

    lbl_sub = widget.QLabel("")
    lbl_sub.setStyleSheet("font-size: 10px; color: #566377; background: transparent;")
    lbl_sub.setWordWrap(True)
    lay.addWidget(lbl_sub)
    return frame, lbl_valor, lbl_sub


class _EncabezadoClicable(widget.QFrame):
    clicked = core.pyqtSignal()

    def mousePressEvent(self, evento):
        if evento.button() == core.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(evento)


def crear_tarjeta_colapsable(titulo, extra=None, icono=None, colapsada=True):
    """Como ``crear_tarjeta`` pero con el encabezado clicable que muestra/oculta el
    cuerpo (la flecha ▸/▾ indica el estado). ``extra`` queda a la derecha y sigue
    visible plegada: sirve para un resumen de lo que hay adentro.

    Devuelve ``(frame, cuerpo_layout, set_colapsada)``.
    """
    frame = TarjetaPintada(sombra=7)
    frame.setObjectName("tarjeta")

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(*_marcos(frame, 14, 8, 14, 9))
    lay.setSpacing(6)

    encabezado = _EncabezadoClicable()
    encabezado.setCursor(core.Qt.PointingHandCursor)
    encabezado.setToolTip("Clic para mostrar u ocultar")
    fila = widget.QHBoxLayout(encabezado)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(6)
    flecha = widget.QLabel()
    flecha.setFixedWidth(12)
    flecha.setStyleSheet("font-size: 12px; color: #64748b; background: transparent;")
    fila.addWidget(flecha)
    if icono is not None:
        fila.addWidget(icono)
    lbl = widget.QLabel(titulo.upper())
    lbl.setObjectName("tarjetaTitulo")
    fila.addWidget(lbl)
    fila.addStretch(1)
    if extra is not None:
        fila.addWidget(extra)
    lay.addWidget(encabezado)

    contenido = widget.QWidget()
    cuerpo = widget.QVBoxLayout(contenido)
    cuerpo.setContentsMargins(0, 0, 0, 0)
    cuerpo.setSpacing(8)
    linea = widget.QFrame()
    linea.setFixedHeight(1)
    linea.setStyleSheet(f"background-color: {COLOR_BORDE};")
    cuerpo.addWidget(linea)
    lay.addWidget(contenido)

    estado = {"colapsada": colapsada}

    def set_colapsada(valor):
        estado["colapsada"] = bool(valor)
        desplegar(contenido, not valor)
        if qta is not None:   # ícono: no depende de que la fuente tenga el glifo ▸/▾
            nombre = "fa5s.chevron-right" if valor else "fa5s.chevron-down"
            flecha.setPixmap(qta.icon(nombre, color="#64748b").pixmap(10, 10))
        else:
            flecha.setText("▸" if valor else "▾")

    encabezado.clicked.connect(lambda: set_colapsada(not estado["colapsada"]))
    set_colapsada(colapsada)
    return frame, cuerpo, set_colapsada


def crear_tarjeta(titulo, extra=None, icono=None):
    """Tarjeta blanca con borde/sombra + fila de encabezado (ícono opcional +
    título en mayúsculas + widget `extra` a la derecha) + separador + cuerpo
    (QVBoxLayout, devuelto para que el llamador agregue su contenido).

    Devuelve ``(frame, cuerpo_layout)``.
    """
    frame = TarjetaPintada(sombra=7)
    frame.setObjectName("tarjeta")

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(*_marcos(frame, 14, 10, 14, 11))
    lay.setSpacing(8)

    header = widget.QHBoxLayout()
    header.setSpacing(6)
    if icono is not None:
        header.addWidget(icono)
    lbl = widget.QLabel(titulo.upper())
    lbl.setObjectName("tarjetaTitulo")
    header.addWidget(lbl)
    header.addStretch(1)
    if extra is not None:
        header.addWidget(extra)
    lay.addLayout(header)

    linea = widget.QFrame()
    linea.setFixedHeight(1)
    linea.setStyleSheet(f"background-color: {COLOR_BORDE};")
    lay.addWidget(linea)

    cuerpo = widget.QVBoxLayout()
    cuerpo.setSpacing(8)
    lay.addLayout(cuerpo)
    return frame, cuerpo
