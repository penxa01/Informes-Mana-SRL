"""Sección INICIO — el panel de control del celular, en el escritorio, más el desglose de litros.

Tres pestañas: General (litros del mes, % premium y recaudado de la semana), Desglose de litros (el informe por producto
con sus filtros, ver `panel_litros.py`) y Cobranzas (ver `panel_cobranzas.py`, con el acceso a los Reclamos).
Los números de General y Cobranzas los calcula el servidor y quedan en Postgres (ver `controllers/panel_io.py`): acá solo
se leen y se dibujan. Se actualizan solos cada 2 minutos y con el botón ↻.
"""
import calendar
import json
from datetime import timedelta

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import panel_io
from src.controllers import panel_vista as pv
from src.ui.paginas.base import PaginaBase
from src.ui.paginas.panel_cobranzas import VistaCobranzas
from src.ui.paginas.panel_litros import VistaLitros
from src.ui.widgets.graficos import Anillo, GraficoBarras
from src.ui.widgets.panel_piezas import (
    CifraAnimada, ChipDelta, PestanasPildora, TarjetaPanel, etiqueta, fila_izquierda, leyenda, nota,
    seccion_desglose, vaciar)
from src.ui.reclamos_acceso import AccesoReclamos
from src.ui.widgets.spinner import Spinner

INTERVALO_MS = 120000
_COLOR_ICONO = "#2640dc"
_CLAVE_FILTRO = "panel/proveedores"


class _Lectura(core.QThread):
    """Lee una sección del panel en segundo plano (la base está en el servidor)."""
    listo = core.pyqtSignal(str, object)       # sección, respuesta
    fallo = core.pyqtSignal(str, str, bool)    # sección, mensaje, ¿es un problema de conexión?

    def __init__(self, seccion, parent=None):
        super().__init__(parent)
        self.seccion = seccion

    def run(self):
        try:
            self.listo.emit(self.seccion, panel_io.leer(self.seccion))
        except panel_io.PanelNoDisponible as e:
            self.fallo.emit(self.seccion, str(e), False)
        except Exception as e:   # sin red, base caída, etc.
            self.fallo.emit(self.seccion, f"No se pudo leer el panel del servidor: {e}", True)


class _EstadoCarga(widget.QWidget):
    """Lo que se ve mientras no hay datos: un spinner con «Cargando…» o el motivo por el que no se pudo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = widget.QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addStretch(1)
        self._spinner = Spinner(self)
        self._texto = etiqueta("Cargando el panel…", "overlayCargaLabel")
        self._texto.setAlignment(core.Qt.AlignCenter)
        self._texto.setWordWrap(True)
        lay.addWidget(self._spinner, 0, core.Qt.AlignCenter)
        lay.addWidget(self._texto, 0, core.Qt.AlignCenter)
        lay.addStretch(2)

    def cargando(self):
        self._spinner.show()
        self._texto.setText("Cargando el panel…")

    def error(self, mensaje):
        self._spinner.hide()
        self._texto.setText(mensaje + "\n\nTocá ↻ para reintentar.")


def _en_columna(vista, ancho_max=1200):
    """Scroll vertical con `vista` centrada y con un ancho máximo (en pantallas grandes no se estira de más)."""
    scroll = widget.QScrollArea()
    scroll.setObjectName("panelScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(widget.QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(core.Qt.ScrollBarAlwaysOff)
    cont = widget.QWidget()
    lay = widget.QHBoxLayout(cont)
    lay.setContentsMargins(20, 6, 20, 24)
    vista.setMaximumWidth(ancho_max)
    lay.addStretch(1)
    lay.addWidget(vista, 1000, core.Qt.AlignTop)
    lay.addStretch(1)
    scroll.setWidget(cont)
    return scroll


# ── General ──────────────────────────────────────────────────────────────────
class VistaGeneral(widget.QWidget):
    """Filtro de productos + tarjetas de litros, premium y recaudado de la semana."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ajustes = core.QSettings("ManaSRL", "InformesMana")
        guardado = self._ajustes.value(_CLAVE_FILTRO, "", type=str)
        self._filtro = pv.FiltroProveedores([c for c in guardado.split(",") if c])
        self._datos = None
        self._firma = None

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._barra_filtro = widget.QWidget()
        fila = widget.QHBoxLayout(self._barra_filtro)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)
        fila.addWidget(etiqueta("Productos", "panelFiltroTitulo"))
        self._chips = {}
        for clave, nombre in [("TODOS", "Todos")] + pv.PROVEEDORES:
            b = widget.QPushButton(nombre)
            b.setObjectName("chipFiltro")
            b.setCheckable(True)
            b.setCursor(core.Qt.PointingHandCursor)
            b.setFocusPolicy(core.Qt.NoFocus)
            b.clicked.connect(lambda _=False, c=clave: self._al_elegir(c))
            fila.addWidget(b)
            self._chips[clave] = b
        fila.addStretch(1)
        lay.addWidget(self._barra_filtro)

        self._grilla = widget.QGridLayout()
        self._grilla.setHorizontalSpacing(6)
        self._grilla.setVerticalSpacing(6)
        self._grilla.setColumnStretch(0, 1)
        self._grilla.setColumnStretch(1, 1)
        lay.addLayout(self._grilla)
        lay.addStretch(1)

    def _al_elegir(self, clave):
        if clave == "TODOS":
            self._filtro.todos()
        else:
            self._filtro.alternar(clave)
        self._ajustes.setValue(_CLAVE_FILTRO, ",".join(sorted(self._filtro.seleccion)))
        self._redibujar()

    def actualizar(self, datos):
        self._datos = datos
        self._redibujar()

    def _redibujar(self):
        if self._datos is None:
            return
        vista = pv.vista_litros(self._datos, self._filtro)
        # Los chips siempre reflejan la selección; las tarjetas se vuelven a armar solo si algo cambió.
        self._barra_filtro.setVisible(vista["con_desglose"])
        self._chips["TODOS"].setChecked(self._filtro.estan_todos())
        for clave, _ in pv.PROVEEDORES:
            self._chips[clave].setChecked(self._filtro.activo(clave))
        firma = json.dumps([self._datos, self._filtro.firma()], sort_keys=True, default=str)
        if firma == self._firma:
            return
        self._firma = firma
        vaciar(self._grilla)
        self._grilla.addWidget(self._tarjeta_litros(self._datos, vista), 0, 0, 1, 2)
        self._grilla.addWidget(self._tarjeta_premium(self._datos, vista), 1, 0, core.Qt.AlignTop)
        self._grilla.addWidget(self._tarjeta_recaudado(self._datos), 1, 1, core.Qt.AlignTop)

    # ── Litros del mes ───────────────────────────────────────────────────────
    def _tarjeta_litros(self, datos, vista):
        per = datos["periodos"]
        desde, hasta = pv.fecha_corta(per["mes"]["desde"]), pv.fecha_corta(per["mes"]["hasta"])
        sub = f"{pv.MESES[desde.month - 1]} · al {hasta.day}" + (f" · {vista['etiqueta']}" if vista["etiqueta"] else "")
        t = TarjetaPanel("Litros vendidos", sub)
        t.agregar(CifraAnimada(vista["litros"], pv.numero, "L"))
        ant_desde = pv.fecha_corta(per["mes_anterior"]["desde"])
        ant_hasta = pv.fecha_corta(per["mes_anterior"]["hasta"])
        t.agregar(fila_izquierda(ChipDelta(vista["litros"], vista["litros_ant"],
                                           f"vs {pv.MESES[ant_desde.month - 1]} al {ant_hasta.day}")))

        # una columna por día del mes: lo premium abajo (ámbar) y el resto arriba (azul)
        por_fecha = {d["fecha"]: d for d in vista["por_dia"]}
        dias_del_mes = calendar.monthrange(desde.year, desde.month)[1]
        barras = []
        for dia in range(1, dias_del_mes + 1):
            d = por_fecha.get(f"{desde.year}-{desde.month:02d}-{dia:02d}")
            premium = max(0.0, d["premium"]) if d else 0.0
            resto = max(0.0, d["litros"] - d["premium"]) if d else 0.0
            if d:
                extra = f" ({pv.numero(d['premium'])} premium)" if vista["incluye_shell"] else ""
                titulo = f"Día {dia}: {pv.numero(d['litros'])} L{extra}"
            else:
                titulo = f"Día {dia}: sin ventas"
            barras.append({
                "etiqueta": str(dia) if dia == 1 or dia % 5 == 0 else None,
                "partes": [(premium, pv.COLORES["ambar"]), (resto, pv.COLORES["azul"])],
                "titulo": titulo,
                "tenue": dia > hasta.day,
            })
        t.agregar(GraficoBarras(barras, alto=160))
        t.agregar(leyenda([(pv.COLORES["ambar"], "Premium"), (pv.COLORES["azul"], "Resto")] if vista["incluye_shell"]
                          else [(pv.COLORES["azul"], "Litros")]))
        return t

    # ── Premium ──────────────────────────────────────────────────────────────
    def _tarjeta_premium(self, datos, vista):
        mes_ant = pv.MESES[pv.fecha_corta(datos["periodos"]["mes_anterior"]["desde"]).month - 1]
        t = TarjetaPanel("Premium", f"sobre los litros de {vista['etiqueta']}" if vista["etiqueta"] else "sobre el total de litros")
        cuerpo = widget.QHBoxLayout()
        cuerpo.setSpacing(22)
        cuerpo.setContentsMargins(0, 10, 0, 4)
        cuerpo.addWidget(Anillo(vista["pct"], pv.COLORES["ambar"], f"{pv.numero(vista['pct'], 1)} %"))
        datos_lado = widget.QVBoxLayout()
        datos_lado.setSpacing(4)
        datos_lado.addStretch(1)
        for valor, texto in ((vista["premium"], "premium"), (vista["litros"] - vista["premium"], "resto")):
            lbl = etiqueta(f"<b style='color:#0f172a; font-size:16px'>{pv.numero(valor)} L</b> {texto}", "panelDato")
            lbl.setTextFormat(core.Qt.RichText)
            datos_lado.addWidget(lbl)
        # Sin Shell no hay premium que comparar: el chip diría «sin dato anterior» y confundiría.
        if vista["incluye_shell"]:
            datos_lado.addSpacing(4)
            datos_lado.addLayout(fila_izquierda(ChipDelta(vista["pct"], vista["pct_ant"], f"vs {mes_ant}", puntos=True)))
        datos_lado.addStretch(1)
        cuerpo.addLayout(datos_lado, 1)
        t.agregar(cuerpo)
        if not vista["incluye_shell"]:
            t.agregar(nota("Premium es solo de Shell: esta selección no lo incluye."))
        return t

    # ── Recaudado de la semana ───────────────────────────────────────────────
    def _tarjeta_recaudado(self, datos):
        sem = datos["recaudado"]["semana"]
        ant = datos["recaudado"]["semana_anterior"]
        lunes = pv.fecha_corta(datos["periodos"]["semana"]["desde"])
        hoy = pv.fecha_corta(datos["periodos"]["semana"]["hasta"])
        t = TarjetaPanel("Recaudado", f"{pv.dia_corto(lunes)} al {pv.dia_corto(hoy)}")
        t.agregar(CifraAnimada(sem["total"], pv.dinero))
        t.agregar(nota(f"$ {pv.numero(sem['total'])} · {pv.plural(sem['recibos'], 'recibo', 'recibos')}"))
        t.agregar(fila_izquierda(ChipDelta(sem["total"], ant["total"], "vs semana anterior al mismo día")))

        por_fecha = {d["fecha"]: d["monto"] for d in sem["por_dia"]}
        barras = []
        for i, letra in enumerate("LMMJVSD"):
            dia = lunes + timedelta(days=i)
            monto = por_fecha.get(dia.isoformat(), 0)
            futuro = dia > hoy
            barras.append({
                "etiqueta": letra,
                "partes": [(monto, pv.COLORES["verde"])],
                "valor_visible": pv.numero(monto / 1e6, 1) if monto > 0 else None,
                "titulo": f"{pv.dia_corto(dia)}: todavía no" if futuro else f"{pv.dia_corto(dia)}: $ {pv.numero(monto)}",
                "tenue": futuro,
            })
        t.agregar(GraficoBarras(barras, alto=140))
        t.agregar(nota("Por día, en millones de $"))
        # Un servidor que todavía manda el formato anterior (sin desglose) simplemente no muestra esta parte.
        if sem.get("desglose"):
            t.agregar(seccion_desglose(sem["desglose"]))
        return t


# ── La página ────────────────────────────────────────────────────────────────
class PaginaInicio(PaginaBase):
    #: la pestaña Desglose de litros necesita la base de ventas, pero General y Cobranzas no: no se tapa toda la página
    #: con «Cargando…», solo esa pestaña (VistaLitros trae su propio aviso).
    recibe_ventas = True
    SECCIONES = ("general", "litros", "cobranzas")

    def __init__(self, app):
        super().__init__(app)
        self._seccion = "general"
        self._respuestas = {"general": None, "cobranzas": None}
        self._sin_conexion = {"general": False, "cobranzas": False}
        self._hilos = {}
        self._reclamos = AccesoReclamos(app, self)

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(22, 12, 22, 0)
        lay.setSpacing(8)

        # Una sola fila arriba: las pestañas a la izquierda y, a la derecha, de cuándo son los datos + actualizar.
        self._pestanas = PestanasPildora(["General", "Desglose de litros", "Cobranzas"])
        self._pestanas.cambio.connect(self._cambiar_seccion)
        fila_pestanas = widget.QHBoxLayout()
        fila_pestanas.setSpacing(10)
        fila_pestanas.addWidget(self._pestanas)
        fila_pestanas.addStretch(1)
        self._lbl_actualizado = etiqueta("", "panelActualizado")
        fila_pestanas.addWidget(self._lbl_actualizado)
        self._btn = widget.QToolButton()
        self._btn.setObjectName("panelActualizar")
        self._btn.setFixedSize(36, 36)
        self._btn.setCursor(core.Qt.PointingHandCursor)
        self._btn.setToolTip("Actualizar ahora (se actualiza solo cada 2 minutos)")
        self._btn.setIconSize(core.QSize(16, 16))
        self._spinner_btn = Spinner(self._btn, diametro=18, grosor=2)
        self._spinner_btn.move(9, 9)
        self._spinner_btn.hide()
        self._poner_icono_reposo()
        self._btn.clicked.connect(self._actualizar_ahora)
        fila_pestanas.addWidget(self._btn)
        lay.addLayout(fila_pestanas)

        self._aviso = etiqueta("", "panelAviso")
        self._aviso.setWordWrap(True)
        self._aviso.hide()
        lay.addWidget(self._aviso)

        self._vistas = {"general": VistaGeneral(), "cobranzas": VistaCobranzas()}
        self._vistas["cobranzas"].reclamos_solicitado.connect(self.abrir_reclamos)
        self._estados = {"general": _EstadoCarga(), "cobranzas": _EstadoCarga()}
        self._pilas = {}
        self._litros = VistaLitros(app)
        self._cuerpo = widget.QStackedWidget()
        for seccion in self.SECCIONES:
            if seccion == "litros":
                self._cuerpo.addWidget(self._litros)
                continue
            pila = widget.QStackedWidget()
            pila.addWidget(self._estados[seccion])                    # 0: cargando / error
            pila.addWidget(_en_columna(self._vistas[seccion]))        # 1: los datos
            self._pilas[seccion] = pila
            self._cuerpo.addWidget(pila)
        lay.addWidget(self._cuerpo, 1)

        self._timer = core.QTimer(self)
        self._timer.setInterval(INTERVALO_MS)
        self._timer.timeout.connect(self._refresco_automatico)
        self._timer.start()

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def on_activar(self):
        if self._seccion == "litros":
            self._litros.on_activar()
        else:
            self._cargar(self._seccion)

    def on_ventas_listas(self, df):
        self._litros.on_ventas_listas(df)

    def al_cerrar(self):
        self._timer.stop()
        self._reclamos.esperar()
        for hilo in self._hilos.values():
            hilo.wait(8000)

    def _refresco_automatico(self):
        if self.isVisible() and self._seccion != "litros":
            self._cargar(self._seccion)

    def _actualizar_ahora(self):
        if self._seccion != "litros":
            self._cargar(self._seccion)

    # ── reclamos ─────────────────────────────────────────────────────────────
    def abrir_reclamos(self, cuenta=None):
        """Abre el modal de reclamos (con `cuenta` preseleccionada si viene). Lo usa el botón de Cobranzas y la alerta de
        la barra de estado, que antes de abrir lleva a la pestaña Cobranzas."""
        if self._seccion != "cobranzas":
            self._pestanas.elegir(2)
        self._reclamos.abrir(cuenta)

    # ── pestañas ─────────────────────────────────────────────────────────────
    def _cambiar_seccion(self, idx):
        self._seccion = self.SECCIONES[idx]
        self._cuerpo.setCurrentIndex(idx)
        # El desglose de litros no usa el panel del servidor: no hay «Datos de las…» ni ↻ (tiene su propio actualizar).
        self._btn.setVisible(self._seccion != "litros")
        self._pintar_encabezado()
        self.on_activar()

    # ── carga ────────────────────────────────────────────────────────────────
    def _poner_icono_reposo(self):
        if qta is not None:
            self._btn.setIcon(qta.icon("fa5s.sync-alt", color=_COLOR_ICONO))
        else:
            self._btn.setText("↻")

    def _girar_boton(self, girando):
        # Mientras carga, el ícono se reemplaza por el spinner propio (no por `qta.Spin`).
        self._btn.setEnabled(not girando)
        self._spinner_btn.setVisible(girando)
        self._btn.setIcon(gui.QIcon()) if girando else self._poner_icono_reposo()

    def _cargar(self, seccion):
        hilo = self._hilos.get(seccion)
        if hilo is not None and hilo.isRunning():
            return
        if self._respuestas[seccion] is None:
            self._estados[seccion].cargando()
        hilo = _Lectura(seccion, self)
        # métodos y no lambdas: así Qt corta la conexión sola si la página se destruye antes de que el hilo termine
        hilo.listo.connect(self._al_llegar)
        hilo.fallo.connect(self._al_fallar)
        hilo.finished.connect(self._al_terminar_hilo)
        self._hilos[seccion] = hilo
        self._girar_boton(True)
        hilo.start()

    def _al_terminar_hilo(self):
        if not any(h.isRunning() for h in self._hilos.values()):
            self._girar_boton(False)

    def _al_llegar(self, seccion, respuesta):
        self._respuestas[seccion] = respuesta
        self._sin_conexion[seccion] = False
        self._vistas[seccion].actualizar(respuesta["datos"])
        self._pilas[seccion].setCurrentIndex(1)
        if seccion == self._seccion:
            self._pintar_encabezado()

    def _al_fallar(self, seccion, mensaje, conexion):
        if self._respuestas[seccion] is None:
            self._estados[seccion].error(mensaje)
            return
        self._sin_conexion[seccion] = True    # se siguen viendo los últimos datos
        if seccion == self._seccion:
            self._pintar_encabezado()

    def _pintar_encabezado(self):
        resp = self._respuestas.get(self._seccion)
        if resp is None:
            self._lbl_actualizado.setText("")
            self._aviso.hide()
            return
        self._lbl_actualizado.setText(pv.texto_actualizado(resp["calculado_en"]))
        avisos = pv.avisos(resp, self._sin_conexion[self._seccion])
        self._aviso.setText("  ".join(avisos))
        self._aviso.setVisible(bool(avisos))
