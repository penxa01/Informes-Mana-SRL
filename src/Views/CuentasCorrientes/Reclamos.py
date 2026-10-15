"""Ventana modal de reclamos de deuda: alta de un reclamo + tabla de reclamos activos."""
import getpass

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import cuentas_corrientes_io as cc_io
from src.controllers import reclamos_db as rdb
from src.controllers.vendedores import VENDEDORES, nombre_vendedor
from src.ui.widgets.tarjeta import crear_tarjeta
from src.Views.CuentasCorrientes.formato import fmt_monto

# estado -> (fondo, texto)
_ESTADO_COLORES = {
    "SIN RESPUESTA": ("#fee2e2", "#991b1b"),
    "CONTACTADO": ("#dbeafe", "#1e40af"),
    "PENDIENTE DE O/P": ("#fef3c7", "#92400e"),
    "RESUELTO": ("#d1fae5", "#065f46"),
}
_COLUMNAS_FACTURAS = ["", "Emisión", "Comprobante", "Saldo"]
_COLUMNAS_RECLAMOS = ["ID", "Cliente", "Teléfono", "Vendedor", "Facturas", "Saldo", "Creado", "Estado"]
_COL_ESTADO = 7


def _estilo_estado(estado):
    fondo, texto = _ESTADO_COLORES.get(estado, ("#f1f5f9", "#475569"))
    return (f"QComboBox {{ background-color: {fondo}; color: {texto}; font-weight: 700; "
            f"font-size: 10px; border: 1px solid {texto}; border-radius: 4px; padding: 1px 6px; }}")


class ReclamosDialog(widget.QDialog):
    """:param con: conexión abierta a la base de Pedidos (el diálogo commitea/revierte,
        pero la cierra quien lo creó).
    :param clientes: DataFrame de ctaclien: se pueden reclamar **todos** los clientes,
        no solo los que hoy figuran en la grilla de deudores.
    :param cuenta_inicial: cuenta a preseleccionar (el cliente elegido en la grilla).
    """

    def __init__(self, con, ctacorr, clientes, fecha_desde, cuenta_inicial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reclamos de deuda")
        self.setModal(True)
        self.resize(1020, 760)

        self._con = con
        self._ctacorr = ctacorr
        self._clientes = clientes
        self._desde = fecha_desde
        self._detalle = None          # facturas del cliente elegido (DataFrame)
        self._usuario = getpass.getuser()

        lay = widget.QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self._crear_form())
        lay.addWidget(self._crear_activos(), 1)

        self.status = widget.QLabel("Listo")
        self.status.setStyleSheet("font-size: 11px; color: #64748b;")
        cerrar = widget.QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        pie = widget.QHBoxLayout()
        pie.addWidget(self.status, 1)
        pie.addWidget(cerrar)
        lay.addLayout(pie)

        self._cargar_clientes()
        self._refrescar_activos()
        if cuenta_inicial is not None:
            i = self.combo_cliente.findData(int(cuenta_inicial))
            if i >= 0:
                self.combo_cliente.setCurrentIndex(i)

    # ── UI: alta ─────────────────────────────────────────────────────────────
    def _etiqueta(self, texto):
        e = widget.QLabel(texto)
        e.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
        e.setAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
        return e

    def _crear_form(self):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.gavel", color="#d97706").pixmap(14, 14))
        tarjeta, cuerpo = crear_tarjeta("Nuevo reclamo", icono=icono)

        self.combo_cliente = widget.QComboBox()
        self.combo_cliente.setEditable(True)
        self.combo_cliente.setInsertPolicy(widget.QComboBox.NoInsert)
        self.combo_cliente.completer().setFilterMode(core.Qt.MatchContains)
        self.combo_cliente.completer().setCaseSensitivity(core.Qt.CaseInsensitive)
        self.combo_cliente.currentIndexChanged.connect(self._on_cliente)

        self.combo_vendedor = widget.QComboBox()
        self.combo_vendedor.addItem("— Seleccionar —", None)
        for codigo, nombre in VENDEDORES.items():
            self.combo_vendedor.addItem(nombre, codigo)

        self.edit_telefono = widget.QLineEdit()
        self.edit_telefono.setPlaceholderText("Teléfono del cliente")
        self.lbl_origen_tel = widget.QLabel("")
        self.lbl_origen_vendedor = widget.QLabel("")

        grid = widget.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.addWidget(self._etiqueta("Cliente"), 0, 0)
        grid.addWidget(self.combo_cliente, 0, 1, 1, 2)
        grid.addWidget(self._etiqueta("Vendedor"), 1, 0)
        grid.addWidget(self.combo_vendedor, 1, 1)
        grid.addWidget(self.lbl_origen_vendedor, 1, 2)
        grid.addWidget(self._etiqueta("Teléfono"), 2, 0)
        grid.addWidget(self.edit_telefono, 2, 1)
        grid.addWidget(self.lbl_origen_tel, 2, 2)
        cuerpo.addLayout(grid)

        cab = widget.QHBoxLayout()
        cab.addWidget(self._etiqueta("Facturas a reclamar"))
        self.chk_todas = widget.QCheckBox("Marcar todas")
        self.chk_todas.toggled.connect(self._marcar_todas)
        cab.addWidget(self.chk_todas)
        cab.addStretch(1)
        self.lbl_seleccion = widget.QLabel("0 facturas · $ 0,00")
        self.lbl_seleccion.setStyleSheet("font-size: 11px; font-weight: 700; color: #0f172a;")
        cab.addWidget(self.lbl_seleccion)
        cuerpo.addLayout(cab)

        self.lbl_sin_facturas = widget.QLabel("")
        self.lbl_sin_facturas.setWordWrap(True)
        self.lbl_sin_facturas.setStyleSheet("font-size: 10px; color: #d97706; font-weight: 700;")
        cuerpo.addWidget(self.lbl_sin_facturas)

        self.tabla_facturas = widget.QTableWidget(0, len(_COLUMNAS_FACTURAS))
        self.tabla_facturas.setHorizontalHeaderLabels(_COLUMNAS_FACTURAS)
        self.tabla_facturas.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla_facturas.setSelectionMode(widget.QAbstractItemView.NoSelection)
        self.tabla_facturas.verticalHeader().setVisible(False)
        self.tabla_facturas.verticalHeader().setDefaultSectionSize(24)
        self.tabla_facturas.setMinimumHeight(150)
        self.tabla_facturas.setMaximumHeight(190)
        h = self.tabla_facturas.horizontalHeader()
        h.setSectionResizeMode(2, widget.QHeaderView.Stretch)
        for col, ancho in ((0, 30), (1, 100), (3, 130)):
            h.setSectionResizeMode(col, widget.QHeaderView.Fixed)
            self.tabla_facturas.setColumnWidth(col, ancho)
        self.tabla_facturas.itemChanged.connect(self._actualizar_seleccion)
        cuerpo.addWidget(self.tabla_facturas)

        self.btn_crear = widget.QPushButton(" Crear reclamo")
        if qta is not None:
            self.btn_crear.setIcon(gui.QIcon(qta.icon("fa5s.plus-circle", color="#ffffff")))
        self.btn_crear.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-weight: 700; "
            "border-radius: 4px; padding: 5px 16px; } QPushButton:hover { background-color: #1d4ed8; }"
        )
        self.btn_crear.clicked.connect(self._crear)
        fila = widget.QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.btn_crear)
        cuerpo.addLayout(fila)
        return tarjeta

    # ── UI: reclamos activos ─────────────────────────────────────────────────
    def _crear_activos(self):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.tasks", color="#0369a1").pixmap(14, 14))
        self.chk_resueltos = widget.QCheckBox("Mostrar resueltos")
        self.chk_resueltos.toggled.connect(self._refrescar_activos)
        tarjeta, cuerpo = crear_tarjeta("Reclamos activos", extra=self.chk_resueltos, icono=icono)
        cuerpo.setContentsMargins(0, 0, 0, 0)

        self.tabla = widget.QTableWidget(0, len(_COLUMNAS_RECLAMOS))
        self.tabla.setHorizontalHeaderLabels(_COLUMNAS_RECLAMOS)
        self.tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(1, widget.QHeaderView.Stretch)
        for col, ancho in ((0, 45), (2, 120), (3, 130), (4, 75), (5, 120), (6, 105), (7, 150)):
            h.setSectionResizeMode(col, widget.QHeaderView.Fixed)
            self.tabla.setColumnWidth(col, ancho)
        cuerpo.addWidget(self.tabla)
        return tarjeta

    # ── datos del form ───────────────────────────────────────────────────────
    def _cargar_clientes(self):
        self.combo_cliente.blockSignals(True)
        self.combo_cliente.clear()
        self.combo_cliente.addItem("", None)
        for etiqueta, cuenta in cc_io.opciones_clientes(self._clientes):
            self.combo_cliente.addItem(etiqueta, cuenta)
        self.combo_cliente.setCurrentIndex(0)
        self.combo_cliente.blockSignals(False)

    def _cuenta_elegida(self):
        """Cuenta del cliente elegido, o ``None`` si el texto no corresponde a un
        cliente de la lista (el combo es editable: puede haber texto suelto)."""
        i = self.combo_cliente.findText(self.combo_cliente.currentText().strip(), core.Qt.MatchFixedString)
        return self.combo_cliente.itemData(i) if i > 0 else None

    def _on_cliente(self, *_):
        cuenta = self._cuenta_elegida()
        self.tabla_facturas.blockSignals(True)
        self.tabla_facturas.setRowCount(0)
        self.tabla_facturas.blockSignals(False)
        self.chk_todas.setChecked(False)
        self._detalle = None

        if cuenta is None:
            self.edit_telefono.clear()
            self.lbl_origen_tel.setText("")
            self.lbl_origen_vendedor.setText("")
            self.combo_vendedor.setCurrentIndex(0)
            self.lbl_sin_facturas.setText("")
            self._actualizar_seleccion()
            return

        datos = cc_io.datos_cliente(self._clientes, cuenta)
        self._rotular(self.lbl_origen_tel, bool(datos["telefono"]), "Tomado de CTACLIEN (podés corregirlo)",
                      "Sin teléfono en CTACLIEN: ingresalo a mano")
        self.edit_telefono.setText(datos["telefono"])

        # El vendedor se asigna solo, según CTACLIEN (se puede corregir a mano).
        i = self.combo_vendedor.findData(datos["vendedor_codigo"])
        self.combo_vendedor.setCurrentIndex(i if i >= 0 else 0)
        codigo = datos["vendedor_codigo"]
        self._rotular(self.lbl_origen_vendedor, i >= 0, "Asignado automáticamente según CTACLIEN",
                      f"CTACLIEN tiene el vendedor {codigo}, que no figura en la lista: seleccionalo"
                      if codigo is not None else "Sin vendedor en CTACLIEN: seleccionalo")

        self._detalle = cc_io.detalle_facturas(self._ctacorr, cuenta, self._desde)
        self.lbl_sin_facturas.setText(
            "" if len(self._detalle) else
            f"Este cliente no tiene facturas pendientes desde el {self._desde.strftime('%d/%m/%Y')}. "
            "Si buscás deuda anterior, cambiá «Analizar facturas desde» en el panel."
        )
        self._poblar_facturas(cuenta)

    @staticmethod
    def _rotular(label, ok, texto_ok, texto_falta):
        """Texto de ayuda al lado de un campo: verde si se completó solo, naranja si falta."""
        label.setText(texto_ok if ok else texto_falta)
        label.setStyleSheet("font-size: 10px; color: #059669;" if ok
                            else "font-size: 10px; color: #d97706; font-weight: 700;")

    def _releer_facturas(self):
        """Refresca qué facturas están ya en un reclamo, sin tocar teléfono ni vendedor."""
        cuenta = self._cuenta_elegida()
        if cuenta is not None and self._detalle is not None:
            self.chk_todas.setChecked(False)
            self._poblar_facturas(cuenta)

    def _poblar_facturas(self, cuenta):
        en_reclamo = rdb.facturas_reclamadas(self._con)
        self.tabla_facturas.blockSignals(True)
        self.tabla_facturas.setRowCount(len(self._detalle))
        mono = gui.QFont("Consolas", 8)
        for i, f in enumerate(self._detalle.itertuples(index=False)):
            reclamo = en_reclamo.get((cuenta, f.Clase, int(f.NroEst), int(f.NC)))
            marca = widget.QTableWidgetItem()
            emision = widget.QTableWidgetItem(f.Emisión.strftime("%d/%m/%Y"))
            comp = widget.QTableWidgetItem(f.Comprobante)
            saldo = widget.QTableWidgetItem(fmt_monto(f.Saldo))
            for it in (emision, comp, saldo):
                it.setFont(mono)
            emision.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            saldo.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            if reclamo is None:
                marca.setFlags(core.Qt.ItemIsEnabled | core.Qt.ItemIsUserCheckable)
                marca.setCheckState(core.Qt.Unchecked)
            else:   # ya está en un reclamo activo: no se puede volver a reclamar
                marca.setFlags(core.Qt.NoItemFlags)
                comp.setText(f"{f.Comprobante}   (en reclamo #{reclamo})")
                for it in (emision, comp, saldo):
                    it.setFlags(core.Qt.NoItemFlags)
                    it.setForeground(gui.QColor("#94a3b8"))
            for col, it in enumerate((marca, emision, comp, saldo)):
                self.tabla_facturas.setItem(i, col, it)
        self.tabla_facturas.blockSignals(False)
        self._actualizar_seleccion()

    def _marcar_todas(self, marcar):
        self.tabla_facturas.blockSignals(True)
        for i in range(self.tabla_facturas.rowCount()):
            it = self.tabla_facturas.item(i, 0)
            if it.flags() & core.Qt.ItemIsUserCheckable:
                it.setCheckState(core.Qt.Checked if marcar else core.Qt.Unchecked)
        self.tabla_facturas.blockSignals(False)
        self._actualizar_seleccion()

    def _filas_marcadas(self):
        return [i for i in range(self.tabla_facturas.rowCount())
                if self.tabla_facturas.item(i, 0).checkState() == core.Qt.Checked]

    def _actualizar_seleccion(self, *_):
        marcadas = self._filas_marcadas()
        total = float(self._detalle.iloc[marcadas]["Saldo"].sum()) if marcadas and self._detalle is not None else 0.0
        self.lbl_seleccion.setText(f"{len(marcadas)} facturas · {fmt_monto(total)}")

    # ── alta ─────────────────────────────────────────────────────────────────
    def _crear(self):
        cuenta = self._cuenta_elegida()
        facturas = []
        if cuenta is not None and self._detalle is not None:
            for _, f in self._detalle.iloc[self._filas_marcadas()].iterrows():
                facturas.append({
                    "tc": f["TC"], "clase": f["Clase"], "nro_est": int(f["NroEst"]), "nc": int(f["NC"]),
                    "fecha_emision": f["Emisión"].date(), "total": f["Total"], "saldo": f["Saldo"],
                })
        codigo = self.combo_vendedor.currentData()
        try:
            id_reclamo = rdb.crear_reclamo(
                self._con, cuenta=cuenta,
                cliente=self.combo_cliente.currentText().rsplit(" (", 1)[0] if cuenta is not None else "",
                telefono=self.edit_telefono.text(), vendedor_codigo=codigo,
                vendedor_nombre=nombre_vendedor(codigo) or "", facturas=facturas, creado_por=self._usuario,
            )
            self._con.commit()
        except ValueError as e:        # validación / regla de negocio: mensaje para el usuario
            self._con.rollback()
            widget.QMessageBox.warning(self, "Reclamo", str(e))
            return
        except Exception as e:         # base caída, etc.
            self._con.rollback()
            widget.QMessageBox.critical(self, "Reclamo", f"No se pudo guardar el reclamo:\n{e}")
            return

        self.status.setText(f"Reclamo #{id_reclamo} creado ({len(facturas)} facturas).")
        self._refrescar_activos()
        self._releer_facturas()     # las recién reclamadas quedan bloqueadas

    # ── reclamos activos ─────────────────────────────────────────────────────
    def _refrescar_activos(self, *_):
        try:
            df = rdb.listar_reclamos(self._con, incluir_resueltos=self.chk_resueltos.isChecked())
        except Exception as e:
            self._con.rollback()
            widget.QMessageBox.critical(self, "Reclamos", f"No se pudieron leer los reclamos:\n{e}")
            return
        self.tabla.setRowCount(0)    # descarta también los combos de estado de la carga anterior
        self.tabla.setRowCount(len(df))
        mono = gui.QFont("Consolas", 8)
        for i, r in enumerate(df.itertuples(index=False)):
            celdas = [
                (f"#{r.id_reclamo}", core.Qt.AlignCenter), (r.cliente, core.Qt.AlignLeft),
                (r.telefono or "", core.Qt.AlignLeft), (r.vendedor, core.Qt.AlignLeft),
                (str(r.n_facturas), core.Qt.AlignCenter), (fmt_monto(r.saldo), core.Qt.AlignRight),
                (r.creado.strftime("%d/%m/%Y"), core.Qt.AlignCenter),
            ]
            for col, (texto, alin) in enumerate(celdas):
                it = widget.QTableWidgetItem(texto)
                it.setTextAlignment(alin | core.Qt.AlignVCenter)
                if col in (0, 5, 6):
                    it.setFont(mono)
                if col == 4:
                    it.setToolTip(r.comprobantes)
                self.tabla.setItem(i, col, it)
            self.tabla.setCellWidget(i, _COL_ESTADO, self._combo_estado(r.id_reclamo, r.estado))

    def _combo_estado(self, id_reclamo, estado):
        combo = widget.QComboBox()
        combo.addItems(rdb.ESTADOS)
        combo.setCurrentText(estado)
        combo.setStyleSheet(_estilo_estado(estado))
        combo.currentTextChanged.connect(lambda nuevo, c=combo, rid=id_reclamo: self._cambiar_estado(c, rid, nuevo))
        return combo

    def _cambiar_estado(self, combo, id_reclamo, nuevo):
        try:
            rdb.cambiar_estado(self._con, id_reclamo, nuevo)
            self._con.commit()
        except Exception as e:
            self._con.rollback()
            widget.QMessageBox.critical(self, "Reclamo", f"No se pudo cambiar el estado:\n{e}")
            self._refrescar_activos()
            return
        combo.setStyleSheet(_estilo_estado(nuevo))
        self.status.setText(f"Reclamo #{id_reclamo}: {nuevo}")
        if nuevo == rdb.ESTADO_FINAL:
            if not self.chk_resueltos.isChecked():
                core.QTimer.singleShot(0, self._refrescar_activos)   # sale de la lista de activos
            self._releer_facturas()  # sus facturas vuelven a ser reclamables
