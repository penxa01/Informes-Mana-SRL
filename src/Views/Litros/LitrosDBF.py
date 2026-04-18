import os
import re

import PyQt5.QtWidgets as widget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import pandas as pd
import numpy as np
from dbfread import DBF
import matplotlib.dates

from src.controllers import config
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import calendar

# Mapa explícito de CODMEDIDA → litros por unidad.
# Claves en minúsculas y sin espacios extra para comparación normalizada.
_CODMEDIDA_LITROS = {
    # ── Litros directos ──────────────────────────────────────────────────
    '0.5 l': 0.5,
    '1 lt': 1.0, '1 lts': 1.0,
    '4 lts': 4.0,
    '5 lts': 5.0, '5': 5.0,
    '8 lts': 8.0,
    '10l': 10.0,
    '15 lt': 15.0,
    '19 l': 19.0,
    '20 lt': 20.0,
    '100 l': 100.0,
    '200 l': 200.0,
    '204 l': 204.0,
    '205 l': 205.0, '205': 205.0,
    '208 l': 208.0,
    '209 l': 209.0,
    '240 l': 240.0,
    '250 l': 250.0,
    '1000': 1000.0,           # IBC 1000 LTS
    # ── Galones (1 gal US = 3.785411784 L) ──────────────────────────────
    '1 gl': 3.785,
    '1/4 g': 0.946,
    # ── cc / cm³ / mL  →  ÷ 1000 ────────────────────────────────────────
    '100 c': 0.1,
    '150': 0.15,
    '200': 0.2,
    '250': 0.25,
    '350 c': 0.35,
    '415': 0.415,
    '440': 0.44, '440 c': 0.44,
    '450 c': 0.45,
    '500 c': 0.5,
    # ── Onzas fluidas (1 fl oz = 0.029574 L) ────────────────────────────
    '12 oz': 0.355,
    '14 oz': 0.414,
    # ── Sin equivalencia en litros (unidades, kits, criques) ─────────────
    '1': 0.0, '1 uni': 0.0, 'kit': 0.0, 'cja10': 0.0,
    # TN = capacidad de carga en criques, no peso → 0 L
    '2 tn': 0.0, '3 tn': 0.0, '4 tn': 0.0, '5 tn': 0.0,
    '10 tn': 0.0, '15 tn': 0.0, '20 tn': 0.0, '30 tn': 0.0,
    # ── Kg → L  (1 kg = 1 L) ─────────────────────────────────────────────
    '1 kg': 1.0,
    '3.5 k': 3.5,
    '4 kg': 4.0,
    '5 kgs': 5.0,
    '16 kg': 16.0,
    '18 kg': 18.0,
    '20 kg': 20.0,
    '45 kg': 45.0,
    '170 k': 170.0,
    '180 k': 180.0,
    '190.5': 190.5,  # GADUS 190,5 KG
    '200k': 200.0,
    # ── Gramos → L  (÷ 1000) ─────────────────────────────────────────────
    '150 g': 0.15,
    '250 g': 0.25,
    '400 g': 0.4,
    '500 g': 0.5,
    '907 g': 0.907,
    # ── Libras → L  (1 lb = 0.453592 kg = 0.453592 L) ────────────────────
    '35 lb': 15.876,  # 35 × 0.453592
}

def _codmedida_a_litros(codmedida: str) -> float:
    """Convierte CODMEDIDA a litros por unidad. Retorna 0.0 si no aplica."""
    key = str(codmedida).strip().lower()
    if key in _CODMEDIDA_LITROS:
        return _CODMEDIDA_LITROS[key]
    # Fallback: extraer primer número (cubre nuevos códigos en L no mapeados)
    m = re.match(r'^(\d+(?:\.\d+)?)', key)
    if m:
        return float(m.group(1))
    return 0.0

# Para tooltips interactivos
try:
    import mplcursors
    MPLCURSORS_AVAILABLE = True
except ImportError:
    MPLCURSORS_AVAILABLE = False
    print("mplcursors no está disponible. Se usarán tooltips básicos.")

class InteractiveCanvas(FigureCanvas):
    """Canvas personalizado con tooltips mejorados"""
    
    def __init__(self, figure):
        super().__init__(figure)
        self.figure = figure
        self.tooltips = []
        self.annotation = None
        
    def setup_hover_annotations(self, plots_data):
        """Configurar anotaciones hover para múltiples líneas"""
        self.plots_data = plots_data
        
        if MPLCURSORS_AVAILABLE and plots_data:
            # Usar mplcursors si está disponible
            try:
                for plot_info in plots_data:
                    if 'plot' in plot_info and plot_info['plot'] is not None:
                        cursor = mplcursors.cursor(plot_info['plot'], hover=True)
                        cursor.connect("add", lambda sel, info=plot_info: self.on_hover_mplcursors(sel, info))
            except Exception as e:
                print(f"Error configurando mplcursors: {e}")
                # Fallback a tooltips manuales
                self.mpl_connect('motion_notify_event', self.on_hover_manual)
        else:
            # Fallback a tooltips manuales
            if hasattr(self, '_motion_event_id'):
                self.mpl_disconnect(self._motion_event_id)
            self._motion_event_id = self.mpl_connect('motion_notify_event', self.on_hover_manual)
    
    def on_hover_mplcursors(self, sel, plot_info):
        """Manejar hover con mplcursors"""
        try:
            # Obtener índice de manera más robusta
            if hasattr(sel, 'index'):
                index = sel.index
            elif hasattr(sel.target, 'index') and not isinstance(sel.target, np.ndarray):
                index = sel.target.index
            else:
                # Fallback: buscar el punto más cercano
                if hasattr(sel, 'target') and hasattr(sel.target, 'get_xydata'):
                    xy_data = sel.target.get_xydata()
                    target_x, target_y = sel.target_point if hasattr(sel, 'target_point') else (0, 0)
                    
                    # Encontrar el índice del punto más cercano
                    distances = np.sqrt((xy_data[:, 0] - target_x)**2 + (xy_data[:, 1] - target_y)**2)
                    index = np.argmin(distances)
                else:
                    index = 0
            
            # Validar que el índice esté en rango
            if index < len(plot_info['x_data']) and index < len(plot_info['y_data']):
                x_val = plot_info['x_data'][index]
                y_val = plot_info['y_data'][index]
                
                # Formatear fecha si es necesario
                if hasattr(x_val, 'strftime'):
                    x_str = x_val.strftime('%d/%m/%Y')
                elif isinstance(x_val, (int, float)):
                    # Para gráficos con posiciones numéricas (mensual)
                    if 'x_labels' in plot_info and index < len(plot_info['x_labels']):
                        x_str = plot_info['x_labels'][index]
                    else:
                        x_str = str(x_val)
                else:
                    x_str = str(x_val)
                
                # Formatear tooltip con información clara
                tooltip_text = f"{plot_info['label']}\n{x_str}\nLitros: {y_val:,.0f}"
                sel.annotation.set_text(tooltip_text)
                sel.annotation.get_bbox_patch().set(boxstyle="round,pad=0.5", 
                                                  facecolor='lightyellow', 
                                                  edgecolor='gray', 
                                                  alpha=0.9)
                sel.annotation.set_fontsize(10)
        except Exception as e:
            # Tooltip básico en caso de error
            try:
                y_val = plot_info['y_data'][0] if plot_info['y_data'] else 0
                sel.annotation.set_text(f"{plot_info['label']}\nLitros: {y_val:,.0f}")
            except:
                sel.annotation.set_text(f"{plot_info['label']}\nPunto seleccionado")
    
    def on_hover_manual(self, event):
        """Manejar hover manual (fallback)"""
        if event.inaxes is None:
            if self.annotation:
                self.annotation.set_visible(False)
                self.draw_idle()
            return
        
        # Buscar el punto más cercano
        closest_point = None
        min_distance = float('inf')
        
        for plot_info in self.plots_data:
            for i, (x, y) in enumerate(zip(plot_info['x_data'], plot_info['y_data'])):
                # Convertir coordenadas a píxeles para calcular distancia
                if hasattr(x, 'timestamp'):
                    x_coord = matplotlib.dates.date2num(x)
                elif pd.api.types.is_datetime64_any_dtype(type(x)):
                    x_coord = matplotlib.dates.date2num(x)
                else:
                    x_coord = x
                
                try:
                    distance = ((event.xdata - x_coord) ** 2 + (event.ydata - y) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_point = {
                            'x': x,
                            'y': y,
                            'label': plot_info['label'],
                            'x_labels': plot_info.get('x_labels', []),
                            'index': i
                        }
                except (TypeError, AttributeError):
                    # Skip if coordinates are invalid
                    continue
        
        # Mostrar tooltip si hay un punto cercano
        if closest_point and min_distance < 3.5:  # Umbral de cercanía aumentado significativamente para mejor precisión
            self.show_tooltip(event, closest_point)
        else:
            if self.annotation:
                self.annotation.set_visible(False)
                self.draw_idle()
    
    def show_tooltip(self, event, point_info):
        """Mostrar tooltip manual"""
        if not self.annotation:
            self.annotation = event.inaxes.annotate('', 
                                                  xy=(0, 0), 
                                                  xytext=(20, 20), 
                                                  textcoords="offset points",
                                                  bbox=dict(boxstyle="round,pad=0.5", 
                                                          facecolor='lightyellow', 
                                                          edgecolor='gray', 
                                                          alpha=0.9),
                                                  arrowprops=dict(arrowstyle="->", 
                                                                connectionstyle="arc3,rad=0"))
        
        # Formatear texto
        x_val = point_info['x']
        y_val = point_info['y']
        
        if hasattr(x_val, 'strftime'):
            x_str = x_val.strftime('%d/%m/%Y')
        elif pd.api.types.is_datetime64_any_dtype(type(x_val)):
            x_str = pd.to_datetime(x_val).strftime('%d/%m/%Y')
        elif isinstance(x_val, (int, float)) and point_info['x_labels']:
            index = point_info['index']
            if index < len(point_info['x_labels']):
                x_str = point_info['x_labels'][index]
            else:
                x_str = str(x_val)
        else:
            x_str = str(x_val)
        
        tooltip_text = f"{point_info['label']}\n{x_str}\nLitros: {y_val:,.0f}"
        
        # Actualizar posición y texto
        try:
            if hasattr(x_val, 'timestamp') or pd.api.types.is_datetime64_any_dtype(type(x_val)):
                x_coord = matplotlib.dates.date2num(x_val)
            else:
                x_coord = x_val
            
            self.annotation.xy = (x_coord, y_val)
            self.annotation.set_text(tooltip_text)
            self.annotation.set_visible(True)
            self.draw_idle()
        except Exception as e:
            # En caso de error, usar coordenadas del evento
            self.annotation.xy = (event.xdata, event.ydata)
            self.annotation.set_text(tooltip_text)
            self.annotation.set_visible(True)
            self.draw_idle()


class ReportLts(widget.QWidget):
    def __init__(self, df_periodo_ventas, df_ventas=None, graficos=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Informe de Litros")
        # Centrar ventana en la pantalla disponible
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        ancho = int(screen.width() * 0.85)
        alto = int(screen.height() * 0.85)
        x = screen.x() + (screen.width() - ancho) // 2
        y = screen.y() + (screen.height() - alto) // 2
        self.setGeometry(x, y, ancho, alto)
        self.index = 0
        self.TotalLts = 0
        self.TotalPremium = 0
        self.modified = False
        self.mostrar_graficos = graficos
        
        # Dataframes
        self.periodoVentas = df_periodo_ventas[["FECHA", "TC", "MODELO", "U_VENDIDAS"]]
        self.df_ventas_completo = df_ventas  # DataFrame completo para comparaciones anuales
        _df_abm = pd.DataFrame(iter(DBF(os.path.join(config.DBF_BASE_PATH, "abmartic.DBF"), encoding="latin1")))
        self.bdArt = _df_abm[["CODART", "DESC", "CODMEDIDA"]]
        self.Clasificacion = pd.read_excel(config.EXCEL_LITROS_PATH, sheet_name="GENERAL")
        self.Clasificacion = self.Clasificacion[["articulo", "Clasificacion", "Artiprov"]]
        self.content_table = pd.DataFrame(columns=["Codigo de Producto", "Descripcion", "Unidades Vendidas", "Litros", "Proveedor", "Premium"])
        
        # Configurar estilo
        self.configurar_estilo()
        
        # Layout principal
        if self.mostrar_graficos:
            # Layout con splitter si se muestran gráficos
            self.layout_principal = widget.QHBoxLayout(self)
            self.splitter = widget.QSplitter(Qt.Horizontal)
            
            # Panel izquierdo - Datos
            self.panel_datos = widget.QWidget()
            self.setup_panel_datos()
            
            # Panel derecho - Gráficos
            self.panel_graficos = widget.QWidget()
            self.setup_panel_graficos()
            
            # Agregar paneles al splitter
            self.splitter.addWidget(self.panel_datos)
            self.splitter.addWidget(self.panel_graficos)
            self.splitter.setSizes([750, 250])  # 3/4 tabla, 1/4 gráficos
            
            self.layout_principal.addWidget(self.splitter)
        else:
            # Layout simple sin gráficos
            self.layout_principal = widget.QVBoxLayout(self)
            self.panel_datos = widget.QWidget()
            self.setup_panel_datos()
            self.layout_principal.addWidget(self.panel_datos)
        
        # Cargar datos
        self.LoadContent()
        self.content_table.sort_values(by=["Codigo de Producto"], ascending=True, inplace=True)
        self.actualizar_totales()
        self.showContent(self.content_table)
        
        # Maximizar la ventana al abrirse
        self.showMaximized()

    def configurar_estilo(self):
        """Configurar estilo general de la aplicación"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #f8f9fa, stop: 1 #ecf0f1);
                color: #2c3e50;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #2c3e50;
                font-size: 11px;
            }
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #3498db, stop: 1 #2980b9);
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #2980b9, stop: 1 #1f618d);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #1f618d, stop: 1 #15465d);
            }
            QLineEdit {
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                background-color: white;
                selection-background-color: #3498db;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background-color: #f0f7ff;
            }
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                selection-background-color: #3498db;
                gridline-color: #e0e6ed;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 5px;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QHeaderView::section {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #34495e, stop: 1 #2c3e50);
                color: white;
                padding: 8px;
                border: none;
                border-right: 1px solid #27313d;
                font-weight: bold;
                font-size: 10px;
            }
            QListWidget {
                background-color: white;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 4px;
                font-size: 10px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #ecf0f1;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item:hover {
                background-color: #ecf3f9;
                color: #2c3e50;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #3498db, stop: 1 #2980b9);
                color: white;
                font-weight: bold;
            }
            QCheckBox {
                color: #2c3e50;
                spacing: 8px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:checked {
                background-color: #27ae60;
                border: 2px solid #27ae60;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
                border: 2px solid #bdc3c7;
                border-radius: 3px;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #3498db;
            }
        """)

    def setup_panel_datos(self):
        """Configurar el panel de datos (izquierdo)"""
        layout_datos = widget.QVBoxLayout(self.panel_datos)
        layout_datos.setContentsMargins(10, 10, 10, 10)
        layout_datos.setSpacing(10)
        
        # Grupo de filtros
        grupo_filtros = widget.QGroupBox("Filtros")
        layout_filtros = widget.QVBoxLayout(grupo_filtros)
        
        # Filtro por nombre
        layout_nombre = widget.QHBoxLayout()
        self.filtro_nombre = widget.QLineEdit()
        self.filtro_nombre.setPlaceholderText("Filtrar por nombre de producto...")
        self.filtro_nombre.textChanged.connect(self.aplicar_filtro)
        layout_nombre.addWidget(widget.QLabel("Producto:"))
        layout_nombre.addWidget(self.filtro_nombre)
        layout_filtros.addLayout(layout_nombre)
        
        # Checkboxes de proveedor
        layout_proveedores = widget.QHBoxLayout()
        self.filtro_shell = widget.QCheckBox("SHELL")
        self.filtro_valvoline = widget.QCheckBox("VALVOLINE")
        self.filtro_otros = widget.QCheckBox("OTROS")
        self.filtro_shell.stateChanged.connect(self.aplicar_filtro)
        self.filtro_valvoline.stateChanged.connect(self.aplicar_filtro)
        self.filtro_otros.stateChanged.connect(self.aplicar_filtro)
        layout_proveedores.addWidget(self.filtro_shell)
        layout_proveedores.addWidget(self.filtro_valvoline)
        layout_proveedores.addWidget(self.filtro_otros)
        layout_filtros.addLayout(layout_proveedores)

        # Checkbox Premium
        self.filtro_premium = widget.QCheckBox("Solo productos Premium (Shell)")
        self.filtro_premium.stateChanged.connect(self.aplicar_filtro)
        layout_filtros.addWidget(self.filtro_premium)

        layout_datos.addWidget(grupo_filtros)
        
        # Tabla de productos
        grupo_tabla = widget.QGroupBox("Productos")
        layout_tabla = widget.QVBoxLayout(grupo_tabla)
        
        self.tabla_produc = widget.QTableWidget()
        self.tabla_produc.setColumnCount(6)
        self.tabla_produc.setHorizontalHeaderLabels(self.content_table.columns)
        self.tabla_produc.setAlternatingRowColors(True)
        self.tabla_produc.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self.tabla_produc.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla_produc.itemSelectionChanged.connect(self.on_producto_seleccionado)
        # Modos de redimensionamiento responsivos por columna
        header = self.tabla_produc.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, widget.QHeaderView.ResizeToContents)  # Código
        header.setSectionResizeMode(1, widget.QHeaderView.Stretch)            # Descripción
        header.setSectionResizeMode(2, widget.QHeaderView.ResizeToContents)  # Unidades Vendidas
        header.setSectionResizeMode(3, widget.QHeaderView.ResizeToContents)  # Litros
        header.setSectionResizeMode(4, widget.QHeaderView.ResizeToContents)  # Proveedor
        header.setSectionResizeMode(5, widget.QHeaderView.ResizeToContents)  # Premium
        self.tabla_produc.setColumnWidth(2, 110)
        self.tabla_produc.setColumnWidth(3, 110)
        self.tabla_produc.setColumnWidth(4, 100)
        self.tabla_produc.setColumnWidth(5, 100)
        font_tabla = QFont("Segoe UI", 8)
        self.tabla_produc.setFont(font_tabla)
        self.tabla_produc.verticalHeader().setDefaultSectionSize(24)
        
        layout_tabla.addWidget(self.tabla_produc)
        layout_datos.addWidget(grupo_tabla, 1)  # Proporción 1 para que ocupe más espacio
        
        # Totales
        grupo_totales = widget.QGroupBox("Resumen")
        layout_totales = widget.QVBoxLayout(grupo_totales)
        layout_totales.setContentsMargins(10, 10, 10, 10)
        layout_totales.setSpacing(8)
        
        # Total litros
        layout_total_litros = widget.QHBoxLayout()
        self.label_total_litros = widget.QLabel("Total Litros:")
        self.label_total_litros.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.line_total_litros = widget.QLineEdit()
        self.line_total_litros.setReadOnly(True)
        self.line_total_litros.setStyleSheet("background-color: #e8f6f3; font-weight: bold; font-size: 12px;")
        layout_total_litros.addWidget(self.label_total_litros)
        layout_total_litros.addWidget(self.line_total_litros)

        # Total premium
        layout_total_premium = widget.QHBoxLayout()
        self.label_total_premium = widget.QLabel("Total Premium:")
        self.label_total_premium.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.line_total_premium = widget.QLineEdit()
        self.line_total_premium.setReadOnly(True)
        self.line_total_premium.setStyleSheet("background-color: #fdf2e9; font-weight: bold; font-size: 12px;")
        layout_total_premium.addWidget(self.label_total_premium)
        layout_total_premium.addWidget(self.line_total_premium)
        
        layout_totales.addLayout(layout_total_litros)
        layout_totales.addLayout(layout_total_premium)
        layout_datos.addWidget(grupo_totales, 0)  # Sin expansión, tamaño fijo
        
        # Asegurar que el layout principal se expanda correctamente
        layout_datos.addStretch(0)

    def setup_panel_graficos(self):
        """Configurar el panel de gráficos (derecho)"""
        if not self.mostrar_graficos:
            return
            
        layout_graficos = widget.QVBoxLayout(self.panel_graficos)
        layout_graficos.setContentsMargins(6, 6, 6, 6)
        layout_graficos.setSpacing(6)

        # Grupo de controles compacto
        grupo_controles = widget.QGroupBox("Análisis")
        layout_controles = widget.QVBoxLayout(grupo_controles)
        layout_controles.setContentsMargins(6, 8, 6, 6)
        layout_controles.setSpacing(4)

        # Botón de control
        self.btn_generar_histograma = widget.QPushButton("Generar Histograma Comparativo")
        self.btn_generar_histograma.clicked.connect(self.generar_histograma_comparativo)
        layout_controles.addWidget(self.btn_generar_histograma)

        # Búsqueda y lista en layout horizontal compacto
        lbl_prod = widget.QLabel("Productos:")
        lbl_prod.setStyleSheet("font-size: 10px; color: #34495e;")
        layout_controles.addWidget(lbl_prod)

        self.buscar_producto = widget.QLineEdit()
        self.buscar_producto.setPlaceholderText("Buscar producto...")
        self.buscar_producto.textChanged.connect(self.filtrar_lista_productos)
        layout_controles.addWidget(self.buscar_producto)

        self.lista_productos = widget.QListWidget()
        self.lista_productos.setMaximumHeight(100)
        self.lista_productos.setMinimumHeight(60)
        self.lista_productos.itemChanged.connect(self.actualizar_grafico_productos_seleccionados)
        layout_controles.addWidget(self.lista_productos)

        self.label_seleccionados = widget.QLabel("Seleccionados: 0")
        self.label_seleccionados.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 10px;")
        layout_controles.addWidget(self.label_seleccionados)

        layout_graficos.addWidget(grupo_controles, 0)  # tamaño fijo

        # Área del gráfico - ocupa todo el espacio restante
        grupo_grafico = widget.QGroupBox("Gráfico Comparativo")
        layout_grafico = widget.QVBoxLayout(grupo_grafico)
        layout_grafico.setContentsMargins(4, 8, 4, 4)

        self.figure = Figure(dpi=90)
        self.figure.patch.set_facecolor('#fafafa')
        self.canvas = InteractiveCanvas(self.figure)
        layout_grafico.addWidget(self.canvas)

        layout_graficos.addWidget(grupo_grafico, 1)  # se expande

    def _clasificar_proveedor(self, sku):
        sku = str(sku).strip()
        if sku.upper().startswith('L'):
            return 'SHELL'
        if re.match(r'^\d{2}[A-Za-z]{2}\d{3}$', sku):
            return 'VALVOLINE'
        return 'OTROS'

    def LoadContent(self):
        """Cargar contenido de la tabla con todos los productos del período"""
        for index, row in self.periodoVentas.iterrows():
            try:
                sku = str(row["MODELO"]).strip()
                producto_info = self.bdArt[self.bdArt["CODART"] == row["MODELO"]]

                if producto_info.empty:
                    continue

                descripcion = producto_info["DESC"].values[0]
                unidades_vendidas = int(row["U_VENDIDAS"])
                codmedida = str(producto_info["CODMEDIDA"].values[0])
                litros_por_unidad = _codmedida_a_litros(codmedida)
                litros = round(unidades_vendidas * litros_por_unidad, 2)
                proveedor = self._clasificar_proveedor(sku)

                if proveedor == 'SHELL':
                    clasificacion_info = self.Clasificacion[
                        (self.Clasificacion["articulo"] == row["MODELO"]) |
                        (self.Clasificacion["Artiprov"] == row["MODELO"])
                    ]
                    premium = clasificacion_info["Clasificacion"].values[0] if not clasificacion_info.empty else "-"
                else:
                    premium = "-"

                if sku not in self.content_table["Codigo de Producto"].values:
                    nueva_fila = {
                        "Codigo de Producto": sku,
                        "Descripcion": descripcion,
                        "Unidades Vendidas": unidades_vendidas,
                        "Litros": litros,
                        "Proveedor": proveedor,
                        "Premium": premium
                    }
                    self.content_table = pd.concat([self.content_table, pd.DataFrame([nueva_fila])], ignore_index=True)
                else:
                    self.content_table.loc[self.content_table["Codigo de Producto"] == sku, "Unidades Vendidas"] += unidades_vendidas
                    self.content_table.loc[self.content_table["Codigo de Producto"] == sku, "Litros"] += litros

                self.TotalLts += litros
                if premium == "Premium":
                    self.TotalPremium += litros

            except Exception as e:
                print(f"Error al cargar el producto {row['MODELO']}: {str(e)}")

        # Llenar lista de productos
        self.actualizar_lista_productos()

    def actualizar_lista_productos(self):
        """Actualizar la lista de productos con checkboxes"""
        if not self.mostrar_graficos:
            return
            
        self.lista_productos.clear()
        
        # Agregar productos individuales con checkboxes
        for _, producto in self.content_table.iterrows():
            codigo = producto["Codigo de Producto"]
            descripcion = producto["Descripcion"]
            
            texto = f"{codigo} - {descripcion[:40]}..."
            item = widget.QListWidgetItem(texto)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, codigo)
            self.lista_productos.addItem(item)

    def filtrar_lista_productos(self):
        """Filtrar productos en la lista basado en el texto de búsqueda"""
        if not self.mostrar_graficos:
            return
            
        texto_busqueda = self.buscar_producto.text().lower().strip()
        
        for i in range(self.lista_productos.count()):
            item = self.lista_productos.item(i)
            
            # Buscar en código y descripción
            codigo = item.data(Qt.UserRole)
            producto_info = self.content_table[self.content_table["Codigo de Producto"] == codigo]
            
            if not producto_info.empty:
                descripcion = producto_info["Descripcion"].iloc[0].lower()
                texto_completo = f"{codigo.lower()} {descripcion}"
                
                # Mostrar solo si coincide con la búsqueda
                mostrar = not texto_busqueda or texto_busqueda in texto_completo
                item.setHidden(not mostrar)

    def obtener_productos_seleccionados(self):
        """Obtener lista de códigos de productos con checkbox marcado"""
        productos_seleccionados = []
        
        for i in range(self.lista_productos.count()):
            item = self.lista_productos.item(i)
            if item.checkState() == Qt.Checked:
                codigo = item.data(Qt.UserRole)
                productos_seleccionados.append(codigo)
        
        return productos_seleccionados

    def actualizar_grafico_productos_seleccionados(self):
        """Actualizar gráfico para productos seleccionados (suma de litros)"""
        productos_seleccionados = self.obtener_productos_seleccionados()
        
        # Actualizar label indicador
        self.label_seleccionados.setText(f"Productos seleccionados: {len(productos_seleccionados)}")
        
        if not productos_seleccionados:
            # Si no hay productos seleccionados, mostrar gráfico general
            self.generar_histograma_comparativo()
        else:
            # Mostrar gráfico de suma de productos seleccionados
            self.generar_histograma_suma_productos(productos_seleccionados)

    def generar_histograma_suma_productos(self, productos_seleccionados):
        """Generar gráfico de líneas con la suma de litros de productos seleccionados"""
        if not self.mostrar_graficos or not productos_seleccionados:
            return
            
        if self.periodoVentas.empty:
            return
            
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        # Filtrar datos para productos seleccionados
        datos_filtrados = self.periodoVentas[self.periodoVentas['MODELO'].isin(productos_seleccionados)].copy()
        
        if datos_filtrados.empty:
            ax.text(0.5, 0.5, 'No hay datos para los productos seleccionados', 
                   ha='center', va='center', transform=ax.transAxes, fontsize=12)
            ax.set_facecolor('#fafafa')
            self.canvas.draw()
            return
        
        # Convertir fechas
        datos_filtrados.loc[:, 'FECHA'] = pd.to_datetime(datos_filtrados['FECHA'])
        fecha_min = datos_filtrados['FECHA'].min()
        fecha_max = datos_filtrados['FECHA'].max()
        dias_diferencia = (fecha_max - fecha_min).days
        
        # Calcular litros por cada venta
        litros_por_producto = {}
        for codigo in productos_seleccionados:
            info_producto = self.content_table[self.content_table['Codigo de Producto'] == codigo]
            if not info_producto.empty:
                litros_por_unidad = info_producto['Litros'].iloc[0] / info_producto['Unidades Vendidas'].iloc[0]
                litros_por_producto[codigo] = litros_por_unidad
        
        datos_filtrados.loc[:, 'Litros'] = datos_filtrados.apply(
            lambda row: row['U_VENDIDAS'] * litros_por_producto.get(row['MODELO'], 0), axis=1
        )
        
        # Preparar datos para tooltips
        plots_data = []
        
        # Datos del año anterior
        datos_anteriores = None
        if self.df_ventas_completo is not None:
            datos_anteriores = self.obtener_datos_anio_anterior_suma_productos(productos_seleccionados, fecha_min, fecha_max)
        
        if dias_diferencia <= 31:
            # Gráfico diario - sumar por fecha
            datos_agrupados_actual = datos_filtrados.groupby('FECHA')['Litros'].sum().reset_index()
            datos_agrupados_actual = datos_agrupados_actual.sort_values('FECHA')
            
            if not datos_agrupados_actual.empty:
                line_actual, = ax.plot(datos_agrupados_actual['FECHA'], datos_agrupados_actual['Litros'], 
                                     marker='o', linewidth=3, markersize=8, 
                                     color='#3498db', markerfacecolor='#2980b9', 
                                     markeredgecolor='white', markeredgewidth=2,
                                     label=f'Productos Seleccionados - Año {datos_agrupados_actual["FECHA"].dt.year.iloc[0]}',
                                     zorder=3)
                
                ax.fill_between(datos_agrupados_actual['FECHA'], datos_agrupados_actual['Litros'], 
                               alpha=0.25, color='#3498db', zorder=1)
                
                # Agregar datos para tooltips
                plots_data.append({
                    'plot': line_actual,
                    'x_data': datos_agrupados_actual['FECHA'].tolist(),
                    'y_data': datos_agrupados_actual['Litros'].tolist(),
                    'label': f'Productos Seleccionados ({len(productos_seleccionados)})'
                })
            
            # Año anterior si existe
            if datos_anteriores is not None and not datos_anteriores.empty:
                line_anterior, = ax.plot(datos_anteriores['FECHA'], datos_anteriores['Litros'], 
                                       marker='s', linewidth=3, markersize=8, 
                                       color='#e74c3c', markerfacecolor='#c0392b', 
                                       markeredgecolor='white', markeredgewidth=2,
                                       label=f'Productos Seleccionados - Año {datos_anteriores["FECHA"].dt.year.iloc[0]}',
                                       zorder=2, linestyle='--', alpha=0.8)
                
                ax.fill_between(datos_anteriores['FECHA'], datos_anteriores['Litros'], 
                               alpha=0.15, color='#e74c3c', zorder=0)
                
                plots_data.append({
                    'plot': line_anterior,
                    'x_data': datos_anteriores['FECHA'].tolist(),
                    'y_data': datos_anteriores['Litros'].tolist(),
                    'label': f'Productos Seleccionados - Año Anterior ({len(productos_seleccionados)})'
                })
            
            ax.set_title(f'Suma de {len(productos_seleccionados)} Productos Seleccionados (Diario)', 
                        fontsize=15, fontweight='bold', color='#2c3e50', pad=20)
            ax.tick_params(axis='x', rotation=45, labelsize=9)
            ax.tick_params(axis='y', labelsize=10)
        else:
            # Gráfico mensual - sumar por mes
            datos_filtrados.loc[:, 'Mes'] = datos_filtrados['FECHA'].dt.to_period('M')
            datos_agrupados_actual = datos_filtrados.groupby('Mes')['Litros'].sum().reset_index()
            datos_agrupados_actual = datos_agrupados_actual.sort_values('Mes')
            
            if not datos_agrupados_actual.empty:
                meses_str = [str(mes) for mes in datos_agrupados_actual['Mes']]
                meses_labels = [calendar.month_name[int(mes.split('-')[1])][:3] + ' ' + mes.split('-')[0] for mes in meses_str]
                x_pos = range(len(meses_str))
                
                line_actual, = ax.plot(x_pos, datos_agrupados_actual['Litros'], 
                                     marker='o', linewidth=3, markersize=10, 
                                     color='#3498db', markerfacecolor='#2980b9', 
                                     markeredgecolor='white', markeredgewidth=2,
                                     label='Productos Seleccionados - Año Actual',
                                     zorder=3)
                
                ax.fill_between(x_pos, datos_agrupados_actual['Litros'], alpha=0.3, color='#3498db', zorder=1)
                
                plots_data.append({
                    'plot': line_actual,
                    'x_data': x_pos,
                    'y_data': datos_agrupados_actual['Litros'].tolist(),
                    'label': f'Productos Seleccionados ({len(productos_seleccionados)})',
                    'x_labels': meses_labels
                })
                
                # Año anterior si existe
                if datos_anteriores is not None and not datos_anteriores.empty:
                    datos_anteriores.loc[:, 'Mes'] = datos_anteriores['FECHA'].dt.to_period('M')
                    datos_agrupados_anterior = datos_anteriores.groupby('Mes')['Litros'].sum().reset_index()
                    
                    if len(datos_agrupados_anterior) == len(x_pos):
                        line_anterior, = ax.plot(x_pos, datos_agrupados_anterior['Litros'], 
                                           marker='s', linewidth=3, markersize=10, 
                                           color='#e74c3c', markerfacecolor='#c0392b', 
                                           markeredgecolor='white', markeredgewidth=2,
                                           label='Productos Seleccionados - Año Anterior',
                                           zorder=2, linestyle='--', alpha=0.8)
                        
                        ax.fill_between(x_pos, datos_agrupados_anterior['Litros'], alpha=0.2, color='#e74c3c', zorder=0)
                        plots_data.append({
                            'plot': line_anterior,
                            'x_data': x_pos,
                            'y_data': datos_agrupados_anterior['Litros'].tolist(),
                            'label': f'Productos Seleccionados - Año Anterior ({len(productos_seleccionados)})',
                            'x_labels': meses_labels
                        })
                
                ax.set_xticks(x_pos)
                ax.set_xticklabels([mes.split('-')[1] for mes in meses_str], rotation=45)
            
            ax.set_title(f'Suma de {len(productos_seleccionados)} Productos Seleccionados (Mensual)', 
                        fontsize=15, fontweight='bold', color='#2c3e50', pad=20)
        
        ax.set_xlabel('Mes', fontweight='bold', fontsize=11, color='#34495e')
        ax.set_ylabel('Litros', fontweight='bold', fontsize=11, color='#34495e')
        ax.tick_params(axis='x', labelsize=9)
        ax.tick_params(axis='y', labelsize=10)
        ax.grid(True, alpha=0.4, linestyle='--', linewidth=0.8, color='#bdc3c7')
        ax.set_facecolor('#fafafa')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=10)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_edgecolor('#bdc3c7')
        legend.get_frame().set_alpha(0.95)
        self.figure.tight_layout()
        
        ax.set_xlabel('Período', fontweight='bold', fontsize=11, color='#34495e')
        ax.set_ylabel('Litros', fontweight='bold', fontsize=11, color='#34495e')
        ax.grid(True, alpha=0.4, linestyle='--', linewidth=0.8, color='#bdc3c7')
        ax.set_facecolor('#fafafa')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=10)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_edgecolor('#bdc3c7')
        legend.get_frame().set_alpha(0.95)
        self.figure.tight_layout()
        
        # Configurar tooltips interactivos
        if plots_data:
            self.canvas.setup_hover_annotations(plots_data)
        
        self.canvas.draw()

    def obtener_datos_anio_anterior_suma_productos(self, productos_seleccionados, fecha_min, fecha_max):
        """Obtener datos del año anterior para suma de productos seleccionados"""
        if self.df_ventas_completo is None:
            return None
            
        try:
            fecha_min_anterior = fecha_min - pd.DateOffset(years=1)
            fecha_max_anterior = fecha_max - pd.DateOffset(years=1)
            
            # Filtrar datos del año anterior para productos seleccionados
            df_ventas_anterior = self.df_ventas_completo.copy()
            df_ventas_anterior.loc[:, 'FECHA'] = pd.to_datetime(df_ventas_anterior['FECHA'])
            
            datos_anterior = df_ventas_anterior[
                (df_ventas_anterior['FECHA'] >= fecha_min_anterior) &
                (df_ventas_anterior['FECHA'] <= fecha_max_anterior) &
                (df_ventas_anterior['MODELO'].isin(productos_seleccionados)) &
                ((df_ventas_anterior['TC'] == 'FC') | (df_ventas_anterior['TC'] == 'NC') | (df_ventas_anterior['TC'] == 'ND')| (df_ventas_anterior['TC'] == 'FE')| (df_ventas_anterior['TC'] == 'CR'))
            ][["FECHA", "TC", "MODELO", "U_VENDIDAS"]]
            
            if datos_anterior.empty:
                return None
            
            # Calcular litros usando la misma información de productos
            litros_por_producto = {}
            for codigo in productos_seleccionados:
                info_producto = self.content_table[self.content_table['Codigo de Producto'] == codigo]
                if not info_producto.empty:
                    litros_por_unidad = info_producto['Litros'].iloc[0] / info_producto['Unidades Vendidas'].iloc[0]
                    litros_por_producto[codigo] = litros_por_unidad
            
            datos_anterior.loc[:, 'Litros'] = datos_anterior.apply(
                lambda row: row['U_VENDIDAS'] * litros_por_producto.get(row['MODELO'], 0), axis=1
            )
            
            # Ajustar fechas para mostrar en el mismo eje temporal
            datos_anterior.loc[:, 'FECHA'] = datos_anterior['FECHA'] + pd.DateOffset(years=1)
            
            return datos_anterior
            
        except Exception as e:
            print(f"Error al obtener datos del año anterior: {e}")
            return None

    def aplicar_filtro(self):
        """Filtrar por proveedor, nombre y premium, y recalcular totales"""
        df_filtrado = self.content_table.copy()

        # Filtro por proveedor (checkboxes SHELL / VALVOLINE / OTROS)
        proveedores_seleccionados = []
        if self.filtro_shell.isChecked():
            proveedores_seleccionados.append("SHELL")
        if self.filtro_valvoline.isChecked():
            proveedores_seleccionados.append("VALVOLINE")
        if self.filtro_otros.isChecked():
            proveedores_seleccionados.append("OTROS")
        if proveedores_seleccionados:
            df_filtrado = df_filtrado[df_filtrado["Proveedor"].isin(proveedores_seleccionados)]

        filtro_nombre = self.filtro_nombre.text().strip().lower()
        if filtro_nombre:
            df_filtrado = df_filtrado[df_filtrado["Descripcion"].str.lower().str.contains(filtro_nombre, na=False)]

        if self.filtro_premium.isChecked():
            df_filtrado = df_filtrado[df_filtrado["Premium"] == "Premium"]

        self.showContent(df_filtrado)

        self.TotalLts = df_filtrado["Litros"].sum() if "Litros" in df_filtrado.columns else 0
        self.TotalPremium = df_filtrado[df_filtrado["Premium"] == "Premium"]["Litros"].sum() if "Litros" in df_filtrado.columns else 0

        self.actualizar_totales()

    def actualizar_totales(self):
        """Actualizar los displays de totales"""
        def fmt(v):
            return f"{v:,.0f}" if float(v) == int(float(v)) else f"{v:,.2f}"
        self.line_total_litros.setText(fmt(self.TotalLts))
        self.line_total_premium.setText(fmt(self.TotalPremium))

    def showContent(self, df):
        """Mostrar contenido en la tabla con formato mejorado"""
        df_mostrar = df.loc[:, [col for col in self.content_table.columns if col in df.columns]]
        self.tabla_produc.setRowCount(0)
        self.tabla_produc.setColumnCount(len(self.content_table.columns))
        self.tabla_produc.setHorizontalHeaderLabels(self.content_table.columns)
        
        for i, (_, fila) in enumerate(df_mostrar.iterrows()):
            self.tabla_produc.insertRow(i)
            
            for j, valor in enumerate(fila):
                if j == 2:  # Unidades Vendidas
                    item = widget.QTableWidgetItem(f"{int(valor):,}")
                elif j == 3:  # Litros
                    v = float(valor)
                    item = widget.QTableWidgetItem(f"{v:,.0f}" if v == int(v) else f"{v:,.2f}")
                elif j == 1:  # Descripción
                    item = widget.QTableWidgetItem(str(valor)[:80])
                else:
                    item = widget.QTableWidgetItem(str(valor))

                if j in [2, 3]:  # Columnas numéricas
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    item.setForeground(QColor('#27ae60'))
                    item.setFont(QFont('Segoe UI', 9, QFont.Bold))
                elif j == 4:  # Proveedor
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    colores_proveedor = {
                        'SHELL': ('#fff0e0', '#b84c00'),
                        'VALVOLINE': ('#e8f0ff', '#1a3a8c'),
                        'OTROS': ('#f5f5f5', '#555555'),
                    }
                    bg, fg = colores_proveedor.get(str(valor), ('#f5f5f5', '#555555'))
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                    item.setFont(QFont('Segoe UI', 9, QFont.Bold))
                elif j == 5:  # Premium
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    if str(valor).lower() == 'premium':
                        item.setBackground(QColor('#fff3cd'))
                        item.setForeground(QColor('#856404'))
                        item.setFont(QFont('Segoe UI', 9, QFont.Bold))
                    elif str(valor) == '-':
                        item.setForeground(QColor('#aaaaaa'))
                    else:
                        item.setBackground(QColor('#e8f5e9'))
                        item.setForeground(QColor('#2e7d32'))
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                
                # Aplicar color de fondo alterno
                if i % 2 == 0:
                    item.setBackground(QColor('#ffffff'))
                else:
                    item.setBackground(QColor('#f8f9fa'))
                
                self.tabla_produc.setItem(i, j, item)
                
            self.tabla_produc.setRowHeight(i, 28)

    def on_producto_seleccionado(self):
        """Manejar selección de producto en la tabla"""
        if not self.mostrar_graficos:
            return
            
        if self.tabla_produc.currentRow() >= 0:
            codigo_producto = self.tabla_produc.item(self.tabla_produc.currentRow(), 0).text()
            
            # Buscar el item correspondiente y marcarlo
            for i in range(self.lista_productos.count()):
                item = self.lista_productos.item(i)
                if item.data(Qt.UserRole) == codigo_producto:
                    # Alternar el estado del checkbox
                    if item.checkState() == Qt.Checked:
                        item.setCheckState(Qt.Unchecked)
                    else:
                        item.setCheckState(Qt.Checked)
                    self.lista_productos.scrollToItem(item)
                    break

    def generar_histograma_comparativo(self):
        """Generar histograma comparativo con año anterior por defecto"""
        if self.periodoVentas.empty:
            widget.QMessageBox.warning(self, "Advertencia", "No hay datos para mostrar")
            return
            
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        # Convertir fechas usando .loc para evitar warning
        self.periodoVentas = self.periodoVentas.copy()  # Hacer una copia para evitar warnings
        self.periodoVentas.loc[:, 'FECHA'] = pd.to_datetime(self.periodoVentas['FECHA'])
        fecha_min = self.periodoVentas['FECHA'].min()
        fecha_max = self.periodoVentas['FECHA'].max()
        
        # Determinar si es día a día o mes a mes
        dias_diferencia = (fecha_max - fecha_min).days
        
        if dias_diferencia <= 31:  # Menos de un mes
            self.generar_histograma_diario_comparativo(ax)
        else:  # Más de un mes
            self.generar_histograma_mensual_comparativo(ax)

    def generar_histograma_diario_comparativo(self, ax):
        """Generar gráfico de líneas día a día comparativo con tooltips"""
        # Datos del año actual
        df_con_litros = self.calcular_litros_por_fecha()
        datos_actuales = df_con_litros.groupby('FECHA')['Litros'].sum().reset_index()
        datos_actuales = datos_actuales.sort_values('FECHA')
        
        # Datos del año anterior
        datos_anteriores = None
        if self.df_ventas_completo is not None:
            datos_anteriores = self.obtener_datos_anio_anterior_diario(datos_actuales)
        
        # Preparar datos para tooltips
        plots_data = []
        
        # Gráfico de líneas para año actual con mejor estética
        line_actual, = ax.plot(datos_actuales['FECHA'], datos_actuales['Litros'], 
                              marker='o', linewidth=3, markersize=8, 
                              color='#3498db', markerfacecolor='#2980b9', 
                              markeredgecolor='white', markeredgewidth=2,
                              label=f'Año {datos_actuales["FECHA"].dt.year.iloc[0]}',
                              zorder=3)
        
        # Rellenar área bajo la curva del año actual
        ax.fill_between(datos_actuales['FECHA'], datos_actuales['Litros'], 
                       alpha=0.25, color='#3498db', zorder=1)
        
        # Agregar datos para tooltips
        plots_data.append({
            'plot': line_actual,
            'x_data': datos_actuales['FECHA'].tolist(),
            'y_data': datos_actuales['Litros'].tolist(),
            'label': f'Año {datos_actuales["FECHA"].dt.year.iloc[0]}'
        })
        
        # Gráfico del año anterior si existe
        if datos_anteriores is not None and not datos_anteriores.empty:
            line_anterior, = ax.plot(datos_anteriores['FECHA'], datos_anteriores['Litros'], 
                                   marker='s', linewidth=3, markersize=8, 
                                   color='#e74c3c', markerfacecolor='#c0392b', 
                                   markeredgecolor='white', markeredgewidth=2,
                                   label=f'Año {datos_anteriores["FECHA"].dt.year.iloc[0]-1}',
                                   zorder=2, linestyle='--', alpha=0.8)
            
            ax.fill_between(datos_anteriores['FECHA'], datos_anteriores['Litros'], 
                           alpha=0.15, color='#e74c3c', zorder=0)
            
            # Agregar datos para tooltips
            plots_data.append({
                'plot': line_anterior,
                'x_data': datos_anteriores['FECHA'].tolist(),
                'y_data': datos_anteriores['Litros'].tolist(),
                'label': f'Año {datos_anteriores["FECHA"].dt.year.iloc[0]-1}'
            })
        
        # Mejorar apariencia del gráfico
        ax.set_title('Comparación Anual - Litros Vendidos por Día', 
                    fontsize=15, fontweight='bold', color='#2c3e50', pad=20)
        ax.set_xlabel('Fecha', fontweight='bold', fontsize=11, color='#34495e')
        ax.set_ylabel('Litros', fontweight='bold', fontsize=11, color='#34495e')
        ax.tick_params(axis='x', rotation=45, labelsize=9)
        ax.tick_params(axis='y', labelsize=10)
        ax.grid(True, alpha=0.4, linestyle='--', linewidth=0.8, color='#bdc3c7')
        ax.set_facecolor('#fafafa')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')
        
        # Formatear números en eje Y
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=10)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_edgecolor('#bdc3c7')
        legend.get_frame().set_alpha(0.95)
        self.figure.tight_layout()
        
        # Configurar tooltips interactivos
        if plots_data:
            self.canvas.setup_hover_annotations(plots_data)
        
        self.canvas.draw()

    def generar_histograma_mensual_comparativo(self, ax):
        """Generar gráfico de líneas mensual comparativo con tooltips"""
        # Datos del año actual
        df_con_litros = self.calcular_litros_por_fecha()
        df_con_litros = df_con_litros.copy()
        df_con_litros.loc[:, 'Mes'] = df_con_litros['FECHA'].dt.to_period('M')
        datos_actuales = df_con_litros.groupby('Mes')['Litros'].sum().reset_index()
        datos_actuales = datos_actuales.sort_values('Mes')
        
        # Datos del año anterior
        datos_anteriores = None
        if self.df_ventas_completo is not None:
            datos_anteriores = self.obtener_datos_anio_anterior_mensual(datos_actuales)
        
        # Convertir períodos a strings para el eje X
        meses_str = [str(mes) for mes in datos_actuales['Mes']]
        meses_labels = [calendar.month_name[int(mes.split('-')[1])][:3] + ' ' + mes.split('-')[0] for mes in meses_str]
        litros_actuales = datos_actuales['Litros'].values
        
        # Crear posiciones numéricas para el eje X
        x_pos = range(len(meses_str))
        
        # Preparar datos para tooltips
        plots_data = []
        
        # Gráfico de líneas para año actual con mejor estética
        line_actual, = ax.plot(x_pos, litros_actuales, marker='o', linewidth=3, markersize=10, 
                              color='#3498db', markerfacecolor='#2980b9', 
                              markeredgecolor='white', markeredgewidth=2,
                              label='Año Actual', zorder=3)
        
        # Rellenar área bajo la curva del año actual con gradiente visual
        ax.fill_between(x_pos, litros_actuales, alpha=0.3, color='#3498db', zorder=1)
        
        # Agregar datos para tooltips
        plots_data.append({
            'plot': line_actual,
            'x_data': x_pos,
            'y_data': litros_actuales.tolist(),
            'label': 'Año Actual',
            'x_labels': meses_labels
        })
        
        # Gráfico del año anterior si existe
        if datos_anteriores is not None and not datos_anteriores.empty:
            litros_anteriores = datos_anteriores['Litros'].values
            line_anterior, = ax.plot(x_pos, litros_anteriores, marker='s', linewidth=3, markersize=10, 
                                   color='#e74c3c', markerfacecolor='#c0392b', 
                                   markeredgecolor='white', markeredgewidth=2,
                                   label='Año Anterior', zorder=2, linestyle='--', alpha=0.8)
            
            ax.fill_between(x_pos, litros_anteriores, alpha=0.2, color='#e74c3c', zorder=0)
            
            # Agregar datos para tooltips
            plots_data.append({
                'plot': line_anterior,
                'x_data': x_pos,
                'y_data': litros_anteriores.tolist(),
                'label': 'Año Anterior',
                'x_labels': meses_labels
            })
        
        # Configurar etiquetas del eje X
        ax.set_xticks(x_pos)
        ax.set_xticklabels(meses_labels, rotation=45, ha='right')
        
        # Mejorar apariencia del gráfico
        ax.set_title('Comparación Anual - Litros Vendidos por Mes', 
                    fontsize=15, fontweight='bold', color='#2c3e50', pad=20)
        ax.set_xlabel('Mes', fontweight='bold', fontsize=11, color='#34495e')
        ax.set_ylabel('Litros', fontweight='bold', fontsize=11, color='#34495e')
        ax.tick_params(axis='x', labelsize=9)
        ax.tick_params(axis='y', labelsize=10)
        ax.grid(True, alpha=0.4, linestyle='--', linewidth=0.8, color='#bdc3c7')
        ax.set_facecolor('#fafafa')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')
        
        # Formatear números en eje Y
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=10)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_edgecolor('#bdc3c7')
        legend.get_frame().set_alpha(0.95)
        self.figure.tight_layout()
        
        # Configurar tooltips interactivos
        if plots_data:
            self.canvas.setup_hover_annotations(plots_data)
        
        self.canvas.draw()

    def obtener_datos_anio_anterior_diario(self, datos_actuales):
        """Obtener datos del año anterior para comparación diaria"""
        if self.df_ventas_completo is None:
            return None
            
        try:
            # Calcular el rango de fechas del año anterior
            fecha_min_actual = datos_actuales['FECHA'].min()
            fecha_max_actual = datos_actuales['FECHA'].max()
            
            fecha_min_anterior = fecha_min_actual - pd.DateOffset(years=1)
            fecha_max_anterior = fecha_max_actual - pd.DateOffset(years=1)
            
            # Filtrar datos del año anterior
            df_ventas_anterior = self.df_ventas_completo.copy()
            df_ventas_anterior.loc[:, 'FECHA'] = pd.to_datetime(df_ventas_anterior['FECHA'])
            
            datos_periodo_anterior = df_ventas_anterior[
                (df_ventas_anterior['FECHA'] >= fecha_min_anterior) &
                (df_ventas_anterior['FECHA'] <= fecha_max_anterior) &
                ((df_ventas_anterior['TC'] == 'FC') | (df_ventas_anterior['TC'] == 'NC') | (df_ventas_anterior['TC'] == 'ND') | (df_ventas_anterior['TC'] == 'FE') | (df_ventas_anterior['TC'] == 'CR'))
            ][["FECHA", "TC", "MODELO", "U_VENDIDAS"]]
            
            if datos_periodo_anterior.empty:
                return None
                
            # Calcular litros para el año anterior
            df_anterior_con_litros = self.calcular_litros_por_fecha_df(datos_periodo_anterior)
            datos_anteriores = df_anterior_con_litros.groupby('FECHA')['Litros'].sum().reset_index()
            datos_anteriores = datos_anteriores.sort_values('FECHA')
            
            # Ajustar fechas para mostrar en el mismo eje temporal
            datos_anteriores.loc[:, 'FECHA'] = datos_anteriores['FECHA'] + pd.DateOffset(years=1)
            
            return datos_anteriores
            
        except Exception as e:
            print(f"Error al obtener datos del año anterior: {e}")
            return None

    def obtener_datos_anio_anterior_mensual(self, datos_actuales):
        """Obtener datos del año anterior para comparación mensual"""
        if self.df_ventas_completo is None:
            return None
            
        try:
            # Calcular los períodos del año anterior
            periodos_actuales = datos_actuales['Mes'].tolist()
            periodos_anteriores = [periodo - 12 for periodo in periodos_actuales]
            
            # Filtrar datos del año anterior
            df_ventas_anterior = self.df_ventas_completo.copy()
            df_ventas_anterior.loc[:, 'FECHA'] = pd.to_datetime(df_ventas_anterior['FECHA'])
            df_ventas_anterior.loc[:, 'Mes'] = df_ventas_anterior['FECHA'].dt.to_period('M')
            
            datos_periodo_anterior = df_ventas_anterior[
                (df_ventas_anterior['Mes'].isin(periodos_anteriores)) &
                ((df_ventas_anterior['TC'] == 'FC') | (df_ventas_anterior['TC'] == 'NC') | (df_ventas_anterior['TC'] == 'ND') | (df_ventas_anterior['TC'] == 'FE') | (df_ventas_anterior['TC'] == 'CR'))
            ][["FECHA", "TC", "MODELO", "U_VENDIDAS"]]
            
            if datos_periodo_anterior.empty:
                return None
                
            # Calcular litros para el año anterior
            df_anterior_con_litros = self.calcular_litros_por_fecha_df(datos_periodo_anterior)
            df_anterior_con_litros.loc[:, 'Mes'] = df_anterior_con_litros['FECHA'].dt.to_period('M')
            datos_anteriores = df_anterior_con_litros.groupby('Mes')['Litros'].sum().reset_index()
            datos_anteriores = datos_anteriores.sort_values('Mes')
            
            return datos_anteriores
            
        except Exception as e:
            print(f"Error al obtener datos del año anterior: {e}")
            return None

    def calcular_litros_por_fecha_df(self, df_ventas):
        """Calcular litros por fecha para un DataFrame específico"""
        df_resultado = df_ventas.copy()
        
        # Agregar información de litros usando los mismos datos de productos
        litros_por_producto = {}
        for _, row in self.content_table.iterrows():
            codigo = row['Codigo de Producto']
            litros_por_unidad = row['Litros'] / row['Unidades Vendidas'] if row['Unidades Vendidas'] > 0 else 0
            litros_por_producto[codigo] = litros_por_unidad
        
        # Usar .loc para evitar warning de pandas
        df_resultado.loc[:, 'Litros'] = df_resultado.apply(
            lambda row: row['U_VENDIDAS'] * litros_por_producto.get(row['MODELO'], 0), axis=1
        )
        
        return df_resultado

    def calcular_litros_por_fecha(self):
        """Calcular litros por fecha combinando con datos de productos"""
        return self.calcular_litros_por_fecha_df(self.periodoVentas)