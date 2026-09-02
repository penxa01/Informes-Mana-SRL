"""Ventana única de la app: navbar de secciones + franja de comandos + stack + status bar.

Ver `guideline/propuesta-ui-integrada.md`.
"""
import os

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

from src.controllers import config
from src.controllers import ProgressBar
from src.Views.Pedidos.programarPedido import DatabaseSyncManager
from src.ui import recursos
from src.ui.registro import PAGINAS
from src.ui.widgets.overlay_carga import OverlayCarga


class AppWindow(widget.QMainWindow):
    #: emitida cuando `fachist` terminó de cargar; las páginas se enganchan a `on_ventas_listas`
    ventas_listas = core.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.df_ventas = None
        self._paginas = []          # instancias, en el orden de PAGINAS
        self._acciones_nav = []     # QAction del navbar, mismo orden

        self.setWindowTitle("Informes Mana S.R.L — Sistema de Gestión")
        self.setWindowIcon(gui.QIcon(recursos.icono("shell.ico")))
        self.setMinimumSize(1024, 680)

        # Sincronización de Pedidos: siempre activa en background (notificaciones
        # aunque estés en otra sección). La comparte la PaginaPedidos.
        self.sync_pedidos = DatabaseSyncManager()

        self._armar_navbar()
        self._armar_barra_comandos()
        self._armar_stack()
        self._armar_status()
        self._cargar_estilos()

        # arranca en la primera sección
        if self._acciones_nav:
            self._acciones_nav[0].setChecked(True)
            self._cambiar_pagina(0)

        self._cargar_ventas()

    # ── construcción ─────────────────────────────────────────────────────────
    def _armar_navbar(self):
        nav = widget.QToolBar("Secciones", self)
        nav.setObjectName("navbar")
        nav.setMovable(False)
        nav.setFloatable(False)
        nav.setToolButtonStyle(core.Qt.ToolButtonTextBesideIcon)
        nav.setIconSize(core.QSize(22, 22))
        self.addToolBar(core.Qt.TopToolBarArea, nav)

        grupo = widget.QActionGroup(self)
        grupo.setExclusive(True)
        for i, pd in enumerate(PAGINAS):
            act = widget.QAction(gui.QIcon(recursos.icono(pd.icono)), pd.titulo, self)
            act.setCheckable(True)
            if pd.atajo:
                act.setShortcut(gui.QKeySequence(pd.atajo))
            act.triggered.connect(lambda _=False, idx=i: self._cambiar_pagina(idx))
            grupo.addAction(act)
            nav.addAction(act)
            self._acciones_nav.append(act)

    def _armar_barra_comandos(self):
        self.barra_comandos = widget.QToolBar("Comandos", self)
        self.barra_comandos.setObjectName("barraComandos")
        self.barra_comandos.setMovable(False)
        self.barra_comandos.setFloatable(False)
        self.addToolBarBreak(core.Qt.TopToolBarArea)
        self.addToolBar(core.Qt.TopToolBarArea, self.barra_comandos)
        self.barra_comandos.hide()

    def _armar_stack(self):
        self.stack = widget.QStackedWidget()
        self.setCentralWidget(self.stack)
        for pd in PAGINAS:
            pagina = pd.factory(self)
            self._paginas.append(pagina)
            self.stack.addWidget(pagina)

        self._overlay = OverlayCarga(self.stack, "Cargando base de ventas…")

    def _armar_status(self):
        self.status = self.statusBar()
        entorno = "LOCAL" if str(config.DB_HOST).lower() in ("localhost", "127.0.0.1") else "RED"
        self._lbl_entorno = widget.QLabel(f"entorno: {entorno}")
        self._lbl_ventas = widget.QLabel("ventas: cargando…")
        self._lbl_version = widget.QLabel("v1.6")
        for w in (self._lbl_entorno, self._lbl_ventas, self._lbl_version):
            self.status.addPermanentWidget(w)

    def _cargar_estilos(self):
        qss = recursos.resource_path(os.path.join("src", "ui", "estilos.qss"))
        try:
            with open(qss, encoding="utf-8") as fh:
                self.setStyleSheet(fh.read())
        except OSError:
            pass

    # ── navegación ───────────────────────────────────────────────────────────
    def _cambiar_pagina(self, idx):
        self.stack.setCurrentIndex(idx)
        pagina = self._paginas[idx]

        # franja de comandos contextual
        self.barra_comandos.clear()
        acciones = list(pagina.acciones_barra() or [])
        for a in acciones:
            self.barra_comandos.addAction(a)
        self.barra_comandos.setVisible(bool(acciones))

        self._actualizar_overlay()
        pagina.on_activar()

    def _actualizar_overlay(self):
        pagina = self._paginas[self.stack.currentIndex()]
        if getattr(pagina, "necesita_ventas", False) and self.df_ventas is None:
            self._overlay.mostrar()
        else:
            self._overlay.ocultar()

    # ── carga de datos ───────────────────────────────────────────────────────
    def _cargar_ventas(self):
        self._hilo_ventas = ProgressBar.LoadDataThread()
        self._hilo_ventas.data_loaded.connect(self._on_ventas_listas)
        self._hilo_ventas.start()

    def _on_ventas_listas(self, df):
        self.df_ventas = df
        try:
            fmin = df["FECHA"].min()
            fmax = df["FECHA"].max()
            self._lbl_ventas.setText(
                f"ventas: {len(df):,} filas · {fmin:%Y}→{fmax:%Y}".replace(",", ".")
            )
        except Exception:
            self._lbl_ventas.setText(f"ventas: {len(df):,} filas")
        for pagina in self._paginas:
            if getattr(pagina, "necesita_ventas", False):
                pagina.on_ventas_listas(df)
        self._actualizar_overlay()
        self.ventas_listas.emit(df)

    # ── helpers para las páginas ─────────────────────────────────────────────
    def recurso(self, relative_path):
        return recursos.resource_path(relative_path)
