import PyQt5.QtWidgets as widget
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Qt
import pandas as pd
from dbfread import DBF
from datetime import datetime
import os
from src.Views.Beneficio.DetalleBeneficio import DetalleDialog


class _CostoDelegate(widget.QStyledItemDelegate):
    """Delegate exclusivo para la columna Costo: selecciona todo al abrir y valida número al confirmar."""

    def createEditor(self, parent, option, index):
        editor = widget.QLineEdit(parent)
        editor.setAlignment(Qt.Qt.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        # Mostrar el valor actual sin símbolo de moneda, seleccionado para fácil reemplazo
        val = str(index.data(Qt.Qt.DisplayRole) or "0").strip()
        editor.setText(val)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        texto = editor.text().strip()
        try:
            # Soportar tanto "1200.50" como "1.200,50" (separador de miles/decimales)
            if ',' in texto and '.' in texto:
                texto = texto.replace('.', '').replace(',', '.')
            else:
                texto = texto.replace(',', '.')
            valor = float(texto)
            model.setData(index, f"{valor:.4f}", Qt.Qt.DisplayRole)
        except ValueError:
            pass  # Valor inválido: no actualizar, mantener el anterior


class margenBeneficio(widget.QWidget):
    def __init__(self, parent=None, df_periodo_ventas=None): 
        super().__init__(parent)
        self.setWindowTitle("Margen de venta")
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        ancho = int(screen.width() * 0.88)
        alto = int(screen.height() * 0.88)
        x = screen.x() + (screen.width() - ancho) // 2
        y = screen.y() + (screen.height() - alto) // 2
        self.setGeometry(x, y, ancho, alto)
        self.setMinimumSize(900, 550)
        self.index = 0
        self.TotalLts = 0
        self.TotalPremium = 0
        self.modified = False
        
        # Diccionario para nombres de clientes
        self.clientes_dict = {}
        
        # Caché para precios y nombres de productos
        self.cache_precios = {}
        self.cache_nombres_productos = {}
        self.cache_artiprov = {}
        
        # Verificar que se pasó el DataFrame
        if df_periodo_ventas is None or df_periodo_ventas.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos para procesar en el período seleccionado.")
            self.close()
            return
            
        # Verificar columnas necesarias
        columnas_requeridas = ["FECHA", "MODELO", "U_VENDIDAS", "TOTAVEN"]
        columnas_opcionales = ["CUENTA", "NROEST", "TC", "NC", "DESC"]
        
        columnas_disponibles = []
        for col in columnas_requeridas + columnas_opcionales:
            if col in df_periodo_ventas.columns:
                columnas_disponibles.append(col)
        
        if not all(col in df_periodo_ventas.columns for col in columnas_requeridas):
            widget.QMessageBox.critical(self, "Error", f"Faltan columnas requeridas en los datos.")
            self.close()
            return
            
        # Dataframes - usar solo columnas disponibles
        self.periodoVentas = df_periodo_ventas[columnas_disponibles].copy()
        
        # Asegurar que no hay valores nulos en campos críticos
        self.periodoVentas = self.periodoVentas.dropna(subset=["MODELO", "U_VENDIDAS", "TOTAVEN"])
        
        if self.periodoVentas.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos válidos para procesar.")
            self.close()
            return
        
        # Cargar datos de clientes
        self.cargar_clientes()
        
        # Cargar lista de precios
        try:
            self.precios = pd.read_excel(r'd:/tiempo/Lista de precios/Lista de precios Mana.xlsm', 
                                       sheet_name='Lista De Precios', header=2)
            self.precios = self.precios[["SKU", 'Producto', "Precio Por envase"]]
            # Limpiar datos de precios
            self.precios = self.precios.dropna(subset=["SKU"])
            # Normalizar SKU en precios para búsquedas más rápidas
            self.precios['SKU_NORM'] = self.precios['SKU'].astype(str).str.strip().str.upper()
        except Exception as e:
            widget.QMessageBox.warning(self, "Advertencia", f"No se pudo cargar la lista de precios: {e}\nSe usarán precios en 0.")
            self.precios = pd.DataFrame(columns=["SKU", 'Producto', "Precio Por envase", "SKU_NORM"])
        
        # Cargar abmartic.dbf una sola vez
        self.abmartic_df = None
        self.cargar_abmartic()
        
        self.content_table = pd.DataFrame(columns=["SKU", "Producto", "Total Ventas", "Margen de beneficio", 'Detalle'])
        self.detalles_por_sku = {}  # Diccionario para almacenar detalles por SKU
        
        # Crear la interfaz
        self.setupUI()
        
        # Procesar los datos
        self.margenesBeneficio(self.periodoVentas)
        
        # Asegurar que la ventana se muestre correctamente
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def cargar_clientes(self):
        """Cargar nombres de clientes desde archivo DBF"""
        try:
            # Intentar cargar desde la ruta típica de clientes
            rutas_posibles = [
                r'D:/tiempo/vtiempoges/GESTION/MANA2014/ctaclien.DBF',
                r'z:/vtiempoges/GESTION/MANA2014/ctaclien.DBF',
                r'D:/GESTION/MANA2014/ctaclien.DBF',
                r'C:/GESTION/MANA2014/ctaclien.DBF'
            ]
            
            clientes_df = None
            for ruta in rutas_posibles:
                if os.path.exists(ruta):
                    try:
                        clientes_dbf = DBF(ruta, encoding='latin1')
                        clientes_df = pd.DataFrame(iter(clientes_dbf))
                        print(f"Clientes cargados desde: {ruta}")
                        break
                    except Exception as e:
                        print(f"Error al cargar desde {ruta}: {e}")
                        continue
            
            if clientes_df is not None and not clientes_df.empty:
                # Crear diccionario de clientes: CNUMERO -> CNOMBRE
                if 'CNUMERO' in clientes_df.columns and 'CNOMBRE' in clientes_df.columns:
                    for _, cliente in clientes_df.iterrows():
                        # Convertir cuenta a entero y luego a string para eliminar decimales
                        try:
                            cuenta = str(int(float(cliente['CNUMERO']))).strip()
                        except (ValueError, TypeError):
                            cuenta = str(cliente['CNUMERO']).strip()
                        
                        nombre = str(cliente['CNOMBRE']).strip()
                        if cuenta and nombre and nombre.lower() != 'nan':
                            self.clientes_dict[cuenta] = nombre
                    
                    print(f"Se cargaron {len(self.clientes_dict)} clientes")
                else:
                    print("No se encontraron las columnas CNUMERO y CNOMBRE en la base de clientes")
            else:
                print("No se pudo cargar la base de datos de clientes")
                
        except Exception as e:
            print(f"Error general al cargar clientes: {e}")
            widget.QMessageBox.warning(self, "Advertencia", f"No se pudieron cargar los nombres de clientes: {e}")

    def cargar_abmartic(self):
        """Cargar archivo abmartic.dbf una sola vez en memoria"""
        try:
            ruta_abmartic = r'd:/tiempo/vtiempoges/GESTION/MANA2014/abmartic.dbf'
            if os.path.exists(ruta_abmartic):
                try:
                    abmartic_dbf = DBF(ruta_abmartic, encoding='latin1')
                    self.abmartic_df = pd.DataFrame(iter(abmartic_dbf))
                    # Normalizar CODART para búsquedas rápidas
                    self.abmartic_df['CODART_NORM'] = self.abmartic_df['CODART'].astype(str).str.strip().str.upper()
                    print(f"abmartic.dbf cargado exitosamente con {len(self.abmartic_df)} registros")
                except Exception as e:
                    print(f"Error al cargar abmartic.dbf: {e}")
                    self.abmartic_df = None
            else:
                print(f"Archivo abmartic.dbf no encontrado en {ruta_abmartic}")
                self.abmartic_df = None
        except Exception as e:
            print(f"Error general al cargar abmartic.dbf: {e}")
            self.abmartic_df = None

    def setupUI(self):
        """Configura la interfaz de usuario"""
        layout = widget.QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Título
        titulo = widget.QLabel("Análisis de Margen de Beneficio")
        titulo.setFont(Gui.QFont("Arial", 16, Gui.QFont.Bold))
        titulo.setAlignment(Qt.Qt.AlignCenter)
        titulo.setStyleSheet("color: #2c3e50; margin: 10px;")
        layout.addWidget(titulo)
        
        # Información del período
        info_periodo = widget.QLabel(f"Productos analizados: {len(self.periodoVentas)} registros de ventas | Clientes cargados: {len(self.clientes_dict)}")
        info_periodo.setAlignment(Qt.Qt.AlignCenter)
        info_periodo.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(info_periodo)
        
        # Barra de búsqueda
        search_frame = widget.QFrame()
        search_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        search_layout = widget.QHBoxLayout(search_frame)
        
        search_label = widget.QLabel("🔍 Buscar:")
        search_label.setFont(Gui.QFont("Arial", 11, Gui.QFont.Bold))
        search_layout.addWidget(search_label)
        
        self.search_input = widget.QLineEdit()
        self.search_input.setPlaceholderText("Buscar por SKU o nombre del producto...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #007bff;
                outline: none;
            }
        """)
        self.search_input.textChanged.connect(self.filtrar_tabla)
        search_layout.addWidget(self.search_input)
        
        btn_limpiar = widget.QPushButton("✖ Limpiar")
        btn_limpiar.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_limpiar.clicked.connect(self.limpiar_busqueda)
        search_layout.addWidget(btn_limpiar)
        
        layout.addWidget(search_frame)
        
        # Tabla principal
        self.tabla = widget.QTableWidget()
        self.tabla.setColumnCount(7)
        self.tabla.setHorizontalHeaderLabels([
            "SKU", "Producto", "Costo Unit.", "Total Ventas", "Margen $", "Margen %", "Detalle"
        ])
        
        # Configurar el estilo de la tabla
        self.tabla.setStyleSheet("""
            QTableWidget {
                gridline-color: #bdc3c7;
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                selection-background-color: #e3f2fd;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #ecf0f1;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QTableWidget::item:hover {
                background-color: #f5f5f5;
                color: #333333;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                font-weight: bold;
                padding: 8px;
                border: none;
            }
        """)
        
        # Configurar la tabla
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.horizontalHeader().setStretchLastSection(False)

        # Modos de redimensionamiento
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, widget.QHeaderView.ResizeToContents)  # SKU
        header.setSectionResizeMode(1, widget.QHeaderView.Stretch)            # Producto
        header.setSectionResizeMode(2, widget.QHeaderView.Fixed)              # Costo (editable)
        header.setSectionResizeMode(3, widget.QHeaderView.ResizeToContents)  # Total Ventas
        header.setSectionResizeMode(4, widget.QHeaderView.ResizeToContents)  # Margen $
        header.setSectionResizeMode(5, widget.QHeaderView.ResizeToContents)  # Margen %
        header.setSectionResizeMode(6, widget.QHeaderView.Fixed)              # Detalle
        self.tabla.setColumnWidth(2, 110)  # Costo
        self.tabla.setColumnWidth(6, 80)   # Detalle

        # Solo la columna Costo (2) es editable via delegate; el resto bloqueado por flags de item
        self.tabla.setEditTriggers(widget.QAbstractItemView.DoubleClicked)
        self.tabla.setItemDelegateForColumn(2, _CostoDelegate(self.tabla))
        self.tabla.cellChanged.connect(self.on_costo_cambiado)

        layout.addWidget(self.tabla)
        
        # Panel de estadísticas
        stats_frame = widget.QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
            }
            QLabel {
                color: #2c3e50;
                font-weight: bold;
            }
        """)
        
        stats_layout = widget.QHBoxLayout(stats_frame)
        self.label_total_ventas = widget.QLabel("Total Ventas: $0.00")
        self.label_total_margen = widget.QLabel("Total Margen: $0.00")
        self.label_margen_promedio = widget.QLabel("Margen Promedio: 0.00%")
        self.label_productos_mostrados = widget.QLabel("Productos mostrados: 0")
        
        stats_layout.addWidget(self.label_total_ventas)
        stats_layout.addWidget(self.label_total_margen)
        stats_layout.addWidget(self.label_margen_promedio)
        stats_layout.addWidget(self.label_productos_mostrados)
        stats_layout.addStretch()
        
        layout.addWidget(stats_frame)
        
        # Botón para exportar
        btn_exportar = widget.QPushButton("📊 Exportar a Excel")
        btn_exportar.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        btn_exportar.clicked.connect(self.exportar_excel)
        layout.addWidget(btn_exportar)
        
        self.setLayout(layout)

    def margenesBeneficio(self, ventas):
        """Procesa los datos de ventas y calcula márgenes de beneficio"""
        
        # Diccionario para acumular datos por SKU
        datos_acumulados = {}
        
        # Normalizar MODELO para búsquedas
        ventas_procesadas = ventas.copy()
        ventas_procesadas['MODELO_NORM'] = ventas_procesadas['MODELO'].astype(str).str.strip().str.upper()
        
        for index, venta in ventas_procesadas.iterrows():
            sku = str(venta['MODELO']).strip()
            sku_norm = venta['MODELO_NORM']
            
            # Validar datos críticos
            try:
                total_venta = float(venta['TOTAVEN']) if pd.notna(venta['TOTAVEN']) else 0
                unidades = float(venta['U_VENDIDAS']) if pd.notna(venta['U_VENDIDAS']) else 0
            except (ValueError, TypeError):
                continue  # Saltar registros con datos inválidos
            
            if unidades == 0:
                continue  # Evitar división por cero
            
            # Buscar precio por envase (ya optimizado con caché)
            precio_por_envase = self.obtener_precio_por_envase(sku_norm)
            if precio_por_envase == 0:
                print(f"Precio por envase no encontrado para SKU: {sku}")
            # Calcular margen unitario: (TOTAVEN/U_VENDIDAS) - Precio Por envase
            precio_venta_unitario = total_venta / unidades
            margen_unitario = precio_venta_unitario - precio_por_envase
            margen_total = margen_unitario * unidades
            
            # Obtener nombre del producto (ya optimizado con caché)
            producto = self.obtener_nombre_producto(sku_norm)
            
            # Crear detalle de esta venta (usar campos disponibles)
            # Convertir cuenta a entero para eliminar decimales
            cuenta_raw = venta.get('CUENTA', 'N/A')
            try:
                cuenta_clean = str(int(float(cuenta_raw))) if cuenta_raw != 'N/A' else 'N/A'
            except (ValueError, TypeError):
                cuenta_clean = str(cuenta_raw)
            
            detalle_venta = {
                'FECHA': venta.get('FECHA', 'N/A'),
                'CUENTA': cuenta_clean,
                'TC': venta.get('TC', 'N/A'),
                'NC': venta.get('NC', 'N/A'),
                'U_VENDIDAS': unidades,
                'TOTAVEN': total_venta,
                'PRECIO_UNITARIO': precio_venta_unitario,
                'PRECIO_COSTO': precio_por_envase,
                'MARGEN_UNITARIO': margen_unitario
            }
            
            # Acumular datos
            if sku in datos_acumulados:
                datos_acumulados[sku]['Total Ventas'] += total_venta
                datos_acumulados[sku]['Margen de beneficio'] += margen_total
                datos_acumulados[sku]['Unidades Vendidas'] += unidades
                self.detalles_por_sku[sku].append(detalle_venta)
            else:
                datos_acumulados[sku] = {
                    'SKU': sku,
                    'Producto': producto,
                    'Costo': precio_por_envase,
                    'Total Ventas': total_venta,
                    'Margen de beneficio': margen_total,
                    'Unidades Vendidas': unidades
                }
                self.detalles_por_sku[sku] = [detalle_venta]
        
        # Convertir a DataFrame y actualizar la tabla
        if datos_acumulados:
            self.content_table = pd.DataFrame(list(datos_acumulados.values()))
            # Calcular margen porcentual
            self.content_table['Margen %'] = (
                (self.content_table['Margen de beneficio'] / (self.content_table['Total Ventas']-self.content_table['Margen de beneficio'])) * 100
            ).round(2)
            # Guardar datos originales para filtrado
            self.datos_originales = self.content_table.copy()
            self.actualizar_tabla()
        else:
            self.content_table = pd.DataFrame()
            self.datos_originales = pd.DataFrame()
            widget.QMessageBox.information(self, "Sin datos", "No hay datos válidos para mostrar en el período seleccionado.")

    def filtrar_tabla(self):
        """Filtra la tabla basado en el texto de búsqueda"""
        texto_busqueda = self.search_input.text().strip().lower()
        
        if not texto_busqueda:
            # Si no hay texto, mostrar todos los datos
            self.content_table = self.datos_originales.copy()
        else:
            # Filtrar por SKU o Producto
            mask = (
                self.datos_originales['SKU'].astype(str).str.lower().str.contains(texto_busqueda, na=False) |
                self.datos_originales['Producto'].astype(str).str.lower().str.contains(texto_busqueda, na=False)
            )
            self.content_table = self.datos_originales[mask].copy()
        
        self.actualizar_tabla()
    
    def limpiar_busqueda(self):
        """Limpia el campo de búsqueda y muestra todos los datos"""
        self.search_input.clear()
        self.content_table = self.datos_originales.copy()
        self.actualizar_tabla()

    def obtener_precio_por_envase(self, sku):
        """Busca el precio por envase del SKU en la lista de precios"""
        if self.precios.empty:
            return 0
        
        # Limpiar el SKU para la búsqueda
        sku_limpio = str(sku).strip().upper()
        
        # Verificar caché primero
        if sku_limpio in self.cache_precios:
            return self.cache_precios[sku_limpio]
        
        # Buscar ARTIPROV en abmartic_df si está cargado
        if self.abmartic_df is not None and sku_limpio not in self.cache_artiprov:
            # Búsqueda en abmartic_df
            codart_rows = self.abmartic_df[self.abmartic_df['CODART_NORM'] == sku_limpio]
            
            if not codart_rows.empty:
                artiprov = codart_rows.iloc[0].get('ARTIPROV', '')
                # Si ARTIPROV no está vacío, usarlo como nuevo sku_limpio
                if pd.notna(artiprov) and str(artiprov).strip():
                    sku_limpio = str(artiprov).strip().upper()
            
            self.cache_artiprov[sku_limpio] = True
        
        # Buscar exacto primero
        precio_row = self.precios[self.precios['SKU_NORM'] == sku_limpio]
        
        if not precio_row.empty:
            precio = precio_row.iloc[0]['Precio Por envase']
            try:
                # Manejar diferentes formatos de precio
                if isinstance(precio, str):
                    # Remover caracteres no numéricos excepto punto y coma
                    precio_limpio = ''.join(c for c in precio if c.isdigit() or c in '.,')
                    precio_limpio = precio_limpio.replace(',', '.')
                    resultado = float(precio_limpio) if precio_limpio else 0
                else:
                    resultado = float(precio) if pd.notna(precio) else 0
                self.cache_precios[sku_limpio] = resultado
                return resultado
            except (ValueError, TypeError):
                self.cache_precios[sku_limpio] = 0
                return 0
        
        # Si no se encuentra exacto, buscar contenido
        precio_row = self.precios[self.precios['SKU_NORM'].str.contains(sku_limpio, case=False, na=False)]
        if not precio_row.empty:
            precio = precio_row.iloc[0]['Precio Por envase']
            try:
                if isinstance(precio, str):
                    precio_limpio = ''.join(c for c in precio if c.isdigit() or c in '.,')
                    precio_limpio = precio_limpio.replace(',', '.')
                    resultado = float(precio_limpio) if precio_limpio else 0
                else:
                    resultado = float(precio) if pd.notna(precio) else 0
                self.cache_precios[sku_limpio] = resultado
                return resultado
            except (ValueError, TypeError):
                self.cache_precios[sku_limpio] = 0
                return 0
        
        self.cache_precios[sku_limpio] = 0
        return 0

    def obtener_nombre_producto(self, sku):
        """Obtiene el nombre del producto desde la columna DESC de periodoVentas"""
        # Limpiar el SKU para la búsqueda
        sku_limpio = str(sku).strip().upper()
        
        # Verificar caché primero
        if sku_limpio in self.cache_nombres_productos:
            return self.cache_nombres_productos[sku_limpio]
        
        # Verificar si existe la columna DESC
        if 'DESC' in self.periodoVentas.columns:
            # Buscar en periodoVentas por MODELO que coincida con el SKU
            producto_rows = self.periodoVentas[
                self.periodoVentas['MODELO'].astype(str).str.strip().str.upper() == sku_limpio
            ]
            
            if not producto_rows.empty:
                # Tomar la primera coincidencia y obtener la descripción
                desc = producto_rows.iloc[0]['DESC']
                if pd.notna(desc) and str(desc).strip():
                    resultado = str(desc).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado
        
        # Si no encuentra descripción, intentar buscar en la lista de precios como fallback
        if not self.precios.empty:
            # Buscar exacto primero en lista de precios
            producto_row = self.precios[self.precios['SKU_NORM'] == sku_limpio]
            
            if not producto_row.empty:
                nombre = producto_row.iloc[0]['Producto']
                if pd.notna(nombre) and str(nombre).strip():
                    resultado = str(nombre).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado
            
            # Si no se encuentra exacto, buscar contenido en lista de precios
            producto_row = self.precios[self.precios['SKU_NORM'].str.contains(sku_limpio, case=False, na=False)]
            if not producto_row.empty:
                nombre = producto_row.iloc[0]['Producto']
                if pd.notna(nombre) and str(nombre).strip():
                    resultado = str(nombre).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado
        
        # Si no encuentra nada, usar el SKU
        self.cache_nombres_productos[sku_limpio] = str(sku)
        return str(sku)

    def _make_item_readonly(self, text, alignment=None, font=None, bg=None, fg=None):
        """Crea un QTableWidgetItem no editable"""
        item = widget.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.Qt.ItemIsEditable)
        if alignment:
            item.setTextAlignment(alignment)
        if font:
            item.setFont(font)
        if bg:
            item.setBackground(bg)
        if fg:
            item.setForeground(fg)
        return item

    def actualizar_tabla(self):
        """Actualiza la tabla con los datos calculados"""
        if self.content_table.empty:
            return

        self.tabla.blockSignals(True)
        try:
            self.tabla.setRowCount(len(self.content_table))

            font_bold = Gui.QFont("Arial", 9, Gui.QFont.Bold)
            font_normal = Gui.QFont("Arial", 9)
            font_sku = Gui.QFont("Arial", 10, Gui.QFont.Bold)
            aln_right = Qt.Qt.AlignRight | Qt.Qt.AlignVCenter

            for i, (_, row) in enumerate(self.content_table.iterrows()):
                self.tabla.setRowHeight(i, 36)

                # Col 0 - SKU (solo lectura)
                self.tabla.setItem(i, 0, self._make_item_readonly(str(row['SKU']), font=font_sku))

                # Col 1 - Producto (solo lectura)
                self.tabla.setItem(i, 1, self._make_item_readonly(str(row['Producto']), font=font_normal))

                # Col 2 - Costo (EDITABLE - fondo amarillo claro)
                costo = row.get('Costo', 0)
                costo_item = widget.QTableWidgetItem(f"{costo:.4f}")
                costo_item.setTextAlignment(aln_right)
                costo_item.setFont(font_bold)
                costo_item.setBackground(Gui.QColor(255, 255, 210))
                costo_item.setForeground(Gui.QColor(80, 60, 0))
                costo_item.setToolTip("Doble clic para editar el costo unitario. Presione Enter para confirmar.")
                self.tabla.setItem(i, 2, costo_item)

                # Col 3 - Total Ventas (solo lectura)
                self.tabla.setItem(i, 3, self._make_item_readonly(
                    f"${row['Total Ventas']:,.2f}", alignment=aln_right, font=font_normal))

                # Col 4 - Margen $ (solo lectura, coloreado)
                margen = row['Margen de beneficio']
                mbg = Gui.QColor(144, 238, 144) if margen >= 0 else Gui.QColor(255, 182, 193)
                mfg = Gui.QColor(0, 100, 0) if margen >= 0 else Gui.QColor(139, 0, 0)
                self.tabla.setItem(i, 4, self._make_item_readonly(
                    f"${margen:,.2f}", alignment=aln_right, font=font_bold, bg=mbg, fg=mfg))

                # Col 5 - Margen % (solo lectura, coloreado)
                pct = row['Margen %']
                pbg = Gui.QColor(144, 238, 144) if pct >= 0 else Gui.QColor(255, 182, 193)
                pfg = Gui.QColor(0, 100, 0) if pct >= 0 else Gui.QColor(139, 0, 0)
                self.tabla.setItem(i, 5, self._make_item_readonly(
                    f"{pct:.2f}%", alignment=aln_right, font=font_normal, bg=pbg, fg=pfg))

                # Col 6 - Detalle (botón)
                btn_detalle = widget.QPushButton("Ver")
                btn_detalle.setStyleSheet("""
                    QPushButton {
                        background-color: #3498db; color: white;
                        border: none; padding: 4px 8px;
                        border-radius: 3px; font-size: 10px;
                    }
                    QPushButton:hover { background-color: #2980b9; }
                    QPushButton:pressed { background-color: #21618c; }
                """)
                btn_detalle.clicked.connect(lambda checked, sku=row['SKU']: self.mostrar_detalle(sku))
                self.tabla.setCellWidget(i, 6, btn_detalle)
        finally:
            self.tabla.blockSignals(False)

        self.actualizar_estadisticas()

    def actualizar_estadisticas(self):
        """Actualiza los labels de estadísticas globales"""
        if self.content_table.empty:
            return
        total_ventas = self.content_table['Total Ventas'].sum()
        total_margen = self.content_table['Margen de beneficio'].sum()
        margen_promedio = (total_margen / total_ventas * 100) if total_ventas > 0 else 0
        self.label_total_ventas.setText(f"Total Ventas: ${total_ventas:,.2f}")
        self.label_total_margen.setText(f"Total Margen: ${total_margen:,.2f}")
        self.label_margen_promedio.setText(f"Margen Promedio: {margen_promedio:.2f}%")
        self.label_productos_mostrados.setText(f"Productos mostrados: {len(self.content_table)}")

    def on_costo_cambiado(self, fila, columna):
        """Recalcula el margen cuando el usuario edita el costo unitario (señal cellChanged)"""
        if columna != 2:
            return

        # Leer el valor ya validado y formateado por _CostoDelegate
        costo_item = self.tabla.item(fila, 2)
        if costo_item is None:
            return
        try:
            nuevo_costo = float(costo_item.text().strip())
        except ValueError:
            return

        # Obtener SKU de la fila
        sku_item = self.tabla.item(fila, 0)
        if sku_item is None:
            return
        sku = sku_item.text()

        # Buscar en content_table
        mask = self.content_table['SKU'].astype(str) == sku
        if not mask.any():
            return

        idx = self.content_table.index[mask][0]
        total_ventas = float(self.content_table.loc[idx, 'Total Ventas'])
        unidades = float(self.content_table.loc[idx, 'Unidades Vendidas'])

        # Recalcular: margen = total_ventas - (costo * unidades)
        nuevo_margen = total_ventas - nuevo_costo * unidades
        costo_total = total_ventas - nuevo_margen  # = costo * unidades
        nuevo_pct = (nuevo_margen / costo_total * 100) if costo_total != 0 else 0

        # Actualizar content_table y datos_originales
        self.content_table.loc[idx, 'Costo'] = nuevo_costo
        self.content_table.loc[idx, 'Margen de beneficio'] = nuevo_margen
        self.content_table.loc[idx, 'Margen %'] = round(nuevo_pct, 2)

        if hasattr(self, 'datos_originales') and not self.datos_originales.empty:
            orig_mask = self.datos_originales['SKU'].astype(str) == sku
            if orig_mask.any():
                orig_idx = self.datos_originales.index[orig_mask][0]
                self.datos_originales.loc[orig_idx, 'Costo'] = nuevo_costo
                self.datos_originales.loc[orig_idx, 'Margen de beneficio'] = nuevo_margen
                self.datos_originales.loc[orig_idx, 'Margen %'] = round(nuevo_pct, 2)

        # Propagar el nuevo costo al detalle de ventas del SKU,
        # para que el diálogo "Ver" refleje los valores actualizados
        if sku in self.detalles_por_sku:
            for detalle in self.detalles_por_sku[sku]:
                precio_venta = detalle.get('PRECIO_UNITARIO', 0)
                detalle['PRECIO_COSTO'] = nuevo_costo
                detalle['MARGEN_UNITARIO'] = precio_venta - nuevo_costo

        # Actualizar celdas afectadas sin repoblar toda la tabla
        self.tabla.blockSignals(True)
        try:
            font_bold = Gui.QFont("Arial", 9, Gui.QFont.Bold)
            font_normal = Gui.QFont("Arial", 9)

            # Costo - restablecer fondo editable
            costo_item.setBackground(Gui.QColor(255, 255, 210))
            costo_item.setForeground(Gui.QColor(80, 60, 0))

            # Margen $
            mbg = Gui.QColor(144, 238, 144) if nuevo_margen >= 0 else Gui.QColor(255, 182, 193)
            mfg = Gui.QColor(0, 100, 0) if nuevo_margen >= 0 else Gui.QColor(139, 0, 0)
            margen_item = self.tabla.item(fila, 4)
            if margen_item:
                margen_item.setText(f"${nuevo_margen:,.2f}")
                margen_item.setBackground(mbg)
                margen_item.setForeground(mfg)
                margen_item.setFont(font_bold)

            # Margen %
            pbg = Gui.QColor(144, 238, 144) if nuevo_pct >= 0 else Gui.QColor(255, 182, 193)
            pfg = Gui.QColor(0, 100, 0) if nuevo_pct >= 0 else Gui.QColor(139, 0, 0)
            pct_item = self.tabla.item(fila, 5)
            if pct_item:
                pct_item.setText(f"{nuevo_pct:.2f}%")
                pct_item.setBackground(pbg)
                pct_item.setForeground(pfg)
                pct_item.setFont(font_normal)
        finally:
            self.tabla.blockSignals(False)

        self.actualizar_estadisticas()

    def mostrar_detalle(self, sku):
        """Muestra el detalle de ventas para un SKU específico"""
        if sku in self.detalles_por_sku:
            producto = self.obtener_nombre_producto(sku)
            detalle_dialog = DetalleDialog(
                sku, producto, self.detalles_por_sku[sku], self.clientes_dict, self,
                on_costo_cambiado_cb=lambda: self._cascada_desde_detalle(sku)
            )
            detalle_dialog.exec_()

    def _cascada_desde_detalle(self, sku):
        """Recalcula los totales del SKU en la tabla principal usando los costos del detalle."""
        if sku not in self.detalles_por_sku:
            return

        detalles = self.detalles_por_sku[sku]
        total_margen     = sum(d['MARGEN_UNITARIO'] * d['U_VENDIDAS'] for d in detalles)
        total_unidades   = sum(d['U_VENDIDAS'] for d in detalles)
        costo_ponderado  = sum(d['PRECIO_COSTO'] * d['U_VENDIDAS'] for d in detalles)
        nuevo_costo_unit = costo_ponderado / total_unidades if total_unidades > 0 else 0
        nuevo_pct        = (total_margen / costo_ponderado * 100) if costo_ponderado != 0 else 0

        # Actualizar content_table
        mask = self.content_table['SKU'].astype(str) == str(sku)
        if not mask.any():
            return
        idx = self.content_table.index[mask][0]
        self.content_table.loc[idx, 'Costo']               = nuevo_costo_unit
        self.content_table.loc[idx, 'Margen de beneficio'] = total_margen
        self.content_table.loc[idx, 'Margen %']            = round(nuevo_pct, 2)

        # Sincronizar datos_originales
        if hasattr(self, 'datos_originales') and not self.datos_originales.empty:
            orig_mask = self.datos_originales['SKU'].astype(str) == str(sku)
            if orig_mask.any():
                orig_idx = self.datos_originales.index[orig_mask][0]
                self.datos_originales.loc[orig_idx, 'Costo']               = nuevo_costo_unit
                self.datos_originales.loc[orig_idx, 'Margen de beneficio'] = total_margen
                self.datos_originales.loc[orig_idx, 'Margen %']            = round(nuevo_pct, 2)

        # Actualizar la fila visual del producto en la tabla principal
        for row_idx in range(self.tabla.rowCount()):
            sku_item = self.tabla.item(row_idx, 0)
            if sku_item and sku_item.text() == str(sku):
                self.tabla.blockSignals(True)
                try:
                    font_bold   = Gui.QFont("Arial", 9, Gui.QFont.Bold)
                    font_normal = Gui.QFont("Arial", 9)

                    costo_item = self.tabla.item(row_idx, 2)
                    if costo_item:
                        costo_item.setText(f"{nuevo_costo_unit:.4f}")

                    mbg = Gui.QColor(144, 238, 144) if total_margen >= 0 else Gui.QColor(255, 182, 193)
                    mfg = Gui.QColor(0, 100, 0)    if total_margen >= 0 else Gui.QColor(139, 0, 0)
                    margen_item = self.tabla.item(row_idx, 4)
                    if margen_item:
                        margen_item.setText(f"${total_margen:,.2f}")
                        margen_item.setBackground(mbg)
                        margen_item.setForeground(mfg)
                        margen_item.setFont(font_bold)

                    pbg = Gui.QColor(144, 238, 144) if nuevo_pct >= 0 else Gui.QColor(255, 182, 193)
                    pfg = Gui.QColor(0, 100, 0)    if nuevo_pct >= 0 else Gui.QColor(139, 0, 0)
                    pct_item = self.tabla.item(row_idx, 5)
                    if pct_item:
                        pct_item.setText(f"{nuevo_pct:.2f}%")
                        pct_item.setBackground(pbg)
                        pct_item.setForeground(pfg)
                        pct_item.setFont(font_normal)
                finally:
                    self.tabla.blockSignals(False)
                break

        self.actualizar_estadisticas()

    def exportar_excel(self):
        """Exporta los resultados a un archivo Excel"""
        if self.content_table.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return
            
        ruta_archivo, _ = widget.QFileDialog.getSaveFileName(
            self, "Exportar Margen de Beneficio", 
            f"margen_beneficio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", 
            "Archivos Excel (*.xlsx)"
        )
        
        if ruta_archivo:
            try:
                # Crear un escritor de Excel con múltiples hojas
                with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
                    # Hoja resumen
                    df_resumen = self.content_table.copy()
                    df_resumen = df_resumen[['SKU', 'Producto', 'Unidades Vendidas', 'Total Ventas', 'Margen de beneficio', 'Margen %']]
                    df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
                    
                    # Hoja con detalles completos incluyendo nombres de clientes
                    detalles_completos = []
                    for sku, detalles in self.detalles_por_sku.items():
                        producto = self.obtener_nombre_producto(sku)
                        for detalle in detalles:
                            detalle_completo = detalle.copy()
                            detalle_completo['SKU'] = sku
                            detalle_completo['Producto'] = producto
                            
                            # Agregar nombre del cliente (sin prefijo "Cliente")
                            cuenta = str(detalle.get('CUENTA', 'N/A'))
                            detalle_completo['CLIENTE'] = self.clientes_dict.get(cuenta, cuenta)  # Solo número si no encuentra nombre
                            
                            # Calcular margen total para esta línea
                            detalle_completo['MARGEN_TOTAL'] = detalle_completo['MARGEN_UNITARIO'] * detalle_completo['U_VENDIDAS']
                            detalles_completos.append(detalle_completo)
                    
                    if detalles_completos:
                        df_detalles = pd.DataFrame(detalles_completos)
                        # Reordenar columnas incluyendo CLIENTE
                        columnas_orden = ['SKU', 'Producto', 'FECHA', 'CLIENTE', 'CUENTA', 'TC', 'NC', 
                                        'U_VENDIDAS', 'TOTAVEN', 'PRECIO_UNITARIO', 'PRECIO_COSTO',
                                        'MARGEN_UNITARIO', 'MARGEN_TOTAL']
                        # Solo incluir columnas que existan
                        columnas_existentes = [col for col in columnas_orden if col in df_detalles.columns]
                        df_detalles = df_detalles[columnas_existentes]
                        df_detalles.to_excel(writer, sheet_name='Detalle_Completo', index=False)
                    
                    # Hoja de estadísticas
                    total_ventas = self.content_table['Total Ventas'].sum()
                    total_margen = self.content_table['Margen de beneficio'].sum()
                    margen_promedio = (total_margen / total_ventas * 100) if total_ventas > 0 else 0
                    productos_con_margen_positivo = len(self.content_table[self.content_table['Margen de beneficio'] > 0])
                    productos_con_margen_negativo = len(self.content_table[self.content_table['Margen de beneficio'] < 0])
                    
                    estadisticas = {
                        'Métrica': [
                            'Total de Productos',
                            'Productos con Margen Positivo',
                            'Productos con Margen Negativo',
                            'Total Ventas ($)',
                            'Total Margen ($)',
                            'Margen Promedio (%)',
                            'Mejor Producto (Margen $)',
                            'Peor Producto (Margen $)',
                            'Clientes Únicos Cargados'
                        ],
                        'Valor': [
                            len(self.content_table),
                            productos_con_margen_positivo,
                            productos_con_margen_negativo,
                            f"${total_ventas:,.2f}",
                            f"${total_margen:,.2f}",
                            f"{margen_promedio:.2f}%",
                            self.content_table.loc[self.content_table['Margen de beneficio'].idxmax(), 'SKU'] if not self.content_table.empty else 'N/A',
                            self.content_table.loc[self.content_table['Margen de beneficio'].idxmin(), 'SKU'] if not self.content_table.empty else 'N/A',
                            len(self.clientes_dict)
                        ]
                    }
                    
                    df_estadisticas = pd.DataFrame(estadisticas)
                    df_estadisticas.to_excel(writer, sheet_name='Estadisticas', index=False)
                
                widget.QMessageBox.information(self, "Éxito", f"Archivo exportado correctamente:\n{ruta_archivo}")
                
            except Exception as e:
                widget.QMessageBox.critical(self, "Error", f"Error al exportar: {e}")