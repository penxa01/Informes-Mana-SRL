"""Indicadores visuales compactos reutilizables (ver prototypeExample/).

`barra_porcentaje` devuelve un mini-widget "barra + valor" para meter en una
celda de tabla (`setCellWidget`), con color por umbral igual a los filtros
rápidos de Margen (>25 verde / 20-25 ámbar / <20 rojo)."""
import math

import PyQt5.QtWidgets as widget

_VERDE = "#059669"
_AMBAR = "#d97706"
_ROJO = "#e11d48"


def _sanear(pct):
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(pct):
        return 0.0
    if math.isinf(pct):
        return 999.0 if pct > 0 else -999.0
    return pct


def color_margen(pct, alto=25.0, bajo=20.0):
    pct = _sanear(pct)
    if pct >= alto:
        return _VERDE
    if pct >= bajo:
        return _AMBAR
    return _ROJO


def _fmt_pct(pct):
    if abs(pct) >= 999:
        return "∞%" if pct > 0 else "-∞%"
    return f"{pct:.2f}%".replace(".", ",")


def barra_porcentaje(pct, alto=25.0, bajo=20.0):
    """QWidget con una barra fina (0-100) + el valor, centrados. Pensado para
    `tabla.setCellWidget(fila, col, barra_porcentaje(pct))`."""
    pct = _sanear(pct)
    color = color_margen(pct, alto, bajo)

    cont = widget.QWidget()
    cont.setStyleSheet("background: transparent;")
    lay = widget.QHBoxLayout(cont)
    lay.setContentsMargins(6, 0, 6, 0)
    lay.setSpacing(6)

    barra = widget.QProgressBar()
    barra.setTextVisible(False)
    barra.setFixedSize(46, 6)
    barra.setRange(0, 100)
    barra.setValue(max(0, min(100, int(round(pct)))))
    barra.setStyleSheet(
        "QProgressBar { background-color: #e2e8f0; border: none; border-radius: 3px; }"
        f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
    )

    etiqueta = widget.QLabel(_fmt_pct(pct))
    etiqueta.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 11px; background: transparent;")

    lay.addStretch(1)
    lay.addWidget(barra)
    lay.addWidget(etiqueta)
    lay.addStretch(1)
    return cont
