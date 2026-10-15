"""Cuentas Corrientes: deuda pendiente por cliente desde una fecha elegida."""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import cuentas_corrientes_io as cc_io
from src.ui.widgets.tarjeta import crear_tarjeta
from src.Views.CuentasCorrientes.DetalleCuenta import DetalleCuentaDialog

_ROL_CUENTA = core.Qt.UserRole + 1   # nº de cuenta guardado en el item "Cliente"
FECHA_DESDE_DEFECTO = core.QDate(2024, 1, 1)
_COLUMNAS = ["#", "Cliente", "Saldo pendiente", "Factura más vieja con saldo"]


def _fmt_monto(valor):
    return f"$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


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
        self._ctacorr = None
        self._clientes = None
        self._hilo = None
        self._setup_ui()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _icono(self, nombre_fa, color):
        return gui.QIcon(qta.icon(nombre_fa, color=color)) if qta is not None else gui.QIcon()

    def _setup_ui(self):
        lay = widget.QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        actualizar = widget.QAction(self._icono("fa5s.sync-alt", "#2563eb"), "Actualizar", self)
        actualizar.triggered.connect(self.cargar_datos)
        self.acciones_toolbar = [actualizar]

        lay.addWidget(self._crear_filtros())
        lay.addWidget(self._crear_tabla(), 1)

        self.status_label = widget.QLabel("Listo")
        lay.addWidget(self.status_label)

    def _crear_filtros(self):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.calendar-alt", color="#2563eb").pixmap(14, 14))
        tarjeta, cuerpo = crear_tarjeta("Período de análisis", icono=icono)

        fila = widget.QHBoxLayout()
        fila.setSpacing(8)
        etiqueta = widget.QLabel("Analizar facturas desde")
        etiqueta.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
        self.fecha_desde = widget.QDateEdit(FECHA_DESDE_DEFECTO)
        self.fecha_desde.setDisplayFormat("dd/MM/yyyy")
        self.fecha_desde.setCalendarPopup(True)
        self.fecha_desde.setMaximumDate(core.QDate.currentDate())
        self.fecha_desde.setFixedWidth(120)
        self.fecha_desde.dateChanged.connect(self.recalcular)
        ayuda = widget.QLabel(
            "Se consideran las facturas emitidas desde esta fecha, hasta hoy. "
            "Doble clic en un cliente para ver sus facturas."
        )
        ayuda.setStyleSheet("font-size: 10px; color: #94a3b8;")
        fila.addWidget(etiqueta)
        fila.addWidget(self.fecha_desde)
        fila.addWidget(ayuda)
        fila.addStretch(1)
        cuerpo.addLayout(fila)
        return tarjeta

    def _crear_tabla(self):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.file-invoice-dollar", color="#0369a1").pixmap(14, 14))
        self._badge = widget.QLabel("0 clientes")
        self._badge.setStyleSheet(
            "background-color: #dbeafe; color: #1d4ed8; font-size: 10px; font-weight: 700;"
            " padding: 1px 8px; border-radius: 8px;"
        )
        tarjeta, cuerpo = crear_tarjeta("Clientes con saldo pendiente", extra=self._badge, icono=icono)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        self.tabla = widget.QTableWidget()
        self.tabla.setColumnCount(len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS)
        self.tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(24)
        self.tabla.cellDoubleClicked.connect(self._abrir_detalle)
        header = self.tabla.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(1, widget.QHeaderView.Stretch)
        for i, ancho in ((0, 40), (2, 150), (3, 190)):
            header.setSectionResizeMode(i, widget.QHeaderView.Interactive)
            self.tabla.setColumnWidth(i, ancho)
        cuerpo.addWidget(self.tabla)

        barra = widget.QFrame()
        barra.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #e2e8f0;")
        fila = widget.QHBoxLayout(barra)
        fila.setContentsMargins(10, 5, 10, 5)
        self._lbl_total = widget.QLabel("Saldo total pendiente: $ 0,00")
        self._lbl_total.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a;")
        fila.addStretch(1)
        fila.addWidget(self._lbl_total)
        cuerpo.addWidget(barra)
        return tarjeta

    # ── datos ────────────────────────────────────────────────────────────────
    def cargar_datos(self):
        """Lee los DBF en background y recalcula con la fecha elegida."""
        if self._hilo is not None and self._hilo.isRunning():
            return
        self.status_label.setText("Cargando cuentas corrientes…")
        for accion in self.acciones_toolbar:
            accion.setEnabled(False)
        self._hilo = _CargaThread()
        self._hilo.completado.connect(self._on_cargado)
        self._hilo.fallo.connect(self._on_fallo)
        self._hilo.start()

    def _on_cargado(self, ctacorr, clientes):
        for accion in self.acciones_toolbar:
            accion.setEnabled(True)
        self._ctacorr, self._clientes = ctacorr, clientes
        self.recalcular()

    def _on_fallo(self, mensaje):
        for accion in self.acciones_toolbar:
            accion.setEnabled(True)
        self.status_label.setText("Error al cargar")
        widget.QMessageBox.warning(self, "Cuentas Corrientes", f"No se pudieron leer los DBF:\n{mensaje}")

    def recalcular(self, *_):
        """Re-aplica la fecha elegida sobre los datos ya cargados (sin releer DBF)."""
        if self._ctacorr is None:
            return
        desde = self.fecha_desde.date().toPyDate()
        self._mostrar(cc_io.calcular_deudores(self._ctacorr, self._clientes, desde))
        self.status_label.setText(f"Facturas desde el {desde.strftime('%d/%m/%Y')} hasta hoy")

    def _abrir_detalle(self, fila, _col):
        """Doble clic: facturas pendientes del cliente de esa fila."""
        item = self.tabla.item(fila, 1)
        if item is None or self._ctacorr is None:
            return
        cuenta = item.data(_ROL_CUENTA)
        desde = self.fecha_desde.date().toPyDate()
        detalle = cc_io.detalle_facturas(self._ctacorr, cuenta, desde)
        DetalleCuentaDialog(item.text(), cuenta, detalle, desde, self).exec_()

    def _mostrar(self, df):
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(len(df))
        fuente_mono = gui.QFont("Consolas", 8)
        for i, fila in enumerate(df.itertuples(index=False)):
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

            fecha = fila[3]
            item_fecha = _ItemOrdenable(fecha.strftime("%d/%m/%Y"))
            item_fecha.setData(core.Qt.UserRole, fecha.to_pydatetime())
            item_fecha.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_fecha.setFont(fuente_mono)

            for col, item in enumerate((item_n, item_cli, item_saldo, item_fecha)):
                self.tabla.setItem(i, col, item)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(2, core.Qt.DescendingOrder)

        self._badge.setText(f"{len(df):,} clientes".replace(",", "."))
        self._lbl_total.setText(f"Saldo total pendiente: {_fmt_monto(df['Saldo'].sum() if len(df) else 0.0)}")
