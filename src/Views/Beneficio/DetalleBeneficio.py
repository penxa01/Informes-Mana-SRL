import PyQt5.QtWidgets as widget
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Qt
import pandas as pd
from datetime import datetime


class _CostoDetalleDelegate(widget.QStyledItemDelegate):
    """Delegate para la columna Costo Unit. en el detalle de ventas."""

    def createEditor(self, parent, option, index):
        editor = widget.QLineEdit(parent)
        editor.setAlignment(Qt.Qt.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        # Mostrar el valor sin símbolo de moneda ni separadores de miles
        val = str(index.data(Qt.Qt.DisplayRole) or "0")
        val = val.replace('$', '').replace(',', '').strip()
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
            model.setData(index, f"${valor:,.2f}", Qt.Qt.DisplayRole)
        except ValueError:
            pass  # Valor inválido: mantener el anterior


class DetalleDialog(widget.QDialog):
    """Dialog para mostrar el detalle de ventas de un producto específico"""
    def __init__(self, sku, producto, detalle_ventas, clientes_dict=None, parent=None, on_costo_cambiado_cb=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle de Ventas - {sku}")
        self.setGeometry(150, 150, 1200, 600)
        self.clientes_dict = clientes_dict or {}
        self.detalle_ventas = detalle_ventas          # referencia mutable compartida con el padre
        self.on_costo_cambiado_cb = on_costo_cambiado_cb
        
        layout = widget.QVBoxLayout()
        
        # Título
        titulo = widget.QLabel(f"Producto: {producto} (SKU: {sku})")
        titulo.setFont(Gui.QFont("Arial", 12, Gui.QFont.Bold))
        layout.addWidget(titulo)
        
        # Estadísticas del producto
        total_unidades = sum(d['U_VENDIDAS'] for d in detalle_ventas)
        total_ventas = sum(d['TOTAVEN'] for d in detalle_ventas)
        total_beneficio = sum(d['MARGEN_UNITARIO'] * d['U_VENDIDAS'] for d in detalle_ventas)
        beneficio_promedio_unitario = total_beneficio / total_unidades if total_unidades > 0 else 0
        
        self.stats_label = widget.QLabel(
            f"Total Unidades: {total_unidades:,.0f} | "
            f"Total Ventas: ${total_ventas:,.2f} | "
            f"Total Beneficio: ${total_beneficio:,.2f} | "
            f"Beneficio Promedio por Unidad: ${beneficio_promedio_unitario:,.2f}"
        )
        self.stats_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc;")
        layout.addWidget(self.stats_label)
        
        # Tabla de detalles - AGREGADA COLUMNA CLIENTE
        self.tabla_detalle = widget.QTableWidget()
        self.tabla_detalle.setColumnCount(12)
        self.tabla_detalle.setHorizontalHeaderLabels([
            "Fecha", "Cliente", "Cuenta", "TC", "NC", "Unidades", "Total Venta", 
            "Precio Unit.", "Costo Unit.", "Beneficio Unit.", "Beneficio Total", "Margen %"
        ])
        
        # Configurar estilo de la tabla
        self.tabla_detalle.setStyleSheet("""
            QTableWidget {
                gridline-color: #bdc3c7;
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #ecf0f1;
            }
            QHeaderView::section {
                background-color: #495057;
                color: white;
                font-weight: bold;
                padding: 8px;
                border: none;
            }
        """)
        
        self.tabla_detalle.setAlternatingRowColors(True)
        
        # Llenar la tabla con los datos
        self.tabla_detalle.setRowCount(len(detalle_ventas))
        for i, venta in enumerate(detalle_ventas):
            # Calcular beneficio total para esta venta
            beneficio_total_venta = venta['MARGEN_UNITARIO'] * venta['U_VENDIDAS']
            costo_total = venta['PRECIO_COSTO'] * venta['U_VENDIDAS']
            margen_porcentual = (beneficio_total_venta / costo_total * 100) if costo_total > 0 else 0
            
            # Obtener nombre del cliente y convertir cuenta a entero
            cuenta_raw = venta.get('CUENTA', 'N/A')
            try:
                cuenta = str(int(float(cuenta_raw))) if cuenta_raw != 'N/A' else 'N/A'
            except (ValueError, TypeError):
                cuenta = str(cuenta_raw)
            
            nombre_cliente = self.clientes_dict.get(cuenta, cuenta)  # Solo número si no encuentra nombre
            
            # Fecha
            self.tabla_detalle.setItem(i, 0, widget.QTableWidgetItem(str(venta.get('FECHA', 'N/A'))))
            
            # Cliente (NUEVA COLUMNA)
            cliente_item = widget.QTableWidgetItem(nombre_cliente)
            cliente_item.setFont(Gui.QFont("Arial", 9, Gui.QFont.Bold))
            cliente_item.setForeground(Gui.QColor(25, 25, 112))  # Azul oscuro
            self.tabla_detalle.setItem(i, 1, cliente_item)
            
            # Cuenta (como entero)
            self.tabla_detalle.setItem(i, 2, widget.QTableWidgetItem(cuenta))
            
            # TC y NC
            self.tabla_detalle.setItem(i, 3, widget.QTableWidgetItem(str(venta.get('TC', 'N/A'))))
            self.tabla_detalle.setItem(i, 4, widget.QTableWidgetItem(str(venta.get('NC', 'N/A'))))
            
            # Unidades
            unidades_item = widget.QTableWidgetItem(f"{venta['U_VENDIDAS']:,.0f}")
            unidades_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            self.tabla_detalle.setItem(i, 5, unidades_item)
            
            # Total Venta
            total_item = widget.QTableWidgetItem(f"${venta['TOTAVEN']:,.2f}")
            total_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            self.tabla_detalle.setItem(i, 6, total_item)
            
            # Precio Unitario
            precio_unit_item = widget.QTableWidgetItem(f"${venta.get('PRECIO_UNITARIO', 0):,.2f}")
            precio_unit_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            self.tabla_detalle.setItem(i, 7, precio_unit_item)
            
            # Costo Unitario
            costo_item = widget.QTableWidgetItem(f"${venta.get('PRECIO_COSTO', 0):,.2f}")
            costo_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            self.tabla_detalle.setItem(i, 8, costo_item)
            
            # Beneficio Unitario
            beneficio_unit_item = widget.QTableWidgetItem(f"${venta['MARGEN_UNITARIO']:,.2f}")
            beneficio_unit_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            beneficio_unit_item.setFont(Gui.QFont("Arial", 9, Gui.QFont.Bold))
            
            # Colorear según si es positivo o negativo
            if venta['MARGEN_UNITARIO'] >= 0:
                beneficio_unit_item.setBackground(Gui.QColor(144, 238, 144))  # Verde más intenso
                beneficio_unit_item.setForeground(Gui.QColor(0, 100, 0))
            else:
                beneficio_unit_item.setBackground(Gui.QColor(255, 182, 193))  # Rosa más intenso
                beneficio_unit_item.setForeground(Gui.QColor(139, 0, 0))
                
            self.tabla_detalle.setItem(i, 9, beneficio_unit_item)
            
            # Beneficio Total
            beneficio_total_item = widget.QTableWidgetItem(f"${beneficio_total_venta:,.2f}")
            beneficio_total_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            beneficio_total_item.setFont(Gui.QFont("Arial", 9, Gui.QFont.Bold))
            
            # Colorear según si es positivo o negativo
            if beneficio_total_venta >= 0:
                beneficio_total_item.setBackground(Gui.QColor(144, 238, 144))  # Verde más intenso
                beneficio_total_item.setForeground(Gui.QColor(0, 100, 0))
            else:
                beneficio_total_item.setBackground(Gui.QColor(255, 182, 193))  # Rosa más intenso
                beneficio_total_item.setForeground(Gui.QColor(139, 0, 0))
                
            self.tabla_detalle.setItem(i, 10, beneficio_total_item)
            
            # Margen Porcentual
            margen_pct_item = widget.QTableWidgetItem(f"{margen_porcentual:.2f}%")
            margen_pct_item.setTextAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
            
            # Colorear según el porcentaje
            if margen_porcentual >= 0:
                margen_pct_item.setBackground(Gui.QColor(144, 238, 144))  # Verde más intenso
            else:
                margen_pct_item.setBackground(Gui.QColor(255, 182, 193))  # Rosa más intenso
                
            self.tabla_detalle.setItem(i, 11, margen_pct_item)
        
        # Ajustar tamaño de columnas
        self.tabla_detalle.resizeColumnsToContents()
        if self.tabla_detalle.columnWidth(1) < 200:
            self.tabla_detalle.setColumnWidth(1, 200)

        # Marcar todas las celdas como readonly excepto col 8 (Costo Unit.)
        for r in range(self.tabla_detalle.rowCount()):
            for c in range(self.tabla_detalle.columnCount()):
                if c == 8:
                    continue
                it = self.tabla_detalle.item(r, c)
                if it:
                    it.setFlags(it.flags() & ~Qt.Qt.ItemIsEditable)

        # Col 8 editable con delegate y tooltip
        self.tabla_detalle.setEditTriggers(widget.QAbstractItemView.DoubleClicked)
        self.tabla_detalle.setItemDelegateForColumn(8, _CostoDetalleDelegate(self.tabla_detalle))
        for r in range(self.tabla_detalle.rowCount()):
            it8 = self.tabla_detalle.item(r, 8)
            if it8:
                it8.setToolTip("Doble clic para editar el costo unitario. Presione Enter para confirmar.")
        self.tabla_detalle.cellChanged.connect(self._on_costo_cambiado)

        layout.addWidget(self.tabla_detalle)
        
        # Botones
        btn_layout = widget.QHBoxLayout()
        
        btn_exportar = widget.QPushButton("📊 Exportar Detalle")
        btn_exportar.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        btn_exportar.clicked.connect(lambda: self.exportar_detalle(sku, producto, detalle_ventas))
        btn_layout.addWidget(btn_exportar)
        
        btn_cerrar = widget.QPushButton("✖ Cerrar")
        btn_cerrar.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_cerrar.clicked.connect(self.accept)
        btn_layout.addWidget(btn_cerrar)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _actualizar_stats(self):
        """Recalcula y refresca el label de estadísticas usando los datos actualizados."""
        total_unidades = sum(d['U_VENDIDAS'] for d in self.detalle_ventas)
        total_ventas   = sum(d['TOTAVEN'] for d in self.detalle_ventas)
        total_beneficio = sum(d['MARGEN_UNITARIO'] * d['U_VENDIDAS'] for d in self.detalle_ventas)
        beneficio_prom  = total_beneficio / total_unidades if total_unidades > 0 else 0
        self.stats_label.setText(
            f"Total Unidades: {total_unidades:,.0f} | "
            f"Total Ventas: ${total_ventas:,.2f} | "
            f"Total Beneficio: ${total_beneficio:,.2f} | "
            f"Beneficio Promedio por Unidad: ${beneficio_prom:,.2f}"
        )

    def _on_costo_cambiado(self, fila, columna):
        """Recalcula beneficio/margen de la fila y cascadea al padre."""
        if columna != 8 or fila >= len(self.detalle_ventas):
            return

        costo_item = self.tabla_detalle.item(fila, 8)
        if costo_item is None:
            return

        # El delegate ya formateó como "$1,234.56" — parsear sin símbolos
        texto = costo_item.text().replace('$', '').replace(',', '').strip()
        try:
            nuevo_costo = float(texto)
        except ValueError:
            return

        detalle = self.detalle_ventas[fila]
        precio_venta = detalle.get('PRECIO_UNITARIO', 0)
        unidades     = detalle.get('U_VENDIDAS', 0)

        # Actualizar el dict compartido con el padre
        detalle['PRECIO_COSTO']    = nuevo_costo
        nuevo_margen_unit          = precio_venta - nuevo_costo
        detalle['MARGEN_UNITARIO'] = nuevo_margen_unit

        beneficio_total = nuevo_margen_unit * unidades
        costo_total     = nuevo_costo * unidades
        margen_pct      = (beneficio_total / costo_total * 100) if costo_total != 0 else 0

        # Actualizar celdas de esta fila sin reentrar en la señal
        self.tabla_detalle.blockSignals(True)
        try:
            item9 = self.tabla_detalle.item(fila, 9)
            if item9:
                item9.setText(f"${nuevo_margen_unit:,.2f}")
                item9.setBackground(Gui.QColor(144, 238, 144) if nuevo_margen_unit >= 0 else Gui.QColor(255, 182, 193))
                item9.setForeground(Gui.QColor(0, 100, 0) if nuevo_margen_unit >= 0 else Gui.QColor(139, 0, 0))

            item10 = self.tabla_detalle.item(fila, 10)
            if item10:
                item10.setText(f"${beneficio_total:,.2f}")
                item10.setBackground(Gui.QColor(144, 238, 144) if beneficio_total >= 0 else Gui.QColor(255, 182, 193))
                item10.setForeground(Gui.QColor(0, 100, 0) if beneficio_total >= 0 else Gui.QColor(139, 0, 0))

            item11 = self.tabla_detalle.item(fila, 11)
            if item11:
                item11.setText(f"{margen_pct:.2f}%")
                item11.setBackground(Gui.QColor(144, 238, 144) if margen_pct >= 0 else Gui.QColor(255, 182, 193))
        finally:
            self.tabla_detalle.blockSignals(False)

        # Actualizar stats del diálogo
        self._actualizar_stats()

        # Cascadear al padre (actualiza la fila del producto en la tabla general)
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
                # Preparar datos con cálculos adicionales
                datos_exportacion = []
                for venta in detalle_ventas:
                    beneficio_total = venta['MARGEN_UNITARIO'] * venta['U_VENDIDAS']
                    costo_total = venta['PRECIO_COSTO'] * venta['U_VENDIDAS']
                    margen_porcentual = (beneficio_total / costo_total * 100) if costo_total > 0 else 0
                    
                    # Obtener nombre del cliente y convertir cuenta a entero
                    cuenta_raw = venta.get('CUENTA', 'N/A')
                    try:
                        cuenta = str(int(float(cuenta_raw))) if cuenta_raw != 'N/A' else 'N/A'
                    except (ValueError, TypeError):
                        cuenta = str(cuenta_raw)
                    
                    nombre_cliente = self.clientes_dict.get(cuenta, cuenta)  # Solo número si no encuentra nombre
                    
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
                df_detalle.to_excel(ruta_archivo, index=False, sheet_name=f"Detalle_{sku}")
                widget.QMessageBox.information(self, "Éxito", f"Detalle exportado:\n{ruta_archivo}")
            except Exception as e:
                widget.QMessageBox.critical(self, "Error", f"Error al exportar: {e}")