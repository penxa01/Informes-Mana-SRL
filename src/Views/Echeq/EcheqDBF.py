import PyQt5.QtWidgets as widget
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import pandas as pd
from src.Views.Echeq.EcheqFormDBF import Form
import os
from src.controllers.ProgressBar import InfoProgressBarWindow

class EcheqWindow(widget.QMainWindow):  # Cambiado a QMainWindow para mejor control
    def __init__(self, df=None):
        super().__init__()
        self.setWindowTitle("Control de E-cheques - Sistema Avanzado")
        self.setGeometry(100, 100, 1100, 650)  # Ventana más grande
        self.setMinimumSize(1000, 600)  # Tamaño mínimo

        # Variables de estado
        self.index = 0
        self.filtros = []
        self.modified = False
        self.direc = 'd:/tiempo/E-cheqs'
        self.campos = ["Nro de Cheque","Echeq id", "Pagador Nombre Apellido/Razón Social", "Monto", "Fecha de Pago","Fecha de Emisión"]
        self.df = pd.DataFrame(columns=['Pagador Nombre Apellido/Razón Social', 'Unnamed: 1', 'Pagador Cuit','Beneficiario Cuit', 'Beneficiario Nombre Apellido/Razón Social','Tenedor Cuit', 'Tenedor Nombre Apellido/Razón Social', 'Banco Emisor','CMC7', 'Endoso: fecha y hora', 'Endoso: tipo', 'Endoso: Estado','Endoso: tipo de documento beneficiario','Endoso: número de documento beneficiario','Endoso: Razón social / Nombre y apellido beneficiario','Endoso: tipo de documento emisor del endoso','Endoso: número de documento emisor del endoso','Endoso: Razón social / Nombre y emisor del endoso', 'Agrupador ID','Nro de Cheque', 'Echeq id', 'Código Visualización', 'Fecha de Emisión','Fecha de Pago', 'Tipo', 'Carácter', 'Modo', 'Monto', 'Estado','Concepto', 'Motivo de Pago', 'Motivo de Repudio en Emisión','Código de Referencia 1', 'Referencia 1', 'Código de Referencia 2','Referencia 2', 'Código de Referencia 3', 'Unnamed: 37', 'Referencia 3','Codigo de banco', 'Sucursal', 'Código Postal', 'Nro de cuenta','Emisor Cuit', 'Razón Social Emisor'])

        # Configurar interfaz
        self.setupUI()
        self.setStyleSheet(self.getStyleSheet())

        # Usar df pre-cargado o cargar desde disco
        if df is not None and not df.empty:
            self.df = df
            self.modified = True
            self.mostrar_en_tabla(self.df)
            self.status_label.setText("Datos cargados correctamente")
        else:
            self.cargar_datos_iniciales()

    def setupUI(self):
        """Configurar la interfaz de usuario"""
        # Widget central
        central_widget = widget.QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = widget.QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Crear barra de herramientas
        self.crear_toolbar()
        
        # Crear sección de filtros
        self.crear_seccion_filtros(main_layout)
        
        # Crear tabla
        self.crear_tabla(main_layout)
        
        # Crear barra de estado
        self.crear_status_bar()

    def crear_toolbar(self):
        """Crear barra de herramientas moderna"""
        toolbar = self.addToolBar("Herramientas")
        toolbar.setToolButtonStyle(core.Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(core.QSize(24, 24))
        
        # Botón Nuevo
        nuevo_action = widget.QAction("➕ Nuevo", self)
        nuevo_action.setStatusTip("Agregar nuevo e-cheque")
        nuevo_action.triggered.connect(self.openForm)
        toolbar.addAction(nuevo_action)
        
        toolbar.addSeparator()
        
        # Botón Guardar
        guardar_action = widget.QAction("💾 Guardar", self)
        guardar_action.setStatusTip("Guardar cambios")
        guardar_action.triggered.connect(self.guardar_archivo)
        toolbar.addAction(guardar_action)
        
        # Botón Actualizar
        actualizar_action = widget.QAction("🔄 Actualizar", self)
        actualizar_action.setStatusTip("Recargar datos")
        actualizar_action.triggered.connect(self.cargar_datos_iniciales)
        toolbar.addAction(actualizar_action)
        
        toolbar.addSeparator()
        
        # Botón Limpiar Filtros
        limpiar_action = widget.QAction("🗑️ Limpiar Filtros", self)
        limpiar_action.setStatusTip("Limpiar todos los filtros")
        limpiar_action.triggered.connect(self.limpiar_filtros)
        toolbar.addAction(limpiar_action)
        
        # Spacer
        spacer = widget.QWidget()
        spacer.setSizePolicy(widget.QSizePolicy.Expanding, widget.QSizePolicy.Expanding)
        toolbar.addWidget(spacer)
        
        # Botón Minimizar
        minimizar_action = widget.QAction("➖ Minimizar", self)
        minimizar_action.setStatusTip("Minimizar ventana")
        minimizar_action.triggered.connect(self.showMinimized)
        toolbar.addAction(minimizar_action)

    def crear_seccion_filtros(self, main_layout):
        """Crear sección de filtros mejorada"""
        # Frame para filtros
        filtros_frame = widget.QFrame()
        filtros_frame.setFrameStyle(widget.QFrame.StyledPanel)
        filtros_frame.setLineWidth(1)
        
        filtros_layout = widget.QVBoxLayout(filtros_frame)
        
        # Título de sección
        titulo_filtros = widget.QLabel("🔍 FILTROS DE BÚSQUEDA")
        titulo_filtros.setObjectName("titulo_seccion")
        filtros_layout.addWidget(titulo_filtros)
        
        # Grid layout para los filtros (2 columnas)
        grid_filtros = widget.QGridLayout()
        grid_filtros.setSpacing(10)
        
        # Crear filtros en grid 2x3
        for i, campo in enumerate(self.campos):
            row = i // 2
            col = (i % 2) * 2  # 0 o 2 para dejar espacio para etiquetas
            
            # Etiqueta
            label = widget.QLabel(campo)
            label.setObjectName("label_filtro")
            grid_filtros.addWidget(label, row, col)
            
            # Campo de filtro
            filtro = widget.QLineEdit()
            filtro.setPlaceholderText(f"Buscar en {campo}...")
            filtro.setObjectName("campo_filtro")
            filtro.textChanged.connect(self.aplicar_filtros)
            grid_filtros.addWidget(filtro, row, col + 1)
            
            self.filtros.append(filtro)
        
        filtros_layout.addLayout(grid_filtros)
        main_layout.addWidget(filtros_frame)

    def crear_tabla(self, main_layout):
        """Crear tabla mejorada"""
        # Frame para tabla
        tabla_frame = widget.QFrame()
        tabla_frame.setFrameStyle(widget.QFrame.StyledPanel)
        
        tabla_layout = widget.QVBoxLayout(tabla_frame)
        
        # Título de sección con contador
        self.titulo_tabla = widget.QLabel("📊 REGISTROS DE E-CHEQUES")
        self.titulo_tabla.setObjectName("titulo_seccion")
        tabla_layout.addWidget(self.titulo_tabla)
        
        # Tabla
        self.tabla_echeq = widget.QTableWidget()
        self.tabla_echeq.setObjectName("tabla_principal")
        
        # Configurar tabla
        self.tabla_echeq.setColumnCount(len(self.campos))
        self.tabla_echeq.setHorizontalHeaderLabels(self.campos)
        
        # Configurar comportamiento de la tabla
        self.tabla_echeq.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla_echeq.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla_echeq.setAlternatingRowColors(True)
        self.tabla_echeq.setSortingEnabled(True)
        
        # Configurar header horizontal
        header = self.tabla_echeq.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(widget.QHeaderView.Interactive)
        
        # Configurar ancho de columnas responsivo
        self.configurar_columnas_responsivas()
        
        tabla_layout.addWidget(self.tabla_echeq)
        main_layout.addWidget(tabla_frame)

    def configurar_columnas_responsivas(self):
        """Configurar columnas para que sean responsivas"""
        header = self.tabla_echeq.horizontalHeader()
        
        # Anchos mínimos y preferidos
        anchos = [120, 150, 300, 120, 140, 140]  # Para las 6 columnas
        
        for i, ancho in enumerate(anchos):
            if i < len(self.campos):
                self.tabla_echeq.setColumnWidth(i, ancho)
                header.setSectionResizeMode(i, widget.QHeaderView.Interactive)

    def crear_status_bar(self):
        """Crear barra de estado"""
        self.status_bar = self.statusBar()
        
        # Label para mostrar información
        self.status_label = widget.QLabel("Listo")
        self.status_bar.addWidget(self.status_label)
        
        # Label para contador de registros
        self.contador_label = widget.QLabel("0 registros")
        self.status_bar.addPermanentWidget(self.contador_label)

    def limpiar_filtros(self):
        """Limpiar todos los filtros"""
        for filtro in self.filtros:
            filtro.clear()
        self.status_label.setText("Filtros limpiados")

    def cargar_datos_iniciales(self):
        """Cargar datos iniciales con progreso"""
        if not os.path.exists(self.direc):
            widget.QMessageBox.warning(self, "Advertencia", f"El directorio {self.direc} no existe")
            return
            
        archivos = os.listdir(self.direc)
        if not archivos:
            widget.QMessageBox.information(self, "Información", "No hay archivos en el directorio")
            return
            
        self.info_window = InfoProgressBarWindow(
            mensaje="Cargando E-cheques...", 
            minimo=0, 
            maximo=len(archivos)
        )
        
        self.index = 0
        
        try:
            for archivo in archivos:
                self.info_window.show()
                self.index += 1
                
                archivo_path = f"{self.direc}/{archivo}"
                
                if archivo.startswith('E'):
                    arch = pd.read_excel(archivo_path)
                else:
                    arch = pd.read_excel(archivo_path, header=1)
                
                self.addEcheqFile(arch)
                self.info_window.actualizar_progreso(self.index)
                widget.QApplication.processEvents()
                
            self.modified = True
            self.info_window.close()
            self.mostrar_en_tabla(self.df)
            self.status_label.setText("Datos cargados correctamente")
            
        except Exception as e:
            self.info_window.close()
            widget.QMessageBox.critical(self, "Error", f"Error al cargar datos: {str(e)}")

    def mostrar_en_tabla(self, df):
        """Mostrar datos en tabla con contador actualizado"""
        # Filtrar las columnas deseadas
        columnas_a_mostrar = self.campos
        df_mostrar = df.loc[:, [col for col in columnas_a_mostrar if col in df.columns]]
        
        # Actualizar título con contador
        total_registros = len(df_mostrar)
        self.titulo_tabla.setText(f"📊 REGISTROS DE E-CHEQUES ({total_registros} registros)")
        self.contador_label.setText(f"{total_registros} registros")
        
        # Limpiar tabla
        self.tabla_echeq.setRowCount(0)
        self.tabla_echeq.setColumnCount(len(columnas_a_mostrar))
        self.tabla_echeq.setHorizontalHeaderLabels(columnas_a_mostrar)
        
        # Poblar tabla
        for i, (_, fila) in enumerate(df_mostrar.iterrows()):
            self.tabla_echeq.insertRow(i)
            for j, valor in enumerate(fila):
                item = widget.QTableWidgetItem(str(valor))
                
                # Colorear celdas según el contenido (ejemplo)
                if j == 3:  # Columna Monto
                    try:
                        monto = float(str(valor).replace(',', '').replace('$', ''))
                        if monto > 100000:
                            item.setBackground(gui.QColor(255, 240, 240))  # Rojo claro
                        elif monto > 50000:
                            item.setBackground(gui.QColor(255, 255, 240))  # Amarillo claro
                    except:
                        pass
                        
                self.tabla_echeq.setItem(i, j, item)
        
        # Reconfigurar columnas
        self.configurar_columnas_responsivas()

    def aplicar_filtros(self):
        """Aplicar filtros mejorado con feedback"""
        textos_filtros = [filtro.text().strip().lower() for filtro in self.filtros]
        
        if not any(textos_filtros):
            # Si no hay filtros, mostrar todo
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
        
        # Actualizar status
        if filtros_activos:
            self.status_label.setText(f"Filtros activos: {', '.join(filtros_activos[:2])}{'...' if len(filtros_activos) > 2 else ''}")

    def getStyleSheet(self):
        """Retorna el CSS para la aplicación"""
        return """
        QMainWindow {
            background-color: #f8f9fa;
        }
        
        QFrame {
            background-color: white;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }
        
        QLabel#titulo_seccion {
            font-size: 16px;
            font-weight: bold;
            color: #495057;
            padding: 10px;
            background-color: #e3f2fd;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        
        QLabel#label_filtro {
            font-weight: bold;
            color: #6c757d;
            padding: 5px 0;
        }
        
        QLineEdit#campo_filtro {
            padding: 8px 12px;
            border: 2px solid #ced4da;
            border-radius: 6px;
            font-size: 14px;
            background-color: white;
        }
        
        QLineEdit#campo_filtro:focus {
            border-color: #007bff;
            outline: none;
        }
        
        QTableWidget#tabla_principal {
            background-color: white;
            alternate-background-color: #f8f9fa;
            selection-background-color: #007bff;
            selection-color: white;
            gridline-color: #e9ecef;
            border: 1px solid #dee2e6;
            border-radius: 6px;
        }
        
        QTableWidget#tabla_principal::item {
            padding: 8px;
            border-bottom: 1px solid #e9ecef;
        }
        
        QTableWidget#tabla_principal::item:selected {
            background-color: #007bff;
            color: white;
        }
        
        QHeaderView::section {
            background-color: #e9ecef;
            color: #495057;
            padding: 10px;
            border: none;
            border-right: 1px solid #dee2e6;
            font-weight: bold;
        }
        
        QToolBar {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: none;
            padding: 8px;
            spacing: 10px;
        }
        
        QToolBar::separator {
            background-color: #dee2e6;
            width: 1px;
            margin: 5px;
        }
        
        QAction {
            padding: 8px 16px;
            margin: 2px;
            border-radius: 4px;
            background-color: transparent;
        }
        
        QAction:hover {
            background-color: #e3f2fd;
        }
        
        QStatusBar {
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
        }
        """

    # ========== MÉTODOS EXISTENTES (sin cambios) ==========
    
    def closeEvent(self, event):
        if self.modified:
            respuesta = widget.QMessageBox.question(self, "Confirmar", "¿Desea guardar los cambios antes de salir?",
                                                    widget.QMessageBox.Yes | widget.QMessageBox.No | widget.QMessageBox.Cancel)
            if respuesta == widget.QMessageBox.Yes:
                self.guardar_archivo()
                event.accept()
            elif respuesta == widget.QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def guardar_archivo(self):
        ruta_archivo = 'd:/tiempo/E-cheqs/Echeqs_sistema.xlsx'
        
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

    def addEcheqFile(self, excel):
        if excel is None:
            return
        try:
            if excel['Pagador Cuit'].apply(self.tiene_letras).any():
                excel.rename(columns={'Pagador Cuit': 'Pagador Nombre Apellido/Razón Social','Pagador Nombre Apellido/Razón Social': 'Pagador Cuit'}, inplace=True)

            # Obtener el conjunto de Nro de Cheque ya cargados para deduplicar
            nros_existentes = set(self.df['Nro de Cheque'].astype(str).str.strip().values) if 'Nro de Cheque' in self.df.columns else set()

            nuevas_filas = []
            for _, newRow in excel.iterrows():
                if "Nro de Cheque" not in newRow or pd.isna(newRow["Nro de Cheque"]):
                    continue
                nro = str(newRow["Nro de Cheque"]).strip()
                if nro and nro not in nros_existentes:
                    nuevas_filas.append(newRow)
                    nros_existentes.add(nro)

            if nuevas_filas:
                self.df = pd.concat([self.df, pd.DataFrame(nuevas_filas)], ignore_index=True)
        except Exception as e:
            widget.QMessageBox.critical(self, "Error", f"Ocurrió un problema al agregar los Echeq: {str(e)}")
            
    def tiene_letras(self, cuit):
        return any(char.isalpha() for char in str(cuit))