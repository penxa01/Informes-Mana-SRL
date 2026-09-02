"""Punto de entrada de la app (UI integrada — ver guideline/propuesta-ui-integrada.md).

El modelo viejo (9 ventanas separadas) quedó en `main_legacy.py` hasta F3.
"""
import sys

import PyQt5.QtWidgets as widget
import PyQt5.QtGui as gui

from src.ui.app_window import AppWindow
from src.ui import recursos

# -------------------------------------------------
# __author__ = "Juan Ignacio Peña Seva"
# __version__ = "1.6.0"
# -------------------------------------------------


def main():
    app = widget.QApplication(sys.argv)
    app.setWindowIcon(gui.QIcon(recursos.icono("shell.ico")))
    ventana = AppWindow()
    ventana.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
