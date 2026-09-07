import os

import pandas as pd
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import config
from src.controllers import echeq_io
from src.controllers.ProgressBar import EcheqLoadThread
from src.ui.widgets.tarjeta import crear_tarjeta
from src.Views.Echeq.EcheqFormDBF import Form

_ESTADO_COLORES = {
    "activo": ("#d1fae5", "#065f46"),
    "emitido pendiente": ("#fef3c7", "#92400e"),
    "cesion pendiente": ("#dbeafe", "#1e40af"),
    "rechazado": ("#fee2e2", "#991b1b"),
}
_ESTADO_DEFECTO = ("#f1f5f9", "#475569")


def _parse_monto(valor):
    """'$425.000,00' -> 425000.0. Devuelve 0.0 si no se puede parsear."""
    try:
        limpio = str(valor).replace("$", "").replace(".", "").replace(",", ".").strip()
        return float(limpio)
    except (ValueError, TypeError):
        return 0.0


def _fmt_monto(valor):
    return f"$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _fecha_para_orden(valor):
    return pd.to_datetime(str(valor).split(" ")[0], format="%d/%m/%Y", errors="coerce")


class EcheqWindow(widget.QWidget):
    """Control de e-cheques. Widget embebible.

    Las acciones de barra (Nuevo / Guardar / Actualizar / Limpiar) se exponen en
    ``self.acciones_toolbar`` para que las muestre quien lo embeba.
    """

    def __init__(self, df=None, parent=None):
        super().__init__(parent)

        self.filtros = []
        self.modified = False
        self.acciones_toolbar = []
        self.direc = config.ECHEQ_PATH
        self.campos = ["Nro de Cheque", "Echeq id", "Pagador Nombre Apellido/Razón Social",
                        "Monto", "Fecha de Pago", "Fecha de Emisión"]
        self.campos_tabla = self.campos + ["Estado"]
        self.df = pd.DataFrame(columns=echeq_io.COLUMNAS)
        self._hilo_carga = None

        self.setupUI()

        # df pre-cargado (uso legacy). Si no viene, el contenedor llama a
        # cargar_datos_iniciales() cuando corresponda (carga lazy).
        if df is not None and not df.empty:
            self.df = df
            self.modified = True
            self.mostrar_en_tabla(self.df)
            self.status_label.setText("Datos cargados correctamente")

    # ── construcción de UI ──────────────────────────────────────────────────
    def setupUI(self):
        main_layout = widget.QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(8, 8, 8, 8)

        self.crear_toolbar()                    # llena self.acciones_toolbar
        self.crear_seccion_filtros(main_layout)
        self.crear_tabla(main_layout)
        self.crear_status_bar(main_layout)

    def _icono(self, nombre_fa, color):
        if qta is not None:
            return gui.QIcon(qta.icon(nombre_fa, color=color))
        return gui.QIcon()

    def crear_toolbar(self):
        """Construye las QAction de barra (las muestra quien embeba el widget)."""
        nuevo = widget.QAction(self._icono("fa5s.plus", "#2563eb"), "Nuevo", self)
        nuevo.triggered.connect(self.openForm)

        guardar = widget.QAction(self._icono("fa5s.save", "#4f46e5"), "Guardar", self)
        guardar.triggered.connect(self.guardar_archivo)

        actualizar = widget.QAction(self._icono("fa5s.sync-alt", "#2563eb"), "Actualizar", self)
        actualizar.triggered.connect(self.cargar_datos_iniciales)

        limpiar = widget.QAction(self._icono("fa5s.eraser", "#e11d48"), "Limpiar Filtros", self)
        limpiar.triggered.connect(self.limpiar_filtros)

        self.acciones_toolbar = [nuevo, guardar, actualizar, limpiar]

    def crear_seccion_filtros(self, main_layout):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.search", color="#2563eb").pixmap(14, 14))
        tarjeta, cuerpo = crear_tarjeta("Filtros de Búsqueda", icono=icono)

        grid_filtros = widget.QGridLayout()
        grid_filtros.setHorizontalSpacing(16)
        grid_filtros.setVerticalSpacing(6)
        grid_filtros.setColumnStretch(1, 1)
        grid_filtros.setColumnStretch(3, 1)

        for i, campo in enumerate(self.campos):
            row = i // 2
            col = (i % 2) * 2

            label = widget.QLabel(campo)
            label.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
            label.setAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            grid_filtros.addWidget(label, row, col)

            filtro = widget.QLineEdit()
            filtro.setPlaceholderText(f"Buscar en {campo}...")
            filtro.textChanged.connect(self.aplicar_filtros)
            grid_filtros.addWidget(filtro, row, col + 1)

            self.filtros.append(filtro)

        cuerpo.addLayout(grid_filtros)
        main_layout.addWidget(tarjeta)

    def crear_tabla(self, main_layout):
        icono = widget.QLabel()
        if qta is not None:
            icono.setPixmap(qta.icon("fa5s.file-invoice", color="#0369a1").pixmap(14, 14))
        self._badge_conteo = widget.QLabel("0 registros")
        self._badge_conteo.setStyleSheet(
            "background-color: #dbeafe; color: #1d4ed8; font-size: 10px; font-weight: 700;"
            " padding: 1px 8px; border-radius: 8px;"
        )
        cab_extra = widget.QHBoxLayout()
        cab_extra.setSpacing(8)
        cab_extra.addWidget(self._badge_conteo)
        orden_lbl = widget.QLabel("Orden: Fecha de Pago DESC")
        orden_lbl.setStyleSheet("font-size: 10px; color: #94a3b8;")
        cab_extra.addWidget(orden_lbl)
        extra_widget = widget.QWidget()
        extra_widget.setLayout(cab_extra)

        tarjeta, cuerpo = crear_tarjeta("Registros de E-Cheques", extra=extra_widget, icono=icono)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        self.tabla_echeq = widget.QTableWidget()
        self.tabla_echeq.setColumnCount(len(self.campos_tabla) + 1)
        self.tabla_echeq.setHorizontalHeaderLabels(["#"] + self.campos_tabla)
        self.tabla_echeq.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla_echeq.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla_echeq.setAlternatingRowColors(True)
        self.tabla_echeq.setSortingEnabled(True)
        self.tabla_echeq.verticalHeader().setVisible(False)
        self.tabla_echeq.verticalHeader().setDefaultSectionSize(24)
        self.tabla_echeq.itemSelectionChanged.connect(self._actualizar_resumen)

        header = self.tabla_echeq.horizontalHeader()
        header.setStretchLastSection(False)
        self.configurar_columnas_responsivas()
        cuerpo.addWidget(self.tabla_echeq)

        self._resumen = self._crear_resumen_tabla()
        cuerpo.addWidget(self._resumen)

        main_layout.addWidget(tarjeta, 1)

    def _crear_resumen_tabla(self):
        barra = widget.QFrame()
        barra.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #e2e8f0;")
        lay = widget.QHBoxLayout(barra)
        lay.setContentsMargins(10, 5, 10, 5)

        self._lbl_total_mostrado = widget.QLabel("Total Mostrado: 0 registros")
        self._lbl_total_mostrado.setStyleSheet("font-size: 11px; color: #475569; font-weight: 600;")
        self._lbl_promedio = widget.QLabel("Promedio por Cheque: $ 0,00")
        self._lbl_promedio.setStyleSheet("font-size: 11px; color: #64748b;")
        lay.addWidget(self._lbl_total_mostrado)
        lay.addWidget(self._sep())
        lay.addWidget(self._lbl_promedio)
        lay.addStretch(1)

        lbl_suma_titulo = widget.QLabel("SUMA SELECCIONADA:")
        lbl_suma_titulo.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b;")
        self._lbl_suma_seleccionada = widget.QLabel("$ 0,00")
        self._lbl_suma_seleccionada.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #1d4ed8; background-color: white;"
            " border: 1px solid #e2e8f0; border-radius: 4px; padding: 1px 8px;"
        )
        lay.addWidget(lbl_suma_titulo)
        lay.addWidget(self._lbl_suma_seleccionada)
        return barra

    def _sep(self):
        s = widget.QFrame()
        s.setFrameShape(widget.QFrame.VLine)
        s.setStyleSheet("color: #cbd5e1;")
        s.setFixedHeight(14)
        return s

    def configurar_columnas_responsivas(self):
        """Configurar columnas para que sean responsivas"""
        header = self.tabla_echeq.horizontalHeader()
        # [#, Nro de Cheque, Echeq id, Pagador, Monto, Fecha de Pago, Fecha de Emisión, Estado]
        anchos = [40, 110, 150, None, 130, 100, 130, 110]
        for i, ancho in enumerate(anchos):
            if ancho is None:
                header.setSectionResizeMode(i, widget.QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(i, widget.QHeaderView.Interactive)
                self.tabla_echeq.setColumnWidth(i, ancho)

    def crear_status_bar(self, main_layout):
        """Barra de estado propia (fila de labels al pie del widget)."""
        barra = widget.QFrame()
        barra.setObjectName("echeqStatus")
        fila = widget.QHBoxLayout(barra)
        fila.setContentsMargins(8, 4, 8, 4)
        self.status_label = widget.QLabel("Listo")
        self.contador_label = widget.QLabel("0 registros")
        fila.addWidget(self.status_label)
        fila.addStretch()
        fila.addWidget(self.contador_label)
        main_layout.addWidget(barra)

    # ── carga de datos ───────────────────────────────────────────────────────
    def limpiar_filtros(self):
        """Limpiar todos los filtros"""
        for filtro in self.filtros:
            filtro.clear()
        self.status_label.setText("Filtros limpiados")

    def cargar_datos_iniciales(self):
        """Carga (o actualiza) los e-cheques en background. La lectura de Excel
        está cacheada por archivo (ver `echeq_io`): solo relee del disco los
        que son nuevos o cambiaron desde la última vez."""
        if self._hilo_carga is not None and self._hilo_carga.isRunning():
            return
        if not os.path.exists(self.direc):
            widget.QMessageBox.warning(self, "Advertencia", f"El directorio {self.direc} no existe")
            return

        self.status_label.setText("Cargando E-cheques…")
        for accion in self.acciones_toolbar:
            accion.setEnabled(False)

        self._hilo_carga = EcheqLoadThread()
        self._hilo_carga.completado.connect(self._on_datos_cargados)
        self._hilo_carga.start()

    def _on_datos_cargados(self, df):
        for accion in self.acciones_toolbar:
            accion.setEnabled(True)
        self.df = df
        self.modified = True
        self.mostrar_en_tabla(self.df)
        self.status_label.setText("Datos cargados correctamente")

    # ── tabla ────────────────────────────────────────────────────────────────
    def mostrar_en_tabla(self, df):
        """Mostrar contenido en la tabla con formato mejorado"""
        df_mostrar = df.loc[:, [col for col in self.campos_tabla if col in df.columns]].copy()
        if "Fecha de Pago" in df_mostrar.columns:
            orden = df_mostrar["Fecha de Pago"].apply(_fecha_para_orden)
            df_mostrar = df_mostrar.assign(_orden=orden).sort_values(
                "_orden", ascending=False, na_position="last"
            ).drop(columns="_orden")

        total_registros = len(df_mostrar)
        self._badge_conteo.setText(f"{total_registros:,} registros".replace(",", "."))
        self.contador_label.setText(f"{total_registros} registros")

        self.tabla_echeq.setSortingEnabled(False)
        self.tabla_echeq.setRowCount(0)

        fuente_mono = gui.QFont("Consolas", 8)
        for i, (_, fila) in enumerate(df_mostrar.iterrows()):
            self.tabla_echeq.insertRow(i)

            item_n = widget.QTableWidgetItem(str(i + 1))
            item_n.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
            item_n.setForeground(gui.QColor("#94a3b8"))
            self.tabla_echeq.setItem(i, 0, item_n)

            for j, campo in enumerate(self.campos_tabla, start=1):
                valor = fila.get(campo, "")
                item = widget.QTableWidgetItem("" if pd.isna(valor) else str(valor))

                if campo == "Monto":
                    item.setText(_fmt_monto(_parse_monto(valor)))
                    item.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
                    item.setForeground(gui.QColor("#0f172a"))
                    item.setFont(gui.QFont("Consolas", 8, gui.QFont.Bold))
                elif campo in ("Fecha de Pago", "Fecha de Emisión"):
                    item.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
                    item.setForeground(gui.QColor("#334155"))
                    item.setFont(fuente_mono)
                elif campo in ("Nro de Cheque", "Echeq id"):
                    item.setForeground(gui.QColor("#1d4ed8" if campo == "Echeq id" else "#0f172a"))
                    item.setFont(fuente_mono)
                elif campo == "Estado":
                    item.setTextAlignment(core.Qt.AlignCenter | core.Qt.AlignVCenter)
                    bg, fg = _ESTADO_COLORES.get(str(valor).strip().lower(), _ESTADO_DEFECTO)
                    item.setBackground(gui.QColor(bg))
                    item.setForeground(gui.QColor(fg))
                    item.setFont(gui.QFont("Segoe UI", 8, gui.QFont.Bold))

                self.tabla_echeq.setItem(i, j, item)

        self.tabla_echeq.setSortingEnabled(True)
        self._actualizar_resumen(df_mostrar)

    def _actualizar_resumen(self, df_mostrar=None):
        if df_mostrar is None:
            # llamado por itemSelectionChanged: solo actualizar la suma seleccionada
            self._actualizar_suma_seleccionada()
            return

        total = len(df_mostrar)
        self._lbl_total_mostrado.setText(f"Total Mostrado: {total} registros")
        if total and "Monto" in df_mostrar.columns:
            montos = df_mostrar["Monto"].apply(_parse_monto)
            promedio = montos.sum() / total
            self._lbl_promedio.setText(f"Promedio por Cheque: {_fmt_monto(promedio)}")
        else:
            self._lbl_promedio.setText("Promedio por Cheque: $ 0,00")
        self._actualizar_suma_seleccionada()

    def _actualizar_suma_seleccionada(self):
        filas = {i.row() for i in self.tabla_echeq.selectedIndexes()}
        col_monto = self.campos_tabla.index("Monto") + 1
        suma = 0.0
        for fila in filas:
            item = self.tabla_echeq.item(fila, col_monto)
            if item is not None:
                suma += _parse_monto(item.text())
        self._lbl_suma_seleccionada.setText(_fmt_monto(suma))

    def aplicar_filtros(self):
        """Aplicar filtros mejorado con feedback"""
        textos_filtros = [filtro.text().strip().lower() for filtro in self.filtros]

        if not any(textos_filtros):
            self.mostrar_en_tabla(self.df)
            self.status_label.setText("Mostrando todos los registros")
            return

        df_filtrado = self.df.copy()
        filtros_activos = []

        for i, texto in enumerate(textos_filtros):
            if texto:
                columna = self.campos[i]
                if columna in df_filtrado.columns:
                    df_filtrado = df_filtrado[
                        df_filtrado[columna].astype(str).str.contains(texto, case=False, na=False)
                    ]
                    filtros_activos.append(f"{columna}: '{texto}'")

        self.mostrar_en_tabla(df_filtrado)

        if filtros_activos:
            self.status_label.setText(
                f"Filtros activos: {', '.join(filtros_activos[:2])}{'...' if len(filtros_activos) > 2 else ''}"
            )

    def hay_cambios_sin_guardar(self):
        """Para que la ventana contenedora pregunte antes de cerrar la app."""
        return self.modified

    def guardar_archivo(self):
        ruta_archivo = os.path.join(config.ECHEQ_PATH, 'Echeqs_sistema.xlsx')

        if ruta_archivo:
            try:
                self.df.to_excel(ruta_archivo, index=False)
                msg_box = widget.QMessageBox()
                msg_box.setIcon(widget.QMessageBox.Information)
                msg_box.setWindowTitle("Informe Generado")
                msg_box.setText(f"El informe se guardó correctamente en:\n{ruta_archivo}")
                msg_box.setStandardButtons(widget.QMessageBox.Ok)
                msg_box.exec_()
                self.status_label.setText("Archivo guardado correctamente")
            except Exception as e:
                widget.QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo: {str(e)}")

    def openForm(self):
        self.formulario = Form(self.df.columns)
        if self.formulario.exec_() == widget.QDialog.Accepted:
            datos = self.formulario.obtener_datos()
            nueva_fila = pd.DataFrame([datos], columns=self.campos)
            self.df = pd.concat([self.df, nueva_fila], ignore_index=True)
            self.mostrar_en_tabla(self.df)
            self.modified = True
