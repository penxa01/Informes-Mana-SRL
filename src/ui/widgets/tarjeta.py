"""Tarjeta blanca reutilizable: encabezado (ícono + título + extra) + separador
+ cuerpo. Estilo común a las secciones rediseñadas (ver prototypeExample/)."""
import PyQt5.QtWidgets as widget
from PyQt5.QtGui import QColor


def aplicar_sombra(w, blur=14, offset=(0, 1), color=None):
    efecto = widget.QGraphicsDropShadowEffect(w)
    efecto.setBlurRadius(blur)
    efecto.setOffset(*offset)
    efecto.setColor(color or QColor(15, 23, 42, 35))
    w.setGraphicsEffect(efecto)


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
