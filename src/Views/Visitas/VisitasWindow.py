"""Visitas: registro de visitas de los vendedores (planilla de Google Sheets, lectura en vivo)."""
import datetime as dt

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import visitas_io as vio
from src.ui.widgets.boton_cuadrado import boton_cuadrado
from src.ui.widgets.item_ordenable import ItemOrdenable
from src.ui.widgets.tarjeta import crear_tarjeta, crear_tarjeta_colapsable

_COLUMNAS = ["Fecha", "Hora", "Vendedor", "Cliente", "Nuevo", "Compró", "Observación"]
_RELEER_SI_PASARON_SEG = 120      # al volver a la pestaña se relee si la última lectura es más vieja que esto

# valor -> (fondo, texto, negrita)
_COLOR_SI_NO = {
    "NUEVO": {"Sí": ("#dbeafe", "#1e40af", True), "No": (None, "#94a3b8", False), "": (None, "#cbd5e1", False)},
    "COMPRO": {"Sí": ("#d1fae5", "#065f46", True), "No": (None, "#64748b", False), "": (None, "#cbd5e1", False)},
}
_ATAJOS = (("Hoy", "hoy"), ("Ayer", "ayer"), ("7 días", "7dias"), ("Mes", "mes"))


class _CargaThread(core.QThread):
    """Lee la hoja de Google fuera del hilo de la UI (una consulta por internet)."""
    cargado = core.pyqtSignal(object, object)
    fallo = core.pyqtSignal(str)

    def run(self):
        try:
            df, info = vio.cargar_visitas()
        except Exception as e:  # el hilo no puede propagar: se informa por señal
            self.fallo.emit(str(e) or type(e).__name__)
            return
        self.cargado.emit(df, info)


class VisitasWindow(widget.QWidget):
    """Widget embebible. Todo lo que hace va en el encabezado: filtros, resumen y actualizar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visitas = None            # DataFrame completo de la hoja (solo en memoria)
        self._info = None
        self._hilo = None
        self._ultima_lectura = None
        self._primera_carga = True
        self._manual = False
        self._setup_ui()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _icono(self, nombre_fa, color):
        return gui.QIcon(qta.icon(nombre_fa, color=color)) if qta is not None else gui.QIcon()

    def _icono_label(self, nombre_fa, color, tam=14):
        lbl = widget.QLabel()
        if qta is not None:
            lbl.setPixmap(qta.icon(nombre_fa, color=color).pixmap(tam, tam))
        return lbl

    def _setup_ui(self):
        lay = widget.QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        self.accion_actualizar = widget.QAction(self._icono("fa5s.sync-alt", "#2563eb"), "Actualizar visitas", self)
        self.accion_actualizar.setToolTip("Volver a leer la planilla de visitas")
        self.accion_actualizar.triggered.connect(lambda: self.cargar_datos(manual=True))

        lay.addWidget(self._crear_filtros())
        lay.addWidget(self._crear_tabla(), 1)

    def _crear_filtros(self):
        # Encabezado (visible aun con el panel oculto): qué hay aplicado, cuántas visitas y actualizar.
        self._lbl_filtros = widget.QLabel("")
        self._lbl_filtros.setStyleSheet("font-size: 11px; color: #64748b;")
        self._lbl_filtros.setSizePolicy(widget.QSizePolicy.Ignored, widget.QSizePolicy.Preferred)   # puede acortarse
        self._lbl_resultados = widget.QLabel("0 visitas")
        self._lbl_resultados.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        resumen = widget.QWidget()
        fila_resumen = widget.QHBoxLayout(resumen)
        fila_resumen.setContentsMargins(0, 0, 0, 0)
        fila_resumen.setSpacing(12)
        fila_resumen.addWidget(self._lbl_filtros)
        fila_resumen.addWidget(self._lbl_resultados)
        fila_resumen.addWidget(boton_cuadrado(self.accion_actualizar, alto=26))
        tarjeta, cuerpo, self._set_filtros_ocultos = crear_tarjeta_colapsable(
            "Filtros", extra=resumen, icono=self._icono_label("fa5s.search", "#2563eb"), colapsada=False)

        self.filtro_cliente = widget.QLineEdit()
        self.filtro_cliente.setPlaceholderText("Buscar cliente…")
        self.filtro_cliente.setClearButtonEnabled(True)
        self.filtro_cliente.setMinimumWidth(110)
        self.filtro_cliente.textChanged.connect(self.aplicar_filtros)

        self.filtro_vendedor = widget.QComboBox()
        self.filtro_vendedor.addItem("Todos", None)
        # que el mínimo no dependa del nombre más largo: así la fila de filtros puede comprimirse
        self.filtro_vendedor.setSizeAdjustPolicy(widget.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.filtro_vendedor.setMinimumContentsLength(8)
        self.filtro_vendedor.currentIndexChanged.connect(self.aplicar_filtros)

        hoy = core.QDate.currentDate()
        self.fecha_desde = self._selector_fecha(hoy)
        self.fecha_hasta = self._selector_fecha(hoy)
        self.fecha_desde.dateChanged.connect(self._on_desde)
        self.fecha_hasta.dateChanged.connect(self._on_hasta)

        def etiqueta(texto):
            e = widget.QLabel(texto)
            e.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
            return e

        # Dos filas: así el panel no obliga a una ventana ancha (monitores de 1024 px).
        arriba = widget.QHBoxLayout()
        arriba.setSpacing(10)
        arriba.addWidget(etiqueta("Cliente"))
        arriba.addWidget(self.filtro_cliente, 3)
        arriba.addWidget(etiqueta("Vendedor"))
        arriba.addWidget(self.filtro_vendedor, 1)
        cuerpo.addLayout(arriba)

        abajo = widget.QHBoxLayout()
        abajo.setSpacing(10)
        abajo.addWidget(etiqueta("Desde"))
        abajo.addWidget(self.fecha_desde)
        abajo.addWidget(etiqueta("Hasta"))
        abajo.addWidget(self.fecha_hasta)
        abajo.addSpacing(8)
        for texto, clave in _ATAJOS:
            boton = widget.QPushButton(texto)
            boton.setCursor(core.Qt.PointingHandCursor)
            boton.setStyleSheet(
                "QPushButton { background-color: #ffffff; color: #1d4ed8; border: 1px solid #bfdbfe; border-radius: 5px;"
                " padding: 3px 8px; font-size: 11px; font-weight: 600; }"
                "QPushButton:hover { background-color: #eff6ff; }")
            boton.clicked.connect(lambda _=False, c=clave: self._aplicar_atajo(c))
            abajo.addWidget(boton)
        abajo.addStretch(1)
        cuerpo.addLayout(abajo)
        self._actualizar_resumen_filtros()
        return tarjeta

    def _selector_fecha(self, fecha):
        d = widget.QDateEdit(fecha)
        d.setDisplayFormat("dd/MM/yyyy")
        d.setCalendarPopup(True)
        d.setMaximumDate(core.QDate.currentDate())
        return d

    def _crear_tabla(self):
        self._badge = widget.QLabel("0 visitas")
        self._badge.setStyleSheet(
            "background-color: #dbeafe; color: #1d4ed8; font-size: 10px; font-weight: 700;"
            " padding: 1px 8px; border-radius: 8px;")
        tarjeta, cuerpo = crear_tarjeta("Visitas", extra=self._badge,
                                        icono=self._icono_label("fa5s.map-marker-alt", "#0369a1"))
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        self.tabla = widget.QTableWidget()
        self.tabla.setColumnCount(len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS)
        self.tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.setWordWrap(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        self.tabla.setMinimumHeight(260)
        h = self.tabla.horizontalHeader()
        h.setSortIndicatorShown(True)
        h.setSectionResizeMode(6, widget.QHeaderView.Stretch)            # observación
        for col, ancho in ((0, 100), (1, 60), (2, 150), (3, 240), (4, 70), (5, 80)):
            h.setSectionResizeMode(col, widget.QHeaderView.Interactive)
            self.tabla.setColumnWidth(col, ancho)
        cuerpo.addWidget(self.tabla)

        barra = widget.QFrame()
        barra.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #e2e8f0;")
        fila = widget.QHBoxLayout(barra)
        fila.setContentsMargins(10, 5, 10, 5)
        self._lbl_resumen = widget.QLabel("")
        self._lbl_resumen.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self._lbl_origen = widget.QLabel("Cargando visitas…")
        self._lbl_origen.setStyleSheet("font-size: 10px; color: #94a3b8;")
        # los textos del pie pueden acortarse: no imponen el ancho mínimo de toda la ventana
        for lbl in (self._lbl_resumen, self._lbl_origen):
            lbl.setSizePolicy(widget.QSizePolicy.Ignored, widget.QSizePolicy.Preferred)
        fila.addWidget(self._lbl_resumen)
        fila.addStretch(1)
        fila.addWidget(self._lbl_origen)
        cuerpo.addWidget(barra)
        return tarjeta

    # ── carga ────────────────────────────────────────────────────────────────
    def refrescar_si_corresponde(self):
        """Al volver a la pestaña: carga la primera vez, o si la última lectura es vieja."""
        vieja = (self._ultima_lectura is None
                 or (dt.datetime.now() - self._ultima_lectura).total_seconds() > _RELEER_SI_PASARON_SEG)
        if vieja:
            self.cargar_datos()

    def cargar_datos(self, manual=False):
        """Lee la planilla en segundo plano. Una lectura a la vez."""
        if self._hilo is not None and self._hilo.isRunning():
            return
        self._manual = manual
        self.accion_actualizar.setEnabled(False)
        self._lbl_origen.setStyleSheet("font-size: 10px; color: #94a3b8;")
        self._lbl_origen.setText("Leyendo la planilla…")
        self._hilo = _CargaThread()
        self._hilo.cargado.connect(self._on_cargado)
        self._hilo.fallo.connect(self._on_fallo)
        self._hilo.finished.connect(lambda: self.accion_actualizar.setEnabled(True))
        self._hilo.start()

    def _on_cargado(self, df, info):
        self._visitas, self._info = df, info
        self._ultima_lectura = info["actualizado"]
        self._cargar_vendedores()
        if self._primera_carga:
            self._primera_carga = False
            self._arrancar_en_hoy_o_ultimo_dia()
        self._lbl_origen.setStyleSheet("font-size: 10px; color: #94a3b8;")
        texto = f"Planilla de Google · leída a las {info['actualizado']:%H:%M}"
        if info["repetidas"]:
            texto += f" · {info['repetidas']} filas repetidas ignoradas"
        self._lbl_origen.setText(texto)
        self.aplicar_filtros()

    def _on_fallo(self, mensaje):
        sin_datos = self._visitas is None
        self._lbl_origen.setStyleSheet("font-size: 10px; font-weight: 700; color: #d97706;")
        if sin_datos:
            self._lbl_origen.setText("No se pudo leer la planilla")
        else:
            self._lbl_origen.setText(
                f"No se pudo actualizar · se muestran los datos de las {self._ultima_lectura:%H:%M}")
        if sin_datos or self._manual:     # una relectura automática fallida no interrumpe con un cartel
            widget.QMessageBox.warning(
                self, "Visitas",
                f"No se pudo leer la planilla de visitas:\n{mensaje}\n\n"
                "Verificá la conexión a internet y que la planilla siga compartida con el enlace.")

    def _arrancar_en_hoy_o_ultimo_dia(self):
        """Por defecto se ven las visitas de hoy; si hoy no hay ninguna, el último día con datos."""
        hoy = dt.date.today()
        if len(vio.filtrar_visitas(self._visitas, desde=hoy, hasta=hoy)) == 0:
            ultimo = vio.ultimo_dia(self._visitas)
            if ultimo is not None:
                self._fijar_rango(ultimo, ultimo)

    def _cargar_vendedores(self):
        actual = self.filtro_vendedor.currentData()
        self.filtro_vendedor.blockSignals(True)
        self.filtro_vendedor.clear()
        self.filtro_vendedor.addItem("Todos", None)
        for v in sorted(set(self._visitas["VENDEDOR"]) - {""}):
            self.filtro_vendedor.addItem(v, v)
        i = self.filtro_vendedor.findData(actual) if actual else 0
        self.filtro_vendedor.setCurrentIndex(max(i, 0))
        self.filtro_vendedor.blockSignals(False)

    # ── fechas ───────────────────────────────────────────────────────────────
    def _fijar_rango(self, desde, hasta):
        for campo, fecha in ((self.fecha_desde, desde), (self.fecha_hasta, hasta)):
            campo.blockSignals(True)
            campo.setDate(core.QDate(fecha.year, fecha.month, fecha.day))
            campo.blockSignals(False)

    def _aplicar_atajo(self, clave):
        desde, hasta = vio.rango_preset(clave)
        self._fijar_rango(desde, hasta)
        self.aplicar_filtros()

    def _on_desde(self, *_):
        if self.fecha_desde.date() > self.fecha_hasta.date():      # el rango no puede quedar al revés
            self.fecha_hasta.blockSignals(True)
            self.fecha_hasta.setDate(self.fecha_desde.date())
            self.fecha_hasta.blockSignals(False)
        self.aplicar_filtros()

    def _on_hasta(self, *_):
        if self.fecha_hasta.date() < self.fecha_desde.date():
            self.fecha_desde.blockSignals(True)
            self.fecha_desde.setDate(self.fecha_hasta.date())
            self.fecha_desde.blockSignals(False)
        self.aplicar_filtros()

    # ── filtros y tabla ──────────────────────────────────────────────────────
    def _filtros_actuales(self):
        return {
            "texto": self.filtro_cliente.text(),
            "vendedor": self.filtro_vendedor.currentData(),
            "desde": self.fecha_desde.date().toPyDate(),
            "hasta": self.fecha_hasta.date().toPyDate(),
        }

    def _actualizar_resumen_filtros(self):
        f = self._filtros_actuales()
        self._lbl_filtros.setText(vio.descripcion_filtros(f["desde"], f["hasta"], f["vendedor"], f["texto"]))

    def aplicar_filtros(self, *_):
        self._actualizar_resumen_filtros()
        if self._visitas is None:
            return
        self._mostrar(vio.filtrar_visitas(self._visitas, **self._filtros_actuales()))

    def _celda_si_no(self, columna, valor):
        fondo, texto, negrita = _COLOR_SI_NO[columna][valor]
        item = ItemOrdenable(valor or "—")
        item.setData(core.Qt.UserRole, valor)
        item.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
        item.setForeground(gui.QColor(texto))
        if fondo:
            item.setBackground(gui.QColor(fondo))
        item.setFont(gui.QFont("Segoe UI", 8, gui.QFont.Bold if negrita else gui.QFont.Normal))
        return item

    def _mostrar(self, df):
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(len(df))
        mono = gui.QFont("Consolas", 8)
        for i, r in enumerate(df.itertuples(index=False)):
            ts = r.FECHA
            fecha = ItemOrdenable(f"{ts:%d/%m/%Y}")
            fecha.setData(core.Qt.UserRole, ts.to_pydatetime())
            hora = ItemOrdenable(f"{ts:%H:%M}")
            hora.setData(core.Qt.UserRole, ts.hour * 3600 + ts.minute * 60 + ts.second)
            for it in (fecha, hora):
                it.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
                it.setFont(mono)
            vendedor = ItemOrdenable(r.VENDEDOR)
            vendedor.setData(core.Qt.UserRole, r.VENDEDOR.lower())
            vendedor.setFont(gui.QFont("Segoe UI", 9))
            cliente = ItemOrdenable(r.CLIENTE)
            cliente.setData(core.Qt.UserRole, vio.normalizar_texto(r.CLIENTE))
            cliente.setFont(gui.QFont("Segoe UI", 9, gui.QFont.DemiBold))
            obs = ItemOrdenable(r.OBSERVACION)
            obs.setData(core.Qt.UserRole, r.OBSERVACION.lower())
            obs.setFont(gui.QFont("Segoe UI", 9))
            obs.setToolTip(r.OBSERVACION)
            fila = (fecha, hora, vendedor, cliente, self._celda_si_no("NUEVO", r.NUEVO),
                    self._celda_si_no("COMPRO", r.COMPRO), obs)
            for col, item in enumerate(fila):
                self.tabla.setItem(i, col, item)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(0, core.Qt.DescendingOrder)      # lo más reciente arriba

        self._lbl_resultados.setText(f"{len(df)} visitas")
        self._badge.setText(f"{len(df)} visitas")
        self._lbl_resumen.setText(self._texto_resumen(df))

    def _texto_resumen(self, df):
        if len(df):
            r = vio.resumen_visitas(df)
            pct = f"{r['pct_compra']:.1f}".replace(".", ",")
            return (f"{r['visitas']} visitas · {r['compraron']} compraron ({pct}%) · "
                    f"{r['nuevos']} clientes nuevos · {r['clientes']} clientes distintos")
        ultimo = vio.ultimo_dia(self._visitas) if self._visitas is not None else None
        sugerencia = f" Última visita registrada: {ultimo:%d/%m/%Y}." if ultimo else ""
        return "Sin visitas para el período elegido." + sugerencia
