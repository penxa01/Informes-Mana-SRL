import PyQt5.QtWidgets as widget
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Qt
import pandas as pd
from datetime import datetime

from src.ui.widgets.indicadores import barra_porcentaje

# ── Índices de columna de la tabla de detalle ────────────────────────────────
(_D_NUM, _D_FECHA, _D_CLIENTE, _D_CUENTA, _D_TC, _D_NC, _D_UNID, _D_TOTAL,
 _D_PUNIT, _D_COSTO, _D_BUNIT, _D_BTOT, _D_PCT) = range(13)

_ENCABEZADOS = ["#", "Fecha Emisión", "Razón Social Cliente", "Cta.", "TC", "N° Comp.",
                "Cant.", "Total Venta ($)", "Precio Unit. ($)", "Costo Unit. ($)",
                "Beneficio Unit.", "Beneficio Total", "Margen %"]

_TABLA_QSS = """
    QTableWidget {
        background-color: white;
        alternate-background-color: #f8fafc;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        gridline-color: #eef2f7;
        border: none;
    }
    QTableWidget::item { padding: 3px 8px; border: none; }
    QHeaderView::section {
        background-color: #1e293b;
        color: #e2e8f0;
        padding: 6px 8px;
        border: none;
        border-right: 1px solid #334155;
        font-weight: 700;
        font-size: 10px;
    }
    QTableCornerButton::section { background-color: #1e293b; border: none; }
"""

_VERDE_BG, _VERDE_FG = Gui.QColor(209, 250, 229), Gui.QColor(6, 95, 70)
_ROJO_BG, _ROJO_FG = Gui.QColor(254, 226, 226), Gui.QColor(153, 27, 27)


def _money(v):
    """1234.5 -> '$ 1.234,50' (formato argentino)."""
    try:
        s = f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "$ 0,00"
    return "$ " + s.replace(",", "@").replace(".", ",").replace("@", ".")


def _pct(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0,00%"
    if v != v or abs(v) == float("inf"):   # NaN o infinito
        return "—"
    return f"{v:.2f}%".replace(".", ",")


class _CostoDetalleDelegate(widget.QStyledItemDelegate):
    """Delegate para la columna Costo Unit. en el detalle de ventas."""

    def createEditor(self, parent, option, index):
        editor = widget.QLineEdit(parent)
        editor.setAlignment(Qt.Qt.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        val = str(index.data(Qt.Qt.DisplayRole) or "0")
        val = val.replace('$', '').replace('.', '').replace(',', '.').strip()
        editor.setText(val)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        texto = editor.text().strip()
        try:
            if ',' in texto and '.' in texto:
                texto = texto.replace('.', '').replace(',', '.')
            else:
                texto = texto.replace(',', '.')
            valor = float(texto)
            model.setData(index, _money(valor), Qt.Qt.DisplayRole)
        except ValueError:
            pass  # Valor inválido: mantener el anterior


class DetalleDialog(widget.QDialog):
    """Detalle venta por venta de un SKU, con estética del prototipo
    (prototypeExample/prototypeDetalleBeneficio.html): banner con KPIs, toolbar
    de búsqueda + filtro de tipo, tabla densa con header oscuro y barra de
    totales consolidados al pie."""

    def __init__(self, sku, producto, detalle_ventas, clientes_dict=None, parent=None, on_costo_cambiado_cb=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle de Ventas — {sku}")
        self.resize(1240, 680)
        self.setMinimumSize(900, 480)
        self.clientes_dict = clientes_dict or {}
        self.detalle_ventas = detalle_ventas          # referencia mutable compartida con el padre
        self.on_costo_cambiado_cb = on_costo_cambiado_cb
        self.sku = sku
        self.producto = producto

        self.setStyleSheet("""
            QDialog { background-color: #f1f5f9; }
            QWidget { font-family: 'Segoe UI', Arial, sans-serif; color: #334155; }
            QLineEdit, QComboBox {
                border: 1px solid #cbd5e1; border-radius: 5px;
                padding: 4px 8px; font-size: 11px; background-color: white;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
        """)

        raiz = widget.QVBoxLayout(self)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        raiz.addWidget(self._crear_banner())
        raiz.addWidget(self._crear_toolbar())
        raiz.addWidget(self._crear_tarjeta_tabla(), 1)
        raiz.addWidget(self._crear_pie_totales())
        raiz.addLayout(self._crear_acciones())

        self._poblar_tabla()
        self._recalcular_totales()

    # ── construcción de UI ──────────────────────────────────────────────────
    def _tarjeta(self):
        f = widget.QFrame()
        f.setObjectName("tarjeta")
        f.setStyleSheet("#tarjeta { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }")
        return f

    def _crear_banner(self):
        tarjeta = self._tarjeta()
        lay = widget.QVBoxLayout(tarjeta)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        fila_id = widget.QHBoxLayout()
        fila_id.setSpacing(8)
        chip = widget.QLabel(f"SKU: {self.sku}")
        chip.setStyleSheet(
            "background-color: #eff6ff; color: #1d4ed8; font-family: Consolas;"
            " font-weight: 700; font-size: 11px; padding: 2px 8px; border: 1px solid #bfdbfe; border-radius: 9px;"
        )
        fila_id.addWidget(chip)
        fila_id.addStretch(1)
        lay.addLayout(fila_id)

        titulo = widget.QLabel(str(self.producto))
        titulo.setStyleSheet("font-size: 17px; font-weight: 800; color: #0f172a;")
        titulo.setWordWrap(True)
        lay.addWidget(titulo)

        sub = widget.QLabel("Comportamiento comercial consolidado del producto por órdenes de facturación")
        sub.setStyleSheet("font-size: 11px; color: #64748b;")
        lay.addWidget(sub)

        fila_kpi = widget.QHBoxLayout()
        fila_kpi.setSpacing(8)
        fila_kpi.setContentsMargins(0, 4, 0, 0)
        self._kpi_unid, k1 = self._kpi("Total Unidades", "#0f172a", "#f8fafc", "#e2e8f0")
        self._kpi_ventas, k2 = self._kpi("Total Ventas", "#0f172a", "#f8fafc", "#e2e8f0")
        self._kpi_benef, k3 = self._kpi("Total Beneficio", "#047857", "#ecfdf5", "#a7f3d0")
        self._kpi_margen, k4 = self._kpi("Margen % Promedio", "#047857", "#f8fafc", "#e2e8f0")
        for k in (k1, k2, k3, k4):
            fila_kpi.addWidget(k)
        fila_kpi.addStretch(1)
        lay.addLayout(fila_kpi)
        return tarjeta

    def _kpi(self, titulo, color_valor, bg, borde):
        card = widget.QFrame()
        card.setStyleSheet(f"QFrame {{ background-color: {bg}; border: 1px solid {borde}; border-radius: 7px; }}")
        card.setMinimumWidth(140)
        v = widget.QVBoxLayout(card)
        v.setContentsMargins(11, 6, 11, 7)
        v.setSpacing(1)
        t = widget.QLabel(titulo.upper())
        t.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; background: transparent; border: none;")
        val = widget.QLabel("—")
        val.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {color_valor}; background: transparent; border: none;")
        v.addWidget(t)
        v.addWidget(val)
        return val, card

    def _crear_toolbar(self):
        barra = widget.QFrame()
        barra.setStyleSheet("QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }")
        lay = widget.QHBoxLayout(barra)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        self.buscar = widget.QLineEdit()
        self.buscar.setPlaceholderText("Buscar por cliente, cuenta o N° de comprobante…")
        self.buscar.setMaximumWidth(360)
        self.buscar.textChanged.connect(self._aplicar_filtros)
        lay.addWidget(self.buscar)

        lbl_tipo = widget.QLabel("Tipo:")
        lbl_tipo.setStyleSheet("font-size: 11px; color: #64748b;")
        lay.addWidget(lbl_tipo)
        self.filtro_tipo = widget.QComboBox()
        self.filtro_tipo.addItem("Todos (FC / NC)", None)
        self.filtro_tipo.addItem("Facturas (FC)", "FC")
        self.filtro_tipo.addItem("Notas de Crédito (NC)", "NC")
        self.filtro_tipo.currentIndexChanged.connect(self._aplicar_filtros)
        lay.addWidget(self.filtro_tipo)

        lay.addStretch(1)

        self.lbl_mostrando = widget.QLabel()
        self.lbl_mostrando.setStyleSheet("font-size: 11px; color: #475569; font-weight: 600;")
        lay.addWidget(self.lbl_mostrando)

        btn_reset = widget.QPushButton("Limpiar")
        btn_reset.setStyleSheet(
            "QPushButton { background-color: white; color: #475569; border: 1px solid #cbd5e1;"
            " border-radius: 5px; padding: 4px 10px; font-size: 11px; }"
            " QPushButton:hover { background-color: #f1f5f9; }"
        )
        btn_reset.clicked.connect(self._limpiar_filtros)
        lay.addWidget(btn_reset)
        return barra

    def _crear_tarjeta_tabla(self):
        tarjeta = self._tarjeta()
        lay = widget.QVBoxLayout(tarjeta)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.tabla_detalle = widget.QTableWidget()
        self.tabla_detalle.setColumnCount(len(_ENCABEZADOS))
        self.tabla_detalle.setHorizontalHeaderLabels(_ENCABEZADOS)
        self.tabla_detalle.setStyleSheet(_TABLA_QSS)
        self.tabla_detalle.setAlternatingRowColors(True)
        self.tabla_detalle.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla_detalle.verticalHeader().setVisible(False)
        self.tabla_detalle.verticalHeader().setDefaultSectionSize(26)
        self.tabla_detalle.setEditTriggers(widget.QAbstractItemView.DoubleClicked)
        self.tabla_detalle.setItemDelegateForColumn(_D_COSTO, _CostoDetalleDelegate(self.tabla_detalle))
        self.tabla_detalle.cellChanged.connect(self._on_costo_cambiado)

        header = self.tabla_detalle.horizontalHeader()
        header.setStretchLastSection(False)
        modos = {
            _D_NUM: (widget.QHeaderView.Fixed, 40),
            _D_FECHA: (widget.QHeaderView.Interactive, 140),
            _D_CLIENTE: (widget.QHeaderView.Stretch, None),
            _D_CUENTA: (widget.QHeaderView.Interactive, 70),
            _D_TC: (widget.QHeaderView.Fixed, 46),
            _D_NC: (widget.QHeaderView.Interactive, 90),
            _D_UNID: (widget.QHeaderView.Interactive, 64),
            _D_TOTAL: (widget.QHeaderView.Interactive, 130),
            _D_PUNIT: (widget.QHeaderView.Interactive, 125),
            _D_COSTO: (widget.QHeaderView.Interactive, 125),
            _D_BUNIT: (widget.QHeaderView.Interactive, 125),
            _D_BTOT: (widget.QHeaderView.Interactive, 130),
            _D_PCT: (widget.QHeaderView.Interactive, 120),
        }
        for col, (modo, ancho) in modos.items():
            header.setSectionResizeMode(col, modo)
            if ancho is not None:
                self.tabla_detalle.setColumnWidth(col, ancho)

        lay.addWidget(self.tabla_detalle)
        return tarjeta

    def _crear_pie_totales(self):
        barra = widget.QFrame()
        barra.setStyleSheet("QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }")
        lay = widget.QHBoxLayout(barra)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        lbl = widget.QLabel("TOTALES CONSOLIDADOS DE ESTE SKU")
        lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b;")
        lay.addWidget(lbl)
        lay.addStretch(1)

        self._foot_facturas = self._pie_metrica("Facturaciones", "#334155")
        self._foot_venta = self._pie_metrica("Total Venta", "#0f172a")
        self._foot_costo = self._pie_metrica("Costo Total", "#475569")
        self._foot_benef = self._pie_metrica("Beneficio", "#047857")
        self._foot_margen = self._pie_metrica("Margen", "#047857")
        for w in (self._foot_facturas, self._foot_venta, self._foot_costo, self._foot_benef, self._foot_margen):
            lay.addWidget(w[0])
        return barra

    def _pie_metrica(self, titulo, color):
        cont = widget.QWidget()
        h = widget.QHBoxLayout(cont)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        t = widget.QLabel(f"{titulo}:")
        t.setStyleSheet("font-size: 10px; color: #94a3b8; font-weight: 600;")
        v = widget.QLabel("—")
        v.setStyleSheet(f"font-size: 12px; color: {color}; font-weight: 800; font-family: Consolas;")
        h.addWidget(t)
        h.addWidget(v)
        return cont, v

    def _crear_acciones(self):
        fila = widget.QHBoxLayout()
        fila.setContentsMargins(2, 0, 2, 0)
        fila.addStretch(1)

        btn_exportar = widget.QPushButton("  Exportar Detalle (Excel)")
        btn_exportar.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: white; border: none;"
            " border-radius: 6px; padding: 7px 16px; font-size: 11px; font-weight: 700; }"
            " QPushButton:hover { background-color: #0f766e; }"
        )
        btn_exportar.clicked.connect(lambda: self.exportar_detalle(self.sku, self.producto, self.detalle_ventas))
        fila.addWidget(btn_exportar)

        btn_cerrar = widget.QPushButton("Cerrar")
        btn_cerrar.setStyleSheet(
            "QPushButton { background-color: #475569; color: white; border: none;"
            " border-radius: 6px; padding: 7px 16px; font-size: 11px; font-weight: 700; }"
            " QPushButton:hover { background-color: #334155; }"
        )
        btn_cerrar.clicked.connect(self.accept)
        fila.addWidget(btn_cerrar)
        return fila

    # ── datos ────────────────────────────────────────────────────────────────
    @staticmethod
    def _cuenta_str(cuenta_raw):
        try:
            return str(int(float(cuenta_raw))) if cuenta_raw != 'N/A' else 'N/A'
        except (ValueError, TypeError):
            return str(cuenta_raw)

    def _celda(self, texto, alinear_derecha=False, mono=False, negrita=False, fg=None, bg=None, editable=False):
        it = widget.QTableWidgetItem(texto)
        if not editable:
            it.setFlags(it.flags() & ~Qt.Qt.ItemIsEditable)
        if alinear_derecha:
            it.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
        else:
            it.setTextAlignment(Qt.Qt.AlignVCenter | Qt.Qt.AlignLeft)
        fuente = Gui.QFont("Consolas" if mono else "Segoe UI", 8)
        if negrita:
            fuente.setBold(True)
        it.setFont(fuente)
        if fg:
            it.setForeground(fg)
        if bg:
            it.setBackground(bg)
        return it

    def _poblar_tabla(self):
        self.tabla_detalle.blockSignals(True)
        try:
            self.tabla_detalle.setRowCount(len(self.detalle_ventas))
            for i, venta in enumerate(self.detalle_ventas):
                self.tabla_detalle.setRowHeight(i, 26)
                self._pintar_fila(i, venta)
        finally:
            self.tabla_detalle.blockSignals(False)

    def _pintar_fila(self, i, venta):
        beneficio_total = venta['MARGEN_UNITARIO'] * venta['U_VENDIDAS']
        costo_total = venta['PRECIO_COSTO'] * venta['U_VENDIDAS']
        margen_pct = (beneficio_total / costo_total * 100) if costo_total > 0 else 0

        cuenta = self._cuenta_str(venta.get('CUENTA', 'N/A'))
        nombre_cliente = self.clientes_dict.get(cuenta, cuenta)

        num = self._celda(str(i + 1), mono=True, fg=Gui.QColor("#94a3b8"))
        num.setTextAlignment(Qt.Qt.AlignCenter)
        self.tabla_detalle.setItem(i, _D_NUM, num)
        self.tabla_detalle.setItem(i, _D_FECHA, self._celda(str(venta.get('FECHA', 'N/A')), mono=True, fg=Gui.QColor("#475569")))
        self.tabla_detalle.setItem(i, _D_CLIENTE, self._celda(nombre_cliente, negrita=True, fg=Gui.QColor("#1d4ed8")))
        self.tabla_detalle.setItem(i, _D_CUENTA, self._celda(cuenta, mono=True))
        tc = self._celda(str(venta.get('TC', 'N/A')))
        tc.setTextAlignment(Qt.Qt.AlignCenter)
        self.tabla_detalle.setItem(i, _D_TC, tc)
        self.tabla_detalle.setItem(i, _D_NC, self._celda(str(venta.get('NC', 'N/A')), mono=True))
        cant = self._celda(f"{venta['U_VENDIDAS']:,.0f}", alinear_derecha=True, mono=True, negrita=True)
        self.tabla_detalle.setItem(i, _D_UNID, cant)
        self.tabla_detalle.setItem(i, _D_TOTAL, self._celda(_money(venta['TOTAVEN']), alinear_derecha=True, mono=True))
        self.tabla_detalle.setItem(i, _D_PUNIT, self._celda(_money(venta.get('PRECIO_UNITARIO', 0)), alinear_derecha=True, mono=True, fg=Gui.QColor("#64748b")))

        costo_item = self._celda(_money(venta.get('PRECIO_COSTO', 0)), alinear_derecha=True, mono=True, editable=True,
                                 bg=Gui.QColor(255, 251, 235), fg=Gui.QColor(120, 90, 0))
        costo_item.setToolTip("Doble clic para editar el costo unitario. Enter para confirmar.")
        self.tabla_detalle.setItem(i, _D_COSTO, costo_item)

        self._pintar_derivados(i, venta['MARGEN_UNITARIO'], beneficio_total, margen_pct)

    def _pintar_derivados(self, i, margen_unit, beneficio_total, margen_pct):
        bg_u, fg_u = (_VERDE_BG, _VERDE_FG) if margen_unit >= 0 else (_ROJO_BG, _ROJO_FG)
        self.tabla_detalle.setItem(i, _D_BUNIT, self._celda(_money(margen_unit), alinear_derecha=True, mono=True, negrita=True, bg=bg_u, fg=fg_u))
        bg_t, fg_t = (_VERDE_BG, _VERDE_FG) if beneficio_total >= 0 else (_ROJO_BG, _ROJO_FG)
        self.tabla_detalle.setItem(i, _D_BTOT, self._celda(_money(beneficio_total), alinear_derecha=True, mono=True, negrita=True, bg=bg_t, fg=fg_t))
        self.tabla_detalle.setCellWidget(i, _D_PCT, barra_porcentaje(margen_pct))

    # ── filtros ──────────────────────────────────────────────────────────────
    def _aplicar_filtros(self):
        texto = self.buscar.text().strip().lower()
        tipo = self.filtro_tipo.currentData()
        visibles = 0
        for i, venta in enumerate(self.detalle_ventas):
            cuenta = self._cuenta_str(venta.get('CUENTA', 'N/A'))
            cliente = str(self.clientes_dict.get(cuenta, cuenta)).lower()
            nc = str(venta.get('NC', '')).lower()
            tc = str(venta.get('TC', '')).strip().upper()
            ok = (not texto or texto in cliente or texto in cuenta.lower() or texto in nc)
            if tipo is not None:
                ok = ok and (tc == tipo)
            self.tabla_detalle.setRowHidden(i, not ok)
            visibles += int(ok)
        total = len(self.detalle_ventas)
        if visibles == total:
            self.lbl_mostrando.setText(f"Mostrando {total} facturaciones")
        else:
            self.lbl_mostrando.setText(f"Mostrando {visibles} de {total} facturaciones")

    def _limpiar_filtros(self):
        self.buscar.clear()
        self.filtro_tipo.setCurrentIndex(0)
        self._aplicar_filtros()

    # ── totales ──────────────────────────────────────────────────────────────
    def _recalcular_totales(self):
        total_unidades = sum(d['U_VENDIDAS'] for d in self.detalle_ventas)
        total_ventas = sum(d['TOTAVEN'] for d in self.detalle_ventas)
        total_beneficio = sum(d['MARGEN_UNITARIO'] * d['U_VENDIDAS'] for d in self.detalle_ventas)
        costo_total = sum(d['PRECIO_COSTO'] * d['U_VENDIDAS'] for d in self.detalle_ventas)
        margen_pct = (total_beneficio / costo_total * 100) if costo_total else 0

        self._kpi_unid.setText(f"{total_unidades:,.0f} u.")
        self._kpi_ventas.setText(_money(total_ventas))
        self._kpi_benef.setText(_money(total_beneficio))
        self._kpi_margen.setText(_pct(margen_pct))

        self._foot_facturas[1].setText(str(len(self.detalle_ventas)))
        self._foot_venta[1].setText(_money(total_ventas))
        self._foot_costo[1].setText(_money(costo_total))
        self._foot_benef[1].setText(_money(total_beneficio))
        self._foot_margen[1].setText(_pct(margen_pct))
        self._aplicar_filtros()

    def _on_costo_cambiado(self, fila, columna):
        """Recalcula beneficio/margen de la fila y cascadea al padre."""
        if columna != _D_COSTO or fila >= len(self.detalle_ventas):
            return

        costo_item = self.tabla_detalle.item(fila, _D_COSTO)
        if costo_item is None:
            return
        texto = costo_item.text().replace('$', '').replace('.', '').replace(',', '.').strip()
        try:
            nuevo_costo = float(texto)
        except ValueError:
            return

        detalle = self.detalle_ventas[fila]
        precio_venta = detalle.get('PRECIO_UNITARIO', 0)
        unidades = detalle.get('U_VENDIDAS', 0)

        detalle['PRECIO_COSTO'] = nuevo_costo
        nuevo_margen_unit = precio_venta - nuevo_costo
        detalle['MARGEN_UNITARIO'] = nuevo_margen_unit

        beneficio_total = nuevo_margen_unit * unidades
        costo_total = nuevo_costo * unidades
        margen_pct = (beneficio_total / costo_total * 100) if costo_total != 0 else 0

        self.tabla_detalle.blockSignals(True)
        try:
            costo_item.setText(_money(nuevo_costo))
            costo_item.setBackground(Gui.QColor(255, 251, 235))
            costo_item.setForeground(Gui.QColor(120, 90, 0))
            self._pintar_derivados(fila, nuevo_margen_unit, beneficio_total, margen_pct)
        finally:
            self.tabla_detalle.blockSignals(False)

        self._recalcular_totales()

        if self.on_costo_cambiado_cb:
            self.on_costo_cambiado_cb()

    def exportar_detalle(self, sku, producto, detalle_ventas):
        """Exporta el detalle de un producto específico incluyendo nombres de clientes"""
        ruta_archivo, _ = widget.QFileDialog.getSaveFileName(
            self, f"Exportar Detalle {sku}",
            f"detalle_{sku}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Archivos Excel (*.xlsx)"
        )

        if ruta_archivo:
            try:
                datos_exportacion = []
                for venta in detalle_ventas:
                    beneficio_total = venta['MARGEN_UNITARIO'] * venta['U_VENDIDAS']
                    costo_total = venta['PRECIO_COSTO'] * venta['U_VENDIDAS']
                    margen_porcentual = (beneficio_total / costo_total * 100) if costo_total > 0 else 0
                    cuenta = self._cuenta_str(venta.get('CUENTA', 'N/A'))
                    nombre_cliente = self.clientes_dict.get(cuenta, cuenta)

                    datos_exportacion.append({
                        'FECHA': venta.get('FECHA', 'N/A'),
                        'CLIENTE': nombre_cliente,
                        'CUENTA': cuenta,
                        'TC': venta.get('TC', 'N/A'),
                        'NC': venta.get('NC', 'N/A'),
                        'UNIDADES': venta['U_VENDIDAS'],
                        'TOTAL_VENTA': venta['TOTAVEN'],
                        'PRECIO_UNITARIO': venta.get('PRECIO_UNITARIO', 0),
                        'COSTO_UNITARIO': venta.get('PRECIO_COSTO', 0),
                        'BENEFICIO_UNITARIO': venta['MARGEN_UNITARIO'],
                        'BENEFICIO_TOTAL': beneficio_total,
                        'MARGEN_PORCENTUAL': margen_porcentual
                    })

                df_detalle = pd.DataFrame(datos_exportacion)
                df_detalle.to_excel(ruta_archivo, index=False, sheet_name=f"Detalle_{sku}"[:31])
                widget.QMessageBox.information(self, "Éxito", f"Detalle exportado:\n{ruta_archivo}")
            except Exception as e:
                widget.QMessageBox.critical(self, "Error", f"Error al exportar: {e}")
