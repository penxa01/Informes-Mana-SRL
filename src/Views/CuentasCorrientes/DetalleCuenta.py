"""Diálogo con las facturas pendientes de un cliente (abre con doble clic en la grilla)."""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

_COLUMNAS = ["Emisión", "Comprobante", "Total", "Saldo"]


def _fmt_monto(valor):
    return f"$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


class DetalleCuentaDialog(widget.QDialog):
    def __init__(self, cliente, cuenta, detalle, fecha_desde, parent=None):
        """
        :param detalle: DataFrame de ``cuentas_corrientes_io.detalle_facturas``.
        :param fecha_desde: ``date`` usada en el análisis (solo informativa).
        """
        super().__init__(parent)
        self.setWindowTitle(f"Facturas pendientes — {cliente}")
        self.resize(640, 420)

        lay = widget.QVBoxLayout(self)
        lay.setSpacing(8)

        titulo = widget.QLabel(cliente)
        titulo.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        sub = widget.QLabel(
            f"Cuenta Nº {cuenta} · facturas desde el {fecha_desde.strftime('%d/%m/%Y')} hasta hoy"
        )
        sub.setStyleSheet("font-size: 11px; color: #64748b;")
        lay.addWidget(titulo)
        lay.addWidget(sub)

        self.tabla = widget.QTableWidget(len(detalle), len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS)
        self.tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(24)
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(1, widget.QHeaderView.Stretch)
        for col in (0, 2, 3):
            header.setSectionResizeMode(col, widget.QHeaderView.ResizeToContents)

        mono = gui.QFont("Consolas", 8)
        for i, fila in enumerate(detalle.itertuples(index=False)):
            emision = widget.QTableWidgetItem(fila[0].strftime("%d/%m/%Y"))
            emision.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            emision.setFont(mono)
            comprobante = widget.QTableWidgetItem(fila[1])
            comprobante.setFont(mono)
            total = widget.QTableWidgetItem(_fmt_monto(fila[2]))
            total.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            total.setFont(mono)
            saldo = widget.QTableWidgetItem(_fmt_monto(fila[3]))
            saldo.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            saldo.setFont(gui.QFont("Consolas", 8, gui.QFont.Bold))
            saldo.setForeground(gui.QColor("#b91c1c"))
            for col, item in enumerate((emision, comprobante, total, saldo)):
                self.tabla.setItem(i, col, item)
        lay.addWidget(self.tabla, 1)

        pie = widget.QHBoxLayout()
        self.lbl_resumen = widget.QLabel(
            f"{len(detalle)} facturas · Saldo pendiente: "
            f"{_fmt_monto(detalle['Saldo'].sum() if len(detalle) else 0.0)}"
        )
        self.lbl_resumen.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a;")
        cerrar = widget.QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        pie.addWidget(self.lbl_resumen)
        pie.addStretch(1)
        pie.addWidget(cerrar)
        lay.addLayout(pie)
