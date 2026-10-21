"""Cuentas Corrientes: panel de deuda pendiente por cliente desde una fecha elegida."""
from datetime import date

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import cuentas_corrientes_io as cc_io
from src.controllers import reclamos_db as rdb
from src.ui.widgets.tarjeta import crear_kpi, crear_tarjeta, crear_tarjeta_colapsable
from src.Views.CuentasCorrientes.DetalleCuenta import DetalleCuentaDialog
from src.Views.CuentasCorrientes.formato import fmt_monto as _fmt_monto
from src.Views.CuentasCorrientes.Reclamos import ReclamosDialog

_ROL_CUENTA = core.Qt.UserRole + 1   # nº de cuenta guardado en el item "Cliente"
FECHA_DESDE_DEFECTO = core.QDate(2024, 1, 1)
_COLUMNAS = ["#", "Cliente", "Saldo pendiente", "Factura más vieja con saldo", "Antigüedad", "Estado"]
_COL_CLIENTE = 1

# estado -> (fondo, texto)
_ESTADO_COLORES = {
    "En término": ("#d1fae5", "#065f46"),
    "Mora": ("#fef3c7", "#92400e"),
    "Mora crítica": ("#fee2e2", "#991b1b"),
}
_ANTIGUEDADES = [("Todas las antigüedades", 0), ("Mayor a 30 días", 30),
                 ("Mayor a 60 días", 60), ("Mayor a 90 días", 90)]


def _fmt_pct(valor):
    return f"{valor:.1f}".replace(".", ",") + "%"


class _ItemOrdenable(widget.QTableWidgetItem):
    """Ordena por la clave tipada de UserRole (número / fecha), no por el texto."""

    def __lt__(self, other):
        a = self.data(core.Qt.UserRole)
        b = other.data(core.Qt.UserRole) if isinstance(other, widget.QTableWidgetItem) else None
        if a is None or b is None:
            return super().__lt__(other)
        return a < b


class _CargaThread(core.QThread):
    """Lee ctacorr + ctaclien (caché Parquet) fuera del hilo de la UI."""
    completado = core.pyqtSignal(object, object)
    fallo = core.pyqtSignal(str)

    def run(self):
        try:
            ctacorr, clientes = cc_io.cargar_datos()
        except Exception as e:  # el hilo no puede propagar: se informa por señal
            self.fallo.emit(str(e))
            return
        self.completado.emit(ctacorr, clientes)


class CuentasCorrientesWindow(widget.QWidget):
    """Widget embebible. Las acciones de barra van en ``self.acciones_toolbar``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.acciones_toolbar = []
        self._abrir_reclamos_al_cargar = False
        self._ctacorr = None
        self._clientes = None
        self._deudores = None        # resultado completo para la fecha elegida
        self._hilo = None
        self._setup_ui()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _icono(self, nombre_fa, color):
        return gui.QIcon(qta.icon(nombre_fa, color=color)) if qta is not None else gui.QIcon()

    def _icono_label(self, nombre_fa, color, tam=16):
        lbl = widget.QLabel()
        if qta is not None:
            lbl.setPixmap(qta.icon(nombre_fa, color=color).pixmap(tam, tam))
        return lbl

    def _setup_ui(self):
        lay = widget.QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        actualizar = widget.QAction(self._icono("fa5s.sync-alt", "#2563eb"), "Actualizar", self)
        actualizar.triggered.connect(self.cargar_datos)
        self.accion_detalle = widget.QAction(self._icono("fa5s.eye", "#0369a1"), "Ver detalle", self)
        self.accion_detalle.setEnabled(False)
        self.accion_detalle.triggered.connect(lambda: self._abrir_detalle(self.tabla.currentRow()))
        self.accion_reclamos = widget.QAction(self._icono("fa5s.gavel", "#d97706"), "Reclamos", self)
        self.accion_reclamos.triggered.connect(self._abrir_reclamos)
        limpiar = widget.QAction(self._icono("fa5s.eraser", "#e11d48"), "Limpiar Filtros", self)
        limpiar.triggered.connect(self.limpiar_filtros)
        self._acciones_carga = [actualizar]
        self.acciones_toolbar = [actualizar, self.accion_detalle, self.accion_reclamos, limpiar]

        lay.addLayout(self._crear_kpis())
        lay.addWidget(self._crear_filtros())
        lay.addWidget(self._crear_tabla(), 1)

        self.status_label = widget.QLabel("Listo")
        lay.addWidget(self.status_label)

    def _crear_kpis(self):
        fila = widget.QHBoxLayout()
        fila.setSpacing(10)
        self._kpi = {}
        definiciones = (
            ("saldo", "Saldo total pendiente", "#0f172a", "fa5s.wallet", "#64748b"),
            ("mora", "En mora (> 30 días)", "#b45309", "fa5s.hourglass-half", "#d97706"),
            ("critica", "Mora crítica (> 60 días)", "#b91c1c", "fa5s.exclamation-triangle", "#e11d48"),
        )
        for clave, titulo, color, icono, color_icono in definiciones:
            frame, valor, sub = crear_kpi(titulo, color, self._icono_label(icono, color_icono))
            self._kpi[clave] = (valor, sub)
            fila.addWidget(frame, 1)
        return fila

    def _crear_filtros(self):
        # Encabezado (visible aun plegado): qué hay aplicado + cuántos resultados.
        self._lbl_filtros = widget.QLabel("")
        self._lbl_filtros.setStyleSheet("font-size: 11px; color: #64748b;")
        self._lbl_resultados = widget.QLabel("0 resultados")
        self._lbl_resultados.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        resumen = widget.QWidget()
        fila_resumen = widget.QHBoxLayout(resumen)
        fila_resumen.setContentsMargins(0, 0, 0, 0)
        fila_resumen.setSpacing(12)
        fila_resumen.addWidget(self._lbl_filtros)
        fila_resumen.addWidget(self._lbl_resultados)
        tarjeta, cuerpo, self._set_filtros_colapsados = crear_tarjeta_colapsable(
            "Filtros", extra=resumen, icono=self._icono_label("fa5s.search", "#2563eb", 14), colapsada=True,
        )

        # Una sola fila: ocupa poco aun desplegado.
        grid = widget.QHBoxLayout()
        grid.setSpacing(10)

        self.filtro_cliente = widget.QLineEdit()
        self.filtro_cliente.setPlaceholderText("Buscar por nombre o nº de cuenta...")
        self.filtro_cliente.textChanged.connect(self.aplicar_filtros)

        self.filtro_saldo = widget.QLineEdit()
        self.filtro_saldo.setPlaceholderText("Desde $ 0,00...")
        self.filtro_saldo.textChanged.connect(self.aplicar_filtros)

        self.filtro_antiguedad = widget.QComboBox()
        for texto, _dias in _ANTIGUEDADES:
            self.filtro_antiguedad.addItem(texto)
        self.filtro_antiguedad.currentIndexChanged.connect(self.aplicar_filtros)

        self.fecha_desde = widget.QDateEdit(FECHA_DESDE_DEFECTO)
        self.fecha_desde.setDisplayFormat("dd/MM/yyyy")
        self.fecha_desde.setCalendarPopup(True)
        self.fecha_desde.setMaximumDate(core.QDate.currentDate())
        self.fecha_desde.dateChanged.connect(self.recalcular)
        self.fecha_desde.setToolTip("Se consideran las facturas emitidas desde esta fecha hasta hoy.")
        self.filtro_antiguedad.setToolTip("Se mide desde la emisión de la factura más vieja con saldo.")

        self.filtro_cliente.setMinimumWidth(180)
        self.filtro_saldo.setFixedWidth(110)
        for texto, campo, estiramiento in (
            ("Cliente", self.filtro_cliente, 3),
            ("Saldo mín.", self.filtro_saldo, 0),
            ("Antigüedad", self.filtro_antiguedad, 1),
            ("Facturas desde", self.fecha_desde, 0),
        ):
            etiqueta = widget.QLabel(texto)
            etiqueta.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
            grid.addWidget(etiqueta)
            grid.addWidget(campo, estiramiento)
        cuerpo.addLayout(grid)
        self._actualizar_resumen_filtros(self.fecha_desde.date().toPyDate(), "", 0.0, 0)
        return tarjeta

    def _crear_leyenda(self):
        cont = widget.QWidget()
        lay = widget.QHBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        for estado, (fondo, texto) in _ESTADO_COLORES.items():
            punto = widget.QLabel(f"● {estado}")
            punto.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {texto};")
            lay.addWidget(punto)
        self.btn_reclamos = widget.QPushButton(" Reclamos")
        if qta is not None:
            self.btn_reclamos.setIcon(self._icono("fa5s.gavel", "#ffffff"))
        self.btn_reclamos.setToolTip("Crear un reclamo y ver los reclamos activos")
        self.btn_reclamos.setStyleSheet(
            "QPushButton { background-color: #d97706; color: white; font-size: 11px; font-weight: 700; "
            "border-radius: 4px; padding: 3px 12px; } QPushButton:hover { background-color: #b45309; }"
            "QPushButton:disabled { background-color: #cbd5e1; }"
        )
        self.btn_reclamos.clicked.connect(self._abrir_reclamos)
        lay.addWidget(self.btn_reclamos)
        self._badge = widget.QLabel("0 clientes")
        self._badge.setStyleSheet(
            "background-color: #dbeafe; color: #1d4ed8; font-size: 10px; font-weight: 700;"
            " padding: 1px 8px; border-radius: 8px;"
        )
        lay.addWidget(self._badge)
        return cont

    def _crear_tabla(self):
        tarjeta, cuerpo = crear_tarjeta(
            "Clientes con saldo pendiente", extra=self._crear_leyenda(),
            icono=self._icono_label("fa5s.file-invoice-dollar", "#0369a1", 14),
        )
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        self.tabla = widget.QTableWidget()
        self.tabla.setColumnCount(len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS)
        self.tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(widget.QAbstractItemView.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        self.tabla.setMinimumHeight(260)
        self.tabla.cellDoubleClicked.connect(lambda fila, _col: self._abrir_detalle(fila))
        self.tabla.itemSelectionChanged.connect(
            lambda: self.accion_detalle.setEnabled(self.tabla.currentRow() >= 0
                                                   and bool(self.tabla.selectedItems()))
        )
        header = self.tabla.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(_COL_CLIENTE, widget.QHeaderView.Stretch)
        for i, ancho in ((0, 40), (2, 150), (3, 220), (4, 100), (5, 125)):
            header.setSectionResizeMode(i, widget.QHeaderView.Interactive)
            self.tabla.setColumnWidth(i, ancho)
        cuerpo.addWidget(self.tabla)

        barra = widget.QFrame()
        barra.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #e2e8f0;")
        fila = widget.QHBoxLayout(barra)
        fila.setContentsMargins(10, 5, 10, 5)
        self._lbl_mostrando = widget.QLabel("Mostrando 0 de 0 clientes")
        self._lbl_mostrando.setStyleSheet("font-size: 11px; color: #475569; font-weight: 600;")
        self._lbl_promedio = widget.QLabel("Promedio por cliente: $ 0,00")
        self._lbl_promedio.setStyleSheet("font-size: 11px; color: #64748b;")
        self._lbl_total = widget.QLabel("Saldo mostrado: $ 0,00")
        self._lbl_total.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a;")
        fila.addWidget(self._lbl_mostrando)
        fila.addWidget(self._sep())
        fila.addWidget(self._lbl_promedio)
        fila.addStretch(1)
        fila.addWidget(self._lbl_total)
        cuerpo.addWidget(barra)
        return tarjeta

    def _sep(self):
        s = widget.QFrame()
        s.setFrameShape(widget.QFrame.VLine)
        s.setStyleSheet("color: #cbd5e1;")
        s.setFixedHeight(14)
        return s

    # ── datos ────────────────────────────────────────────────────────────────
    def cargar_datos(self):
        """Lee los DBF en background y recalcula con la fecha elegida."""
        if self._hilo is not None and self._hilo.isRunning():
            return
        self.status_label.setText("Cargando cuentas corrientes…")
        for accion in self._acciones_carga:
            accion.setEnabled(False)
        self._hilo = _CargaThread()
        self._hilo.completado.connect(self._on_cargado)
        self._hilo.fallo.connect(self._on_fallo)
        self._hilo.start()

    def _on_cargado(self, ctacorr, clientes):
        for accion in self._acciones_carga:
            accion.setEnabled(True)
        self._ctacorr, self._clientes = ctacorr, clientes
        self.recalcular()
        if self._abrir_reclamos_al_cargar:      # venían desde la alerta de reclamos sin novedades
            self._abrir_reclamos_al_cargar = False
            core.QTimer.singleShot(0, self._abrir_reclamos)

    def abrir_reclamos_cuando_listo(self):
        """Abre el modal de reclamos ya, o apenas terminen de cargar los datos (si todavía no lo
        hicieron). Lo usa la alerta de «reclamos sin novedades» de la barra de estado."""
        if self._deudores is not None:
            self._abrir_reclamos()
        else:
            self._abrir_reclamos_al_cargar = True
            self.cargar_datos()

    def _on_fallo(self, mensaje):
        for accion in self._acciones_carga:
            accion.setEnabled(True)
        self.status_label.setText("Error al cargar")
        widget.QMessageBox.warning(self, "Cuentas Corrientes", f"No se pudieron leer los DBF:\n{mensaje}")

    def recalcular(self, *_):
        """Re-aplica la fecha elegida sobre los datos ya cargados (sin releer DBF)."""
        if self._ctacorr is None:
            return
        desde = self.fecha_desde.date().toPyDate()
        self._deudores = cc_io.calcular_deudores(self._ctacorr, self._clientes, desde)
        self._actualizar_kpis(cc_io.resumen_cartera(self._ctacorr, self._deudores, desde))
        self.aplicar_filtros()
        self.status_label.setText(f"Facturas desde el {desde.strftime('%d/%m/%Y')} hasta hoy")

    def _actualizar_kpis(self, r):
        self._kpi["saldo"][0].setText(_fmt_monto(r["saldo_total"]))
        detalle = f"{r['clientes']} clientes con saldo pendiente"
        if r["cuentas_a_favor"]:
            # El total es neto: la tabla suma solo lo que se debe; esto explica la diferencia.
            detalle += (f" · neto de {_fmt_monto(r['a_favor'])} de {r['cuentas_a_favor']} "
                        "cuentas con saldo a favor")
        self._kpi["saldo"][1].setText(detalle)
        self._kpi["saldo"][1].setToolTip(
            f"Deuda de los clientes de la tabla: {_fmt_monto(r['saldo_bruto'])}\n"
            f"Saldos a favor (cuentas no listadas): {_fmt_monto(r['a_favor'])}")
        self._kpi["mora"][0].setText(_fmt_monto(r["mora"]))
        self._kpi["mora"][1].setText(f"{_fmt_pct(r['pct_mora'])} de la cartera")
        self._kpi["critica"][0].setText(_fmt_monto(r["critica"]))
        self._kpi["critica"][1].setText(f"{_fmt_pct(r['pct_critica'])} de la cartera")

    # ── filtros ──────────────────────────────────────────────────────────────
    def limpiar_filtros(self):
        self.filtro_cliente.clear()
        self.filtro_saldo.clear()
        self.filtro_antiguedad.setCurrentIndex(0)

    def _saldo_minimo(self):
        try:
            minimo = cc_io.parsear_monto(self.filtro_saldo.text())
        except ValueError:
            self.filtro_saldo.setStyleSheet("border: 1px solid #e11d48;")
            self.filtro_saldo.setToolTip("Monto inválido. Usá el formato 1.500.000,50")
            return 0.0
        self.filtro_saldo.setStyleSheet("")
        self.filtro_saldo.setToolTip("")
        return minimo

    def _actualizar_resumen_filtros(self, desde, texto, saldo_min, dias_min):
        self._lbl_filtros.setText(cc_io.descripcion_filtros(desde, texto, saldo_min, dias_min))

    def aplicar_filtros(self, *_):
        texto = self.filtro_cliente.text()
        saldo_min = self._saldo_minimo()
        dias_min = _ANTIGUEDADES[self.filtro_antiguedad.currentIndex()][1]
        self._actualizar_resumen_filtros(self.fecha_desde.date().toPyDate(), texto, saldo_min, dias_min)
        if self._deudores is None:
            return
        self._mostrar(cc_io.filtrar_deudores(self._deudores, texto=texto, saldo_min=saldo_min, dias_min=dias_min))

    # ── tabla ────────────────────────────────────────────────────────────────
    def _abrir_detalle(self, fila):
        """Facturas pendientes del cliente de esa fila (doble clic o botón de barra)."""
        item = self.tabla.item(fila, _COL_CLIENTE) if fila >= 0 else None
        if item is None or self._ctacorr is None:
            return
        cuenta = item.data(_ROL_CUENTA)
        desde = self.fecha_desde.date().toPyDate()
        detalle = cc_io.detalle_facturas(self._ctacorr, cuenta, desde)
        DetalleCuentaDialog(item.text(), cuenta, detalle, desde, self).exec_()

    def _abrir_reclamos(self):
        """Modal de reclamos. Preselecciona el cliente de la fila elegida en la grilla."""
        if self._deudores is None:
            widget.QMessageBox.information(self, "Reclamos", "Esperá a que terminen de cargar las cuentas corrientes.")
            return
        widget.QApplication.setOverrideCursor(core.Qt.WaitCursor)
        try:
            con = rdb.conectar()
            rdb.asegurar_esquema(con)
            con.commit()
        except Exception as e:
            widget.QApplication.restoreOverrideCursor()
            widget.QMessageBox.warning(
                self, "Reclamos", f"No se pudo conectar a la base de datos de Pedidos:\n{e}")
            return
        widget.QApplication.restoreOverrideCursor()

        item = self.tabla.item(self.tabla.currentRow(), _COL_CLIENTE) if self.tabla.selectedItems() else None
        cuenta = item.data(_ROL_CUENTA) if item is not None else None
        try:
            ReclamosDialog(con, self._ctacorr, self._clientes,
                           self.fecha_desde.date().toPyDate(), cuenta, self).exec_()
        finally:
            con.close()

    def _mostrar(self, df):
        hoy = date.today()
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(len(df))
        fuente_mono = gui.QFont("Consolas", 8)
        for i, fila in enumerate(df.itertuples(index=False)):
            fecha = fila[3]
            dias = (hoy - fecha.date()).days
            estado = cc_io.estado_mora(dias)
            fondo, texto = _ESTADO_COLORES[estado]

            item_n = _ItemOrdenable(str(i + 1))
            item_n.setData(core.Qt.UserRole, i)
            item_n.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_n.setForeground(gui.QColor("#94a3b8"))

            item_cli = _ItemOrdenable(fila.Cliente)
            item_cli.setData(core.Qt.UserRole, fila.Cliente.lower())
            item_cli.setData(_ROL_CUENTA, int(fila.Cuenta))
            item_cli.setToolTip(f"Cuenta Nº {fila.Cuenta}")

            item_saldo = _ItemOrdenable(_fmt_monto(fila.Saldo))
            item_saldo.setData(core.Qt.UserRole, float(fila.Saldo))
            item_saldo.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            item_saldo.setForeground(gui.QColor("#b91c1c"))
            item_saldo.setFont(gui.QFont("Consolas", 8, gui.QFont.Bold))

            item_fecha = _ItemOrdenable(fecha.strftime("%d/%m/%Y"))
            item_fecha.setData(core.Qt.UserRole, fecha.to_pydatetime())
            item_fecha.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_fecha.setFont(fuente_mono)

            item_dias = _ItemOrdenable(f"{dias} días")
            item_dias.setData(core.Qt.UserRole, dias)
            item_dias.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_dias.setForeground(gui.QColor(texto))
            item_dias.setFont(fuente_mono)

            item_estado = _ItemOrdenable(estado)
            item_estado.setData(core.Qt.UserRole, dias)   # ordena de "más al día" a "más crítico"
            item_estado.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_estado.setBackground(gui.QColor(fondo))
            item_estado.setForeground(gui.QColor(texto))
            item_estado.setFont(gui.QFont("Segoe UI", 8, gui.QFont.Bold))

            for col, item in enumerate((item_n, item_cli, item_saldo, item_fecha, item_dias, item_estado)):
                self.tabla.setItem(i, col, item)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(2, core.Qt.DescendingOrder)

        total = float(df["Saldo"].sum()) if len(df) else 0.0
        de = len(self._deudores) if self._deudores is not None else 0
        self._badge.setText(f"{len(df):,} clientes".replace(",", "."))
        self._lbl_resultados.setText(f"{len(df)} resultados")
        self._lbl_mostrando.setText(f"Mostrando {len(df)} de {de} clientes")
        self._lbl_promedio.setText(f"Promedio por cliente: {_fmt_monto(total / len(df) if len(df) else 0.0)}")
        self._lbl_total.setText(f"Saldo mostrado: {_fmt_monto(total)}")
