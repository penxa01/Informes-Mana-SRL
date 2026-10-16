"""Tarjeta blanca reutilizable: encabezado (ícono + título + extra) + separador
+ cuerpo. Estilo común a las secciones rediseñadas (ver prototypeExample/)."""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget
from PyQt5.QtGui import QColor

try:
    import qtawesome as qta
except ImportError:
    qta = None


def aplicar_sombra(w, blur=14, offset=(0, 1), color=None):
    efecto = widget.QGraphicsDropShadowEffect(w)
    efecto.setBlurRadius(blur)
    efecto.setOffset(*offset)
    efecto.setColor(color or QColor(15, 23, 42, 35))
    w.setGraphicsEffect(efecto)


def crear_kpi(titulo, color="#0f172a", icono=None):
    """Tarjeta KPI: título chico en mayúsculas, valor grande y una línea de
    contexto. Devuelve ``(frame, lbl_valor, lbl_sub)``; el llamador actualiza
    los textos con ``setText``. ``icono`` es un QLabel opcional (arriba a la derecha)."""
    frame = widget.QFrame()
    frame.setObjectName("kpi")
    frame.setStyleSheet(
        "#kpi { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }"
    )
    aplicar_sombra(frame)

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(12, 9, 12, 10)
    lay.setSpacing(2)

    fila = widget.QHBoxLayout()
    lbl_titulo = widget.QLabel(titulo.upper())
    lbl_titulo.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
    fila.addWidget(lbl_titulo)
    fila.addStretch(1)
    if icono is not None:
        fila.addWidget(icono)
    lay.addLayout(fila)

    lbl_valor = widget.QLabel("—")
    lbl_valor.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")
    lay.addWidget(lbl_valor)

    lbl_sub = widget.QLabel("")
    lbl_sub.setStyleSheet("font-size: 10px; color: #94a3b8;")
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
    frame = widget.QFrame()
    frame.setObjectName("tarjeta")
    frame.setStyleSheet(
        "#tarjeta { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }"
    )
    aplicar_sombra(frame)

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(12, 7, 12, 8)
    lay.setSpacing(6)

    encabezado = _EncabezadoClicable()
    encabezado.setCursor(core.Qt.PointingHandCursor)
    encabezado.setToolTip("Clic para mostrar u ocultar")
    fila = widget.QHBoxLayout(encabezado)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(6)
    flecha = widget.QLabel()
    flecha.setFixedWidth(12)
    flecha.setStyleSheet("font-size: 12px; color: #64748b;")
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
    linea.setFrameShape(widget.QFrame.HLine)
    linea.setStyleSheet("color: #f1f5f9; max-height: 1px;")
    cuerpo.addWidget(linea)
    lay.addWidget(contenido)

    estado = {"colapsada": colapsada}

    def set_colapsada(valor):
        estado["colapsada"] = bool(valor)
        contenido.setVisible(not valor)
        if qta is not None:   # ícono: no depende de que la fuente tenga el glifo ▸/▾
            nombre = "fa5s.chevron-right" if valor else "fa5s.chevron-down"
            flecha.setPixmap(qta.icon(nombre, color="#64748b").pixmap(10, 10))
        else:
            flecha.setText("▸" if valor else "▾")

    encabezado.clicked.connect(lambda: set_colapsada(not estado["colapsada"]))
    set_colapsada(colapsada)
    return frame, cuerpo, set_colapsada


def crear_tarjeta(titulo, extra=None, icono=None):
    """QFrame blanco con borde/sombra + fila de encabezado (ícono opcional +
    título en mayúsculas + widget `extra` a la derecha) + separador + cuerpo
    (QVBoxLayout, devuelto para que el llamador agregue su contenido).

    Devuelve ``(frame, cuerpo_layout)``.
    """
    frame = widget.QFrame()
    frame.setObjectName("tarjeta")
    frame.setStyleSheet(
        "#tarjeta { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }"
    )
    aplicar_sombra(frame)

    lay = widget.QVBoxLayout(frame)
    lay.setContentsMargins(12, 9, 12, 10)
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
    linea.setFrameShape(widget.QFrame.HLine)
    linea.setStyleSheet("color: #f1f5f9; max-height: 1px;")
    lay.addWidget(linea)

    cuerpo = widget.QVBoxLayout()
    cuerpo.setSpacing(8)
    lay.addLayout(cuerpo)
    return frame, cuerpo
