"""Ventana única de la app: navbar de secciones + franja de comandos + stack + status bar.

Ver `guideline/propuesta-ui-integrada.md`.
"""
import datetime as dt
import os

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import config
from src.controllers import ProgressBar
from src.controllers import reclamos_db, ventas_io
from src.Views.Pedidos.programarPedido import DatabaseSyncManager
from src.ui import recursos, ventanas
from src.ui.alertas_reclamos import MonitorReclamos
from src.ui.eventos import bus
from src.ui.registro import PAGINAS
from src.ui.widgets.overlay_carga import OverlayCarga


_COLOR_NAV_INACTIVO = "#94a3b8"   # slate-400
_COLOR_NAV_ACTIVO = "#ffffff"


class AppWindow(widget.QMainWindow):
    #: emitida cuando `fachist` terminó de cargar; las páginas se enganchan a `on_ventas_listas`
    ventas_listas = core.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.df_ventas = None
        self._firma_ventas = None   # firma de fachist.DBF en la última carga (ver ventas_io)
        self._hilo_ventas = None
        self._actualizacion_manual = False
        self._paginas = []          # instancias, en el orden de PAGINAS
        self._acciones_nav = []     # QAction del navbar, mismo orden

        self.setWindowTitle("Informes Mana S.R.L — Sistema de Gestión")
        self.setWindowIcon(gui.QIcon(recursos.icono("shell.ico")))
        ventanas.limitar_minimo(self, 1024, 680)     # nunca más grande que la pantalla donde está

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

        # Refresco automático de la base de ventas (cada N minutos). Solo recarga si
        # fachist.DBF cambió; la verificación va en un hilo, no congela la ventana.
        self._timer_ventas = core.QTimer(self)
        self._timer_ventas.setInterval(self._minutos_refresco * 60 * 1000)
        self._timer_ventas.timeout.connect(lambda: self._cargar_ventas(manual=False))
        self._timer_ventas.start()

        self._armar_alertas_reclamos()

    # ── construcción ─────────────────────────────────────────────────────────
    def _armar_navbar(self):
        nav = widget.QToolBar("Secciones", self)
        nav.setObjectName("navbar")
        nav.setMovable(False)
        nav.setFloatable(False)
        nav.setToolButtonStyle(core.Qt.ToolButtonTextBesideIcon)
        nav.setIconSize(core.QSize(22, 22))
        self.addToolBar(core.Qt.TopToolBarArea, nav)

        self._nav_iconos = []   # [(icono_inactivo, icono_activo), ...] mismo orden que _acciones_nav

        grupo = widget.QActionGroup(self)
        grupo.setExclusive(True)
        for i, pd in enumerate(PAGINAS):
            inactivo, activo = self._iconos_pagina(pd)
            act = widget.QAction(inactivo, pd.titulo, self)
            act.setCheckable(True)
            if pd.atajo:
                act.setShortcut(gui.QKeySequence(pd.atajo))
            act.triggered.connect(lambda _=False, idx=i: self._cambiar_pagina(idx))
            grupo.addAction(act)
            nav.addAction(act)
            self._acciones_nav.append(act)
            self._nav_iconos.append((inactivo, activo))

    def _iconos_pagina(self, pd):
        """Par (ícono inactivo, ícono activo) para una sección del navbar."""
        if qta is not None and pd.icono_fa:
            return (qta.icon(pd.icono_fa, color=_COLOR_NAV_INACTIVO),
                    qta.icon(pd.icono_fa, color=_COLOR_NAV_ACTIVO))
        icono = gui.QIcon(recursos.icono(pd.icono))
        return icono, icono

    def _armar_barra_comandos(self):
        self.barra_comandos = widget.QToolBar("Comandos", self)
        self.barra_comandos.setObjectName("barraComandos")
        self.barra_comandos.setMovable(False)
        self.barra_comandos.setFloatable(False)
        self.addToolBarBreak(core.Qt.TopToolBarArea)
        self.addToolBar(core.Qt.TopToolBarArea, self.barra_comandos)
        self.barra_comandos.hide()

        # Acción global: se agrega sola a las secciones que usan la base de ventas.
        self._minutos_refresco = ventas_io.minutos_refresco(os.getenv("VENTAS_ACTUALIZAR_MIN"))
        icono = qta.icon("fa5s.sync-alt", color="#2563eb") if qta is not None else gui.QIcon()
        self.accion_actualizar_ventas = widget.QAction(icono, "Actualizar ventas", self)
        self.accion_actualizar_ventas.setShortcut(gui.QKeySequence("F5"))
        self.accion_actualizar_ventas.setToolTip(
            f"Vuelve a leer la base de ventas (F5). Se actualiza sola cada {self._minutos_refresco} minutos.")
        self.accion_actualizar_ventas.triggered.connect(lambda: self._cargar_ventas(manual=True))
        # Colgada de la ventana para que F5 funcione aunque la acción no esté en ninguna barra
        # (las páginas con su propio botón no la muestran arriba).
        self.addAction(self.accion_actualizar_ventas)

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
        self._lbl_entorno = widget.QLabel(f"datos: {config.ENTORNO or 'SIN DATOS'}")
        self._lbl_entorno.setToolTip(f"Carpeta de datos: {config.BASE_DATOS}\nBase de datos (Pedidos): {config.DB_HOST}")
        self._lbl_ventas = widget.QLabel("ventas: cargando…")
        self._lbl_version = widget.QLabel("v1.6")

        # Alerta de reclamos sin novedades: oculta mientras no haya ninguno; clic = ir a los reclamos.
        self._btn_reclamos = widget.QPushButton()
        self._btn_reclamos.setCursor(core.Qt.PointingHandCursor)
        self._btn_reclamos.setStyleSheet(
            "QPushButton { color: #92400e; background-color: #fef3c7; border: 1px solid #fcd34d; border-radius: 4px;"
            " padding: 1px 8px; font-size: 11px; font-weight: 700; }"
            "QPushButton:hover { background-color: #fde68a; }")
        if qta is not None:
            self._btn_reclamos.setIcon(qta.icon("fa5s.exclamation-triangle", color="#d97706"))
        self._btn_reclamos.clicked.connect(self._ir_a_reclamos)
        self._btn_reclamos.hide()

        for w in (self._btn_reclamos, self._lbl_entorno, self._lbl_ventas, self._lbl_version):
            self.status.addPermanentWidget(w)

    # ── alertas de reclamos ──────────────────────────────────────────────────
    def _armar_alertas_reclamos(self):
        """Vigila los reclamos que llevan mucho sin actualizarse (ver ``reclamos_db.sin_novedades``)."""
        self._ids_avisados = set()          # los que ya se avisaron con el aviso emergente en esta sesión
        self._monitor_reclamos = MonitorReclamos(self)
        self._monitor_reclamos.cambio.connect(self._on_reclamos_vencidos)
        # Al crear / cambiar de estado / marcar como revisado un reclamo se vuelve a chequear al toque.
        bus.reclamos_modificados.connect(self._monitor_reclamos.comprobar)
        self._monitor_reclamos.iniciar()

    def _on_reclamos_vencidos(self, vencidos):
        n = len(vencidos)
        if n == 0:
            self._btn_reclamos.hide()
            self._ids_avisados.clear()
            return
        self._btn_reclamos.setText(f"{n} reclamo{'s' if n != 1 else ''} sin novedades")
        detalle = "\n".join(f"#{r.id_reclamo} {r.cliente} — {r.dias_sin_novedad} días ({r.estado})"
                            for r in vencidos.head(8).itertuples())
        self._btn_reclamos.setToolTip(f"Llevan {self._monitor_reclamos.dias} días o más sin actualizar su estado:\n{detalle}"
                                      + (f"\n… y {n - 8} más" if n > 8 else "") + "\n\nClic para abrir los reclamos.")
        self._btn_reclamos.show()

        # Aviso emergente solo de los que todavía no se avisaron (no repetirlo cada 30 minutos).
        # Los que dejan de estar en alerta se olvidan: si vuelven a vencer, se avisa de nuevo.
        ids = {int(i) for i in vencidos["id_reclamo"]}
        nuevos = vencidos[~vencidos["id_reclamo"].isin(self._ids_avisados)]
        self._ids_avisados = ids
        aviso = reclamos_db.texto_alerta(nuevos, self._monitor_reclamos.dias)
        if aviso is not None:
            self.sync_pedidos.notification_manager.show_notification(aviso[0], aviso[1], "warning", 10000)

    def _ir_a_reclamos(self):
        """Lleva a Cuentas Corrientes y abre el modal de reclamos."""
        ids = [p.id for p in PAGINAS]
        if "cuentas" not in ids:
            return
        idx = ids.index("cuentas")
        self._acciones_nav[idx].setChecked(True)
        self._cambiar_pagina(idx)
        self._paginas[idx].abrir_reclamos()

    def _cargar_estilos(self):
        qss = recursos.resource_path(os.path.join("src", "ui", "estilos.qss"))
        try:
            with open(qss, encoding="utf-8") as fh:
                self.setStyleSheet(fh.read())
        except OSError:
            pass

    # ── navegación ───────────────────────────────────────────────────────────
    def _cambiar_pagina(self, idx):
        for i, (inactivo, activo) in enumerate(self._nav_iconos):
            self._acciones_nav[i].setIcon(activo if i == idx else inactivo)

        self.stack.setCurrentIndex(idx)
        pagina = self._paginas[idx]

        # franja de comandos contextual
        self.barra_comandos.clear()
        acciones = list(pagina.acciones_barra() or [])
        if getattr(pagina, "necesita_ventas", False) and not getattr(pagina, "tiene_boton_actualizar", False):
            acciones.append(self.accion_actualizar_ventas)
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
    def _cargar_ventas(self, manual=False):
        """Carga (arranque) o actualiza la base de ventas en segundo plano.

        Si ya hay una carga en curso no hace nada. Solo relee el DBF si cambió desde
        la última carga; ``manual`` (botón / F5) solo cambia cuánto se le avisa al usuario.
        """
        if self._hilo_ventas is not None and self._hilo_ventas.isRunning():
            if manual:
                self.status.showMessage("Ya se está actualizando la base de ventas…", 4000)
            return
        self._actualizacion_manual = manual
        hilo = ProgressBar.LoadDataThread(self._firma_ventas)
        hilo.data_loaded.connect(self._on_ventas_listas)
        hilo.sin_cambios.connect(self._on_ventas_sin_cambios)
        hilo.fallo.connect(self._on_ventas_error)
        hilo.finished.connect(self._on_hilo_ventas_terminado)
        self._hilo_ventas = hilo
        self.accion_actualizar_ventas.setEnabled(False)
        if manual:
            self.status.showMessage("Actualizando la base de ventas…")
        hilo.start()

    def _on_hilo_ventas_terminado(self):
        self.accion_actualizar_ventas.setEnabled(True)

    def _marcar_ventas_al_dia(self):
        self._lbl_ventas.setText(ventas_io.texto_estado_ventas(self.df_ventas, dt.datetime.now()))
        self._lbl_ventas.setToolTip("La hora indica la última vez que se verificó la base de ventas.")

    def _on_ventas_listas(self, df):
        primera_carga = self.df_ventas is None
        self.df_ventas = df
        self._firma_ventas = self._hilo_ventas.firma
        self._marcar_ventas_al_dia()
        if not primera_carga:   # antes de avisar a las páginas: ellas pueden pisar este mensaje con el suyo
            self.status.showMessage(f"Ventas actualizadas: {len(df):,} filas.".replace(",", "."), 6000)
        for pagina in self._paginas:
            if getattr(pagina, "necesita_ventas", False):
                pagina.on_ventas_listas(df)
        self._actualizar_overlay()
        self.ventas_listas.emit(df)

    def _on_ventas_sin_cambios(self):
        self._marcar_ventas_al_dia()
        if self._actualizacion_manual:
            self.status.showMessage("La base de ventas ya está al día: no hay datos nuevos.", 6000)

    def _on_ventas_error(self, mensaje):
        """No se pudo leer la base. Se conservan los datos que ya había (si los hay)."""
        if self.df_ventas is None:          # ni siquiera pudo cargar al arrancar
            self._overlay.ocultar()
            widget.QMessageBox.critical(
                self, "Base de ventas",
                f"No se pudo cargar la base de ventas:\n{mensaje}\n\n"
                "Verificá la conexión con el servidor y volvé a intentar (F5).")
            return
        self._lbl_ventas.setToolTip(f"No se pudo actualizar: {mensaje}")
        self.status.showMessage("No se pudo actualizar la base de ventas; se siguen mostrando los datos anteriores.", 8000)
        if self._actualizacion_manual:
            widget.QMessageBox.warning(
                self, "Base de ventas",
                f"No se pudo actualizar la base de ventas:\n{mensaje}\n\nSe siguen usando los datos anteriores.")

    def closeEvent(self, evento):
        if self._hilo_ventas is not None and self._hilo_ventas.isRunning():
            self._hilo_ventas.wait(5000)     # no destruir el hilo en plena lectura
        self._monitor_reclamos.esperar()
        super().closeEvent(evento)

    # ── helpers para las páginas ─────────────────────────────────────────────
    def recurso(self, relative_path):
        return recursos.resource_path(relative_path)
