import calendar
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
import os
import pandas as pd
import numpy as np
import sys

import PyQt5.QtWidgets as widget
import PyQt5.QtCore as Qt
import PyQt5.QtCore as core
import PyQt5.QtGui as gui

def resource_path(relative_path: str) -> str:
    """Resuelve rutas de recursos tanto en desarrollo como en ejecutable PyInstaller."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

import src.controllers.others as others
import src.controllers.ProgressBar as ProgressBar
from src.controllers.others import buscaArtic
from src.controllers import config
from src.controllers import dbf_io

from src.Views.Echeq.EcheqDBF import EcheqWindow
from src.Views.Litros.LitrosDBF import ReportLts
from dbfread import DBF
from datetime import datetime
from src.controllers.FechaDBF import Fecha
from src.controllers.RangeFechas import DateRangeDialog
from src.controllers.rangeMY import DateYearRangeDialog

from src.controllers.MesAno import MesAnioDialog

from src.Views.Pedidos.programarPedido import VentanaProgramarPedido
from src.Views.Beneficio.margenBeneficio import margenBeneficio


#-------------------------------------------------
#__author__ = "Juan Ignacio Peña Seva"
#__version__ = "1.5.10"
#__copyright__ = "Copyright (c) 2024, Juan ignacio Pena. Todos los derechos reservados."
#__identifier__ = "ID-APP-JP00001"
#-------------------------------------------------

class MainWindow(widget.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setupUI()
        self.setStyleSheet(self.getStyleSheet())
        self.load_data()  # Tu función existente
    
    def setupUI(self):
        """Configurar la interfaz de usuario moderna"""
        self.setWindowTitle("📊 Informes Mana S.R.L - Sistema de Gestión")
        self.setWindowIcon(gui.QIcon(resource_path("src/Distribuidora/shell.ico")))
        
        # Configurar ventana responsiva
        self.setMinimumSize(600, 500)
        self.setGeometry(200, 150, 800, 650)
        
        # Widget central
        central_widget = widget.QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = widget.QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 20, 30, 20)
        
        # Crear secciones
        self.crear_header(main_layout)
        self.crear_botones_principales(main_layout)
        self.crear_barra_carga(main_layout)

        # Deshabilitar botones hasta que termine la carga
        for boton in self.botones_principales:
            boton.setEnabled(False)
    
    def crear_header(self, main_layout):
        """Crear sección del header con logo y título"""
        header_frame = widget.QFrame()
        header_frame.setObjectName("header_frame")
        header_frame.setFixedHeight(155)

        header_layout = widget.QVBoxLayout(header_frame)
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(10, 8, 10, 8)

        # Logo
        self.etiqueta_imagen = widget.QLabel()
        pixmap = gui.QPixmap(resource_path("src/Distribuidora/Logo Mana SRL.jpg"))

        if not pixmap.isNull():
            # Redimensionar logo manteniendo proporción
            scaled_pixmap = pixmap.scaled(105, 63, core.Qt.KeepAspectRatio, core.Qt.SmoothTransformation)
            self.etiqueta_imagen.setPixmap(scaled_pixmap)
        else:
            # Fallback si no encuentra la imagen
            self.etiqueta_imagen.setText("MANA S.R.L")
            self.etiqueta_imagen.setObjectName("logo_text")
            
        self.etiqueta_imagen.setAlignment(core.Qt.AlignCenter)
        header_layout.addWidget(self.etiqueta_imagen)
        
        # Título y subtítulo
        titulo = widget.QLabel("Sistema de Gestión e Informes")
        titulo.setObjectName("titulo_principal")
        titulo.setAlignment(core.Qt.AlignCenter)
        header_layout.addWidget(titulo)
        
        subtitulo = widget.QLabel("Seleccione el módulo que desea utilizar")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setAlignment(core.Qt.AlignCenter)
        header_layout.addWidget(subtitulo)
        
        main_layout.addWidget(header_frame)
    
    def crear_botones_principales(self, main_layout):
        """Crear grid de botones principales"""
        botones_frame = widget.QFrame()
        botones_frame.setObjectName("botones_frame")
        
        # Grid layout 3x3 responsivo
        grid_layout = widget.QGridLayout(botones_frame)
        grid_layout.setSpacing(15)
        grid_layout.setContentsMargins(15, 15, 15, 15)
        
        # Definir botones con sus propiedades
        botones_config = [
            {
                'name': 'botonThalamus',
                'text': 'Thalamus',
                'icon': 'src/Distribuidora/informe.png',
                'function': self.informeThalamus2,
                'description': 'Generar informes para Thalamus',
                'color': '#e3f2fd',
                'pos': (0, 0)
            },
            {
                'name': 'botonLitros', 
                'text': 'Informe Litros',
                'icon': 'src/Distribuidora/gotas.png',
                'function': self.reporteLitros,
                'description': 'Reportes de volumen en litros',
                'color': '#f3e5f5',
                'pos': (0, 1)
            },
            {
                'name': 'botonSellIn',
                'text': 'Sell In',
                'icon': 'src/Distribuidora/compras.png', 
                'function': self.sellIn,
                'description': 'Gestión de ventas entrantes',
                'color': '#e8f5e8',
                'pos': (0, 2)
            },
            {
                'name': 'botonMensual',
                'text': 'Ventas Mensuales',
                'icon': 'src/Distribuidora/calendario.png',
                'function': self.reporteMensual,
                'description': 'Informes mensuales de ventas',
                'color': '#fff3e0',
                'pos': (1, 0)
            },
            {
                'name': 'botonSalib',
                'text': 'Informe IIBB', 
                'icon': 'src/Distribuidora/IIBB.png',
                'function': self.IIBB,
                'description': 'Ingresos Brutos',
                'color': '#fce4ec',
                'pos': (1, 1)
            },
            {
                'name': 'botonEcheq',
                'text': 'E-Cheques',
                'icon': 'src/Distribuidora/echeq.png',
                'function': self.manejadorEcheq,
                'description': 'Gestión de cheques electrónicos',
                'color': '#e0f2f1',
                'pos': (1, 2)
            },
            {
                'name': 'botonPedidos',
                'text': 'Pedidos',
                'icon': 'src/Distribuidora/pedidos.png',
                'function': self.pedidosCaller,
                'description': 'Gestión de pedidos',
                'color': '#f1f8e9',
                'pos': (2, 0)
            },
            {
                'name': 'botonMargen',
                'text': 'Margen Beneficio',
                'icon': 'src/Distribuidora/margen.png',
                'function': self.margenesBeneficio,
                'description': 'Cálculo de márgenes',
                'color': '#fff8e1',
                'pos': (2, 1)
            },
            {
                'name': 'botonActualizacionPrecios',
                'text': 'Actualizar Precios',
                'icon': 'src/Distribuidora/precio.png',
                'function': self.actualizar_precios_mana_horeb,
                'description': 'Actualizar precios de productos de Lista Mana',
                'color': '#e3f2fd',
                'pos': (2, 2)
            }
        ]
        
        # Crear botones
        self.botones_principales = []
        for config in botones_config:
            boton = self.crear_boton_moderno(config)
            setattr(self, config['name'], boton)  # Asignar como atributo de la clase
            self.botones_principales.append(boton)
            grid_layout.addWidget(boton, config['pos'][0], config['pos'][1])
            
        # Agregar espacio vacío en la última posición si es necesario
        spacer = widget.QWidget()
        spacer.setMaximumSize(10, 10)
        grid_layout.addWidget(spacer, 2, 2)
        
        # Hacer columnas responsivas
        for i in range(3):
            grid_layout.setColumnStretch(i, 1)
            grid_layout.setRowStretch(i, 1)
            
        main_layout.addWidget(botones_frame)
    
    def crear_boton_moderno(self, config):
        """Crear un botón moderno con estilo personalizado"""
        boton = widget.QPushButton()
        boton.setObjectName("boton_moderno")
        
        # Layout interno del botón
        layout_boton = widget.QVBoxLayout(boton)
        layout_boton.setSpacing(8)
        layout_boton.setContentsMargins(15, 15, 15, 15)
        
        # Icono
        if config['icon']:
            icon_label = widget.QLabel()
            pixmap = gui.QPixmap(resource_path(config['icon']))
            if not pixmap.isNull():
                scaled_icon = pixmap.scaled(32, 32, core.Qt.KeepAspectRatio, core.Qt.SmoothTransformation)
                icon_label.setPixmap(scaled_icon)
            else:
                icon_label.setText("📊")  # Fallback emoji
                icon_label.setStyleSheet("font-size: 24px;")
            icon_label.setAlignment(core.Qt.AlignCenter)
            layout_boton.addWidget(icon_label)
        
        # Título del botón
        titulo_label = widget.QLabel(config['text'])
        titulo_label.setObjectName("boton_titulo")
        titulo_label.setAlignment(core.Qt.AlignCenter)
        titulo_label.setWordWrap(True)
        layout_boton.addWidget(titulo_label)
        
        # Descripción
        desc_label = widget.QLabel(config['description'])
        desc_label.setObjectName("boton_descripcion")
        desc_label.setAlignment(core.Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout_boton.addWidget(desc_label)
        
        # Configurar propiedades
        boton.setMinimumSize(180, 120)
        boton.setMaximumSize(250, 150)
        boton.setSizePolicy(widget.QSizePolicy.Expanding, widget.QSizePolicy.Expanding)
        boton.setFocusPolicy(core.Qt.StrongFocus)
        boton.clicked.connect(config['function'])
        
        # Aplicar color de fondo personalizado
        boton.setProperty("background_color", config['color'])
        
        return boton
    
    def crear_barra_carga(self, main_layout):
        """Panel de carga integrado en la ventana principal"""
        self.frame_carga = widget.QFrame()
        self.frame_carga.setObjectName("frame_carga")

        carga_layout = widget.QVBoxLayout(self.frame_carga)
        carga_layout.setSpacing(6)
        carga_layout.setContentsMargins(20, 10, 20, 10)

        self.label_carga = widget.QLabel("Cargando base de datos, por favor espere...")
        self.label_carga.setAlignment(core.Qt.AlignCenter)
        self.label_carga.setObjectName("label_carga")
        carga_layout.addWidget(self.label_carga)

        self.barra_carga = widget.QProgressBar()
        self.barra_carga.setMinimum(0)
        self.barra_carga.setMaximum(0)  # Modo indeterminado
        self.barra_carga.setTextVisible(False)
        self.barra_carga.setFixedHeight(14)
        carga_layout.addWidget(self.barra_carga)

        main_layout.addWidget(self.frame_carga)

    def resizeEvent(self, event):
        """Manejar redimensionamiento de ventana"""
        super().resizeEvent(event)
        
        # Ajustar logo según tamaño de ventana
        if hasattr(self, 'etiqueta_imagen'):
            size = min(self.width() // 5, 140)
            pixmap = gui.QPixmap(resource_path("src/Distribuidora/Logo Mana SRL.jpg"))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(size, size // 2, core.Qt.KeepAspectRatio, core.Qt.SmoothTransformation)
                self.etiqueta_imagen.setPixmap(scaled_pixmap)
    
    def getStyleSheet(self):
        """Retorna el CSS para la aplicación"""
        return """
        QMainWindow {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #f8f9fa, stop: 1 #e9ecef);
        }
        
        QFrame#header_frame {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: 2px solid #dee2e6;
            border-radius: 15px;
            margin: 5px;
        }
        
        QFrame#botones_frame {
            background-color: rgba(255, 255, 255, 0.9);
            border: 1px solid #dee2e6;
            border-radius: 10px;
            margin: 5px;
        }
        
        QFrame#footer_frame {
            background-color: #f8f9fa;
            border-top: 2px solid #dee2e6;
            border-radius: 5px;
        }
        
        QLabel#logo_text {
            font-size: 28px;
            font-weight: bold;
            color: #495057;
            background-color: transparent;
        }
        
        QLabel#titulo_principal {
            font-size: 16px;
            font-weight: bold;
            color: #343a40;
            background-color: transparent;
            margin: 2px 0;
        }

        QLabel#subtitulo {
            font-size: 11px;
            color: #6c757d;
            background-color: transparent;
            font-style: italic;
        }
        
        QPushButton#boton_moderno {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: 2px solid #dee2e6;
            border-radius: 12px;
            padding: 10px;
            margin: 5px;
            text-align: center;
        }
        
        QPushButton#boton_moderno:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e3f2fd, stop: 1 #bbdefb);
            border-color: #2196f3;
        }
        
        QPushButton#boton_moderno:pressed {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #bbdefb, stop: 1 #90caf9);
            border-color: #1976d2;
        }
        
        QPushButton#boton_moderno:focus {
            border: 3px solid #2196f3;
            outline: none;
        }
        
        QLabel#boton_titulo {
            font-size: 14px;
            font-weight: bold;
            color: #495057;
            background-color: transparent;
        }
        
        QLabel#boton_descripcion {
            font-size: 11px;
            color: #6c757d;
            background-color: transparent;
            line-height: 1.2;
        }
        
        QLabel#version_label, QLabel#estado_label {
            font-size: 12px;
            color: #6c757d;
            background-color: transparent;
            padding: 5px;
        }

        QFrame#frame_carga {
            background-color: rgba(255, 255, 255, 0.95);
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin: 5px;
        }

        QLabel#label_carga {
            font-size: 13px;
            color: #495057;
            background-color: transparent;
            font-style: italic;
        }

        QProgressBar {
            border: 1px solid #ced4da;
            border-radius: 6px;
            background-color: #e9ecef;
        }

        QProgressBar::chunk {
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                                        stop: 0 #4dabf7, stop: 1 #228be6);
            border-radius: 6px;
        }

        """

    def load_data(self):
        # Iniciar el hilo de carga (la barra ya está visible en la ventana principal)
        self.load_thread = ProgressBar.LoadDataThread()
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.start()

    def on_data_loaded(self, df):
        self.df_ventas = df

        # Ocultar el panel de carga
        self.frame_carga.setVisible(False)

        # Habilitar todos los botones
        for boton in self.botones_principales:
            boton.setEnabled(True)

        self.botonThalamus.setFocus()

    def margenesBeneficio(self):
        try:
            dateRange = DateRangeDialog(self)
            if dateRange.exec_() == widget.QDialog.Accepted:
                # Convertir FECHA a Timestamp para comparación compatible con pd.Timestamp
                fechas = pd.to_datetime(self.df_ventas['FECHA'])
                fecha_desde = dateRange.fecha_desde_procesada
                fecha_hasta = dateRange.fecha_hasta_procesada

                # Filtrado adicional por vendedor (si no es "TODOS")
                if dateRange.vendedor_procesado:
                    df_filtrado = self.df_ventas[
                        (fechas >= fecha_desde) &
                        (fechas <= fecha_hasta) &
                        (self.df_ventas['MODELO'].astype(str).str.startswith('L')) &
                        (self.df_ventas['VENDNUMERO'] == dateRange.vendedor_procesado) &
                        ((self.df_ventas['TC'] == 'FC') | (self.df_ventas['TC'] == 'NC') |
                         (self.df_ventas['TC'] == 'ND') | (self.df_ventas['TC'] == 'FE'))
                    ]
                else:
                    df_filtrado = self.df_ventas[
                        (fechas >= fecha_desde) &
                        (fechas <= fecha_hasta) &
                        (self.df_ventas['MODELO'].astype(str).str.startswith('L')) &
                        ((self.df_ventas['TC'] == 'FC') | (self.df_ventas['TC'] == 'NC') |
                         (self.df_ventas['TC'] == 'FE') | (self.df_ventas['TC'] == 'ND'))
                    ]

                margenBeneficioWindow = margenBeneficio(df_periodo_ventas=df_filtrado)
                margenBeneficioWindow.show()
        except Exception as e:
            widget.QMessageBox.warning(self, "Error", str(e))
    
    def reporteMensual(self):
        try:
            direc = self.seleccionar_carpeta()
            
            # Crear las filas iniciales
            fila_distribuidor = pd.DataFrame([["DISTRIBUIDOR", None, None, None,None]], columns=["Fecha","Comprobante", "Codigo de producto", "Familia", "Litros"])
            columnas = ["Dia / Periodo","Comprobante", "Codigo de producto", "Familia", "Litros"]
            fila_cabecera = pd.DataFrame([columnas], columns=columnas)
            df_mensual = pd.concat([fila_distribuidor, fila_cabecera], ignore_index=True)

            # Cargar archivo de artículos
            df_art = pd.read_excel(config.EXCEL_LITROS_PATH, sheet_name='GENERAL')
            print(df_art.columns)
            
            if direc:
                for archivo in os.listdir(direc):
                    if archivo.startswith('Template'):
                        daily_report = pd.read_excel(f"{direc}/{archivo}")
                        print(f"Procesando archivo: {direc}/{archivo}")

                        filas_nuevas = []
                        for index, venta in daily_report.iterrows():
                            art_filtrado = df_art[(df_art["articulo"] == venta["Code"]) | (df_art["Artiprov"] == venta["Code"])]

                            if not art_filtrado.empty:
                                art = art_filtrado.iloc[0]
                                filas_nuevas.append({
                                    "Fecha": pd.to_datetime(venta['Sale Date']).strftime('%Y/%m/%d'),
                                    "Comprobante": venta['Transaction ID'],
                                    "Codigo de producto": venta['Code'],
                                    "Familia": self.get_familia(art),
                                    "Litros": self.get_litros(art, venta['Quantity'])
                                })
                            else:
                                mensaje = (f"El código {venta['Code']} correspondiente a {venta['Sale Date']} no se encontró en LITROS SHELL.")
                                msg_box = widget.QMessageBox()
                                msg_box.setIcon(widget.QMessageBox.Information)
                                msg_box.setWindowTitle("Archivo Guardado")
                                msg_box.setText(mensaje)
                                msg_box.setStandardButtons(widget.QMessageBox.Ok)
                                msg_box.exec_()

                        if filas_nuevas:
                            df_mensual = pd.concat([df_mensual, pd.DataFrame(filas_nuevas)], ignore_index=True)
                df_mensual.sort_values(by='Dia / Periodo', ascending=True)
                # Guardar el DataFrame formateado en un archivo Excel
                ruta_salida = widget.QFileDialog.getSaveFileName(
                    self, "Guardar Informe Mensual COLOQUE MES EN EL NOMBRE DEL ARCHIVO", "Anexo_6_MES.xlsx", "Archivos Excel (*.xlsx)"
                )[0]
                
                if ruta_salida:
                    others.generar_archivo_excel(df_mensual, ruta_salida)
            else:
                # Mostrar advertencia si no se seleccionó carpeta
                msg_box = widget.QMessageBox()
                msg_box.setIcon(widget.QMessageBox.Warning)
                msg_box.setWindowTitle("Selección Cancelada")
                msg_box.setText("No se seleccionó ninguna carpeta.")
                msg_box.setStandardButtons(widget.QMessageBox.Ok)
                msg_box.exec_()
        except Exception as e:
            # Mostrar mensaje de error
            msg_box = widget.QMessageBox()
            msg_box.setIcon(widget.QMessageBox.Critical)
            msg_box.setWindowTitle("Error al Guardar")
            msg_box.setText(f"Se produjo un Error:\n{e}")
            msg_box.setStandardButtons(widget.QMessageBox.Ok)
            msg_box.exec_()
    
    def get_familia(self,art):
        familias = ['Helix','Rimula','Gadus','Omala','Tellus','Advance','Corena','Coolant','Diala','Raizen','Spirax','Refrigeration','Tonna','Turbo']
        fam = 'Otro'
        if art["desc"].split()[0] in familias:
            fam = art["desc"].split()[0]
        return fam
    
    def get_litros(self,art,cantidad):
        return art['codmedida']*cantidad
    
    def seleccionar_carpeta(self):
        ruta_archivo = widget.QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Informe Mensual")
        if ruta_archivo:  # Si el usuario seleccionó un archivo
            return ruta_archivo
        else:
            return None
    
    def informeThalamus2(self):
        """
        Filtra los datos de ventas y los agrega al archivo Excel existente.
        """
        dialogo = Fecha(self)
        if dialogo.exec_() == widget.QDialog.Accepted:
            fecha_seleccionada = dialogo.input_fecha.text()
            fecha_ingresada = datetime.strptime(fecha_seleccionada, "%d/%m/%Y").date()

            # Filtrar el DataFrame con las condiciones dadas
            df_filtrado = self.df_ventas[
                (pd.to_datetime(self.df_ventas["FECHA"]).dt.date == fecha_ingresada) &
                (self.df_ventas["MODELO"].str.match(r'^L\d')) &
                (self.df_ventas["CUENTA"].notna()) &
                ((self.df_ventas["TC"] == "FC") | (self.df_ventas["TC"] == "NC") | (self.df_ventas["TC"] == "FE") | (self.df_ventas["TC"] == "CR"))
            ]
            SKUArticDS = buscaArtic(df_filtrado)
            
            # Obtener los códigos correctos (reemplazados por ARTIPROV cuando corresponda)
            codigos_correctos = self.getCodigosCorrectos(df_filtrado['MODELO'], SKUArticDS)
            
            # Crear un DataFrame con las filas filtradas
            nuevos_datos = pd.DataFrame({
                'Systemid': df_filtrado['CUENTA'].astype(int),
                'Sale Date': pd.to_datetime(df_filtrado['FECHA']).dt.strftime('%Y/%m/%d'),
                'Transaction ID': df_filtrado.apply(
                    lambda row: "{} {} {} {}".format(
                        row['TC'], row['LETRA'], row['NROEST'], str(row['NC']).zfill(8)
                    ),
                    axis=1
                ),
                'Code': codigos_correctos,
                'Quantity': df_filtrado['U_VENDIDAS'].astype(int),
                'Description 1': np.where(
                    df_filtrado['TC'] == 'FC', 'F',
                    np.where(df_filtrado['TC'] == 'NC', 'NC', '')),
                'Amount': round(self.addPrice(df_filtrado['MODELO'], SKUArticDS).astype(float),2),
            })
            self.verificaCliente(nuevos_datos['Systemid'])

            # El resto del código permanece igual...
            # Ruta del archivo existente
            ruta_base = os.path.join(config.EXCEL_THALAMUS_PATH, "Template_VENTA MANA.xlsx")
            dia_mes = fecha_ingresada.strftime('%d-%m')
            nombre_archivo = f"Template_VENTA MANA {dia_mes}.xlsx"
            ruta_final = os.path.join(config.EXCEL_THALAMUS_PATH, nombre_archivo)

            # Verificar si el archivo existe
            if not os.path.exists(ruta_base):
                widget.QMessageBox.warning(
                    self, "Error", f"No se encontró el archivo base en la ruta: {ruta_base}"
                )
                return

            # Abrir el archivo con openpyxl
            try:
                workbook = openpyxl.load_workbook(ruta_base)
                hoja = workbook.active
                hoja.delete_rows(2, hoja.max_row)
                # Agregar los nuevos datos al final de la hoja
                for fila in dataframe_to_rows(nuevos_datos, index=False, header=False):
                    hoja.append(fila)
                # Guardar el archivo actualizado
                formato_fecha = "yyyy/mm/dd;@"
                for fila in hoja.iter_rows(min_row=2, min_col=2, max_col=2):
                    for celda in fila:
                        celda.number_format = formato_fecha

                workbook.save(ruta_final)
                widget.QMessageBox.information(
                    self, "Éxito", f"Los datos se han añadido correctamente al archivo:\n{ruta_final}"
                )
            except PermissionError:
                widget.QMessageBox.critical(
                    self, "Error", f"No se pudo guardar el archivo. Asegúrate de que no esté abierto:\n{ruta_base}"
                )
            except Exception as e:
                widget.QMessageBox.critical(self, "Error inesperado", str(e))
    
    def getCodigosCorrectos(self, modelos_series, SKUArticDS):
        """
        Reemplaza los códigos de modelo con ARTIPROV cuando está disponible
        """
        codigos_resultado = []
        
        for modelo in modelos_series:
            # Buscar si existe ARTIPROV para este modelo
            matches = SKUArticDS[SKUArticDS['CODART'] == modelo]
            
            if not matches.empty:
                artiprov = matches['ARTIPROV'].iloc[0]
                # Si ARTIPROV no está vacío, usar ese código, sino usar el modelo original
                codigo_final = artiprov if (artiprov is not None and artiprov != '' and pd.notna(artiprov)) else modelo
            else:
                codigo_final = modelo
            
            codigos_resultado.append(codigo_final)
        
        return pd.Series(codigos_resultado, index=modelos_series.index)
    
    def addPrice(self, modelos_series, SKUArticDS):
        try:
            # Cargar archivo de precios
            self.precios = pd.read_excel(
                os.path.join(config.EXCEL_PRECIOS_PATH, 'Lista de precios Mana.xlsm'),
                sheet_name='Lista De Precios',
                header=2
            )
            
            # Seleccionar las columnas necesarias
            self.precios = self.precios[["SKU", 'Producto', "Precio Por envase", "Informe  s/IVA"]]
            
            # Limpiar datos: eliminar espacios y convertir a string
            self.precios['SKU'] = self.precios['SKU'].astype(str).str.strip()
            
            # Crear un diccionario para búsqueda rápida de precios
            precio_dict = dict(zip(self.precios['SKU'], self.precios['Informe  s/IVA']))
            
            # Crear lista de precios resultado manteniendo el orden original
            precios_resultado = []
            
            for modelo in modelos_series:
                # Buscar si existe ARTIPROV para este modelo
                matches = SKUArticDS[SKUArticDS['CODART'] == modelo]
                
                if not matches.empty:
                    artiprov = matches['ARTIPROV'].iloc[0]
                    # Si ARTIPROV no está vacío, usar ese código, sino usar el modelo original
                    codigo_busqueda = artiprov if (artiprov is not None and artiprov != '' and pd.notna(artiprov)) else modelo
                else:
                    codigo_busqueda = modelo
                
                # Buscar precio usando el código final
                precio = precio_dict.get(codigo_busqueda, 0)
                precios_resultado.append(precio)
            
            # Convertir a Series manteniendo el índice original
            return pd.Series(precios_resultado, index=modelos_series.index)
            
        except FileNotFoundError:
            return pd.Series([0] * len(modelos_series), index=modelos_series.index)
            
        except Exception as e:
            print(f"❌ Error al procesar precios: {str(e)}")
            return pd.Series([0] * len(modelos_series), index=modelos_series.index)
    
    def verificaCliente(self,numero_clientes):
        documento = pd.read_excel(os.path.join(config.EXCEL_THALAMUS_PATH, "Template_CLIENTE MANA.xlsx"))
        listaContraste = documento["Systemid"]
        bdClient = pd.DataFrame(iter(DBF(os.path.join(config.DBF_BASE_PATH, 'ctaclien.DBF'), encoding=config.DBF_ENCODING)))
        cod_vendedor = {
            "1": "ROMULO SANCHEZ",
            "3": "MIGUEL ORTUnO",
            "4": "JOSE BANCO",
            "5": "DIEGO CALDERON",
            "6": "MATIAS BARATA",
            "9": "MARTIN MOYA"
        }
        codigos_prov ={
        "LA RIOJA": "3580",
        "BUENOS AIRES": "3579",
        "CAPITAL FEDERAL": "3578",
        "CATAMARCA": "3577",
        "CHACO": "3576",
        "CHUBUT": "3575",
        "CORDOBA": "3574",
        "CORRIENTES": "3573",
        "ENTRE RIOS": "3572",
        "FORMOSA": "3571",
        "JUJUY": "3570",
        "LA PAMPA": "3569",
        "MENDOZA": "3568",
        "MISIONES": "3567",
        "NEUQUEN": "3566",
        "RIO NEGRO": "3565",
        "SALTA": "3564",
        "SAN JUAN": "3563",
        "SAN LUIS": "3562",
        "SANTA CRUZ": "3561",
        "SANTA FE": "3560",
        "SANTIAGO DEL ESTERO": "3559",
        "TIERRA DEL FUEGO": "3558",
        "TUCUMAN": "3557"
    }
        # Convertir listas a conjuntos para mejor rendimiento
        clientes_recibidos_set = set(numero_clientes)
        lista_clientes_set = set(listaContraste)
        
        # Identificar clientes no encontrados
        no_encontrados = clientes_recibidos_set - lista_clientes_set
        
        try:
            if no_encontrados:
                filas_nuevas = []
                for id in no_encontrados:
                    cliente = bdClient[bdClient['CNUMERO'] == id]
                    if not cliente.empty:
                        filas_nuevas.append({
                            "Systemid": id,
                            "FiscalID": int(cliente["CUIT"].values[0].replace("-","")) if cliente["CUIT"].values[0].replace("-","").isdigit() else "",
                            "FiscalName":cliente["CNOMBRE"].values[0],
                            "Name":cliente["CNOMBRE"].values[0],
                            "Address.countryId": 1010,
                            "Address.street1": cliente["CPROVIN"].values[0],
                            "Address.street2": cliente["CDIREC"].values[0],
                            "Address.postalCode": int(cliente["CCP"].values[0]) if cliente["CCP"].values[0].isdigit() else '',
                            "Address.city": cliente["CLOCAL"].values[0],
                            "address.stateId": int(codigos_prov.get(cliente["CPROVIN"].values[0])),
                            "email": "",
                            "dia_visita": "",
                            "frecuencia_visita":"",
                            "semana_visita":"",
                            "subsegmento":self.selectSubsec(id,cliente["CNOMBRE"].values[0]),
                            "zona": "",
                            "Vendedor": cod_vendedor[str(cliente["VENDEDOR"].values[0])],
                        })
                    else:
                        raise ValueError(f"No se encontró el cliente con Systemid: {id}")
                if filas_nuevas:
                    documento = pd.concat([documento, pd.DataFrame(filas_nuevas)], ignore_index=True)
                # Guardar el archivo actualizado
                documento.sort_values(by=["Systemid"], ascending=True, inplace=True)
                others.format_CLIENTE(documento, os.path.join(config.EXCEL_THALAMUS_PATH, "Template_CLIENTE MANA.xlsx"), len(no_encontrados))
                
                # Ajustar el ancho de las columnas
        except ValueError as e:
            widget.QMessageBox.warning(self, "Error", str(e))
    
    def selectSubsec(self, id, nombre):
        # Crear un diálogo para seleccionar el subsegmento
        dialog = widget.QDialog(self)
        dialog.setWindowTitle("CLIENTE NUEVO - Seleccionar Subsegmento")
        
        # Crear un layout vertical
        layout = widget.QVBoxLayout(dialog)
        # Etiqueta con el ID y nombre del cliente
        label = widget.QLabel(f"ID: {id}\nNombre: {nombre}", dialog)
        layout.addWidget(label)
        # Crear un combo box con los subsegmentos
        subsegmentos = [
            "AGRO",
            "CEMENTERA/CANTERA",
            "CONSTRUCCIÓN",
            "INDUSTRIAS GENERALES",
            "METALES/CAUCHERAS",
            "MINERÍA",
            "TRANSPORTE",
            "OIL & GAS",
            "REVENTA",
            "ENTIDADES",
            "ENERGIA",
            "CONSUMO MASIVO",
            "LUBRICENTRO",
            "CASA DE REPUESTO",
            "CONCESIONARIOS",
            "ESTACIONES DE SERVICIOS",
            "TALLER",
            "SERVICIOS",
            "BARCAZA",
            "CARGUEROS",
            "CONTAINEROS",
            "CRUCEROS",
            "PESQUERO",
            "REMOLCADOR",
            "NAVAL",
            "TANQUEROS",
            "ARENERO",
            "DRAGAS",
            "FRIGORIFICOS",
            "CASA DE REPUESTOS MOTOS"
        ]
        
        combo_box = widget.QComboBox(dialog)
        combo_box.addItems(subsegmentos)
        layout.addWidget(combo_box)
        
        # Botones de aceptar y cancelar
        button_box = widget.QDialogButtonBox(widget.QDialogButtonBox.Ok | widget.QDialogButtonBox.Cancel, dialog)
        layout.addWidget(button_box)
        
        # Conectar senales
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        # Mostrar el diálogo
        if dialog.exec_() == widget.QDialog.Accepted:
            # Obtener el subsegmento seleccionado
            subsegmento_seleccionado = combo_box.currentText()
            return subsegmento_seleccionado
        else:
            return None  # Si se cancela, devolver None
    
    def manejadorEcheq(self):
        # Mostrar barra de carga integrada y deshabilitar botones
        self.label_carga.setText("Cargando E-Cheques, por favor espere...")
        self.frame_carga.setVisible(True)
        for boton in self.botones_principales:
            boton.setEnabled(False)

        self.echeq_thread = ProgressBar.EcheqLoadThread()
        self.echeq_thread.completado.connect(self.on_echeq_loaded)
        self.echeq_thread.start()

    def on_echeq_loaded(self, df):
        """Oculta la barra, habilita botones y abre la ventana de E-cheques"""
        self.frame_carga.setVisible(False)
        self.label_carga.setText("Cargando base de datos, por favor espere...")
        for boton in self.botones_principales:
            boton.setEnabled(True)

        self.echeqWindow = EcheqWindow(df=df)
        self.echeqWindow.show()
    
    def sellIn(self):
        try:
            dateRange = DateYearRangeDialog(self, enable_seller=False)
            resultado = dateRange.exec_()  # ✅ Ejecutar UNA SOLA VEZ
            
            if resultado == widget.QDialog.Accepted:
                # Procesar fecha DESDE según el modo seleccionado
                fecha_desde_procesada = dateRange.fecha_desde_procesada
                
                if dateRange.fecha_desde_manual_seleccionada:
                    # Fecha manual: usar el día exacto
                    fecha_desde = datetime(fecha_desde_procesada.year, fecha_desde_procesada.month, fecha_desde_procesada.day, 0, 0, 0)
                else:
                    # Fecha del desplegable: primer día del mes
                    fecha_desde = datetime(fecha_desde_procesada.year, fecha_desde_procesada.month, 1, 0, 0, 0)
                
                # Procesar fecha HASTA según el modo seleccionado
                fecha_hasta_procesada = dateRange.fecha_hasta_procesada
                if dateRange.fecha_hasta_manual_seleccionada:
                    # Fecha manual: usar el día exacto hasta las 23:59:59
                    fecha_hasta = datetime(fecha_hasta_procesada.year, fecha_hasta_procesada.month, fecha_hasta_procesada.day, 23, 59, 59)
                else:
                    # Fecha del desplegable: último día del mes
                    ultimo_dia = calendar.monthrange(fecha_hasta_procesada.year, fecha_hasta_procesada.month)[1]
                    fecha_hasta = datetime(fecha_hasta_procesada.year, fecha_hasta_procesada.month, ultimo_dia, 23, 59, 59)
                
                # Asegurar que la columna FECHA sea datetime
                if 'FECHA' in self.df_ventas.columns:
                    self.df_ventas['FECHA'] = pd.to_datetime(self.df_ventas['FECHA'])
                
                # ✅ Filtrar los datos (ya no necesitas otro if)
                df_filtrado = self.df_ventas[
                    (self.df_ventas['FECHA'] >= fecha_desde) &
                    (self.df_ventas['FECHA'] <= fecha_hasta) &
                    (self.df_ventas['MODELO'].astype(str).str.startswith('L')) &
                    (self.df_ventas['CODMOV'] == 'RI')
                ]
                    
                # Mostrar la ventana ReportLts con los datos filtrados
                self.winLts = ReportLts(df_filtrado, df_ventas=self.df_ventas, graficos=False)
                self.winLts.show()
                
        except Exception as e:
            widget.QMessageBox.warning(self, "Error", str(e))
            print(f"Error detallado: {e}")
            print(f"Tipo de fecha_desde: {type(fecha_desde) if 'fecha_desde' in locals() else 'No definida'}")
            print(f"Tipo de columna FECHA: {type(self.df_ventas['FECHA'].iloc[0]) if len(self.df_ventas) > 0 else 'DataFrame vacío'}")
    
    def reporteLitros(self):
        try:
            dateRange = DateYearRangeDialog(self)
            if dateRange.exec_() == widget.QDialog.Accepted:
                # Procesar fecha DESDE según el modo seleccionado
                fecha_desde_procesada = dateRange.fecha_desde_procesada
            if dateRange.fecha_desde_manual_seleccionada:
                # Fecha manual: usar el día exacto
                fecha_desde = datetime(fecha_desde_procesada.year, fecha_desde_procesada.month, fecha_desde_procesada.day, 0, 0, 0)
            else:
                # Fecha del desplegable: primer día del mes
                fecha_desde = datetime(fecha_desde_procesada.year, fecha_desde_procesada.month, 1, 0, 0, 0)
            
            # Procesar fecha HASTA según el modo seleccionado
            fecha_hasta_procesada = dateRange.fecha_hasta_procesada
            if dateRange.fecha_hasta_manual_seleccionada:
                # Fecha manual: usar el día exacto hasta las 23:59:59
                fecha_hasta = datetime(fecha_hasta_procesada.year, fecha_hasta_procesada.month, fecha_hasta_procesada.day, 23, 59, 59)
            else:
                # Fecha del desplegable: último día del mes
                ultimo_dia = calendar.monthrange(fecha_hasta_procesada.year, fecha_hasta_procesada.month)[1]
                fecha_hasta = datetime(fecha_hasta_procesada.year, fecha_hasta_procesada.month, ultimo_dia, 23, 59, 59)
            
            # Asegurar que la columna FECHA sea datetime
            if 'FECHA' in self.df_ventas.columns:
                self.df_ventas['FECHA'] = pd.to_datetime(self.df_ventas['FECHA'])
            
            # Filtrado adicional por vendedor (si no es "TODOS")
            if dateRange.vendedor_procesado:  # None si seleccionó "TODOS"
                df_filtrado = self.df_ventas[
                    (self.df_ventas['FECHA'] >= fecha_desde) &
                    (self.df_ventas['FECHA'] <= fecha_hasta) &
                    (self.df_ventas['VENDNUMERO'] == dateRange.vendedor_procesado) &
                    ((self.df_ventas['TC'] == 'FC') | (self.df_ventas['TC'] == 'NC') | (self.df_ventas['TC'] == 'ND')| (self.df_ventas['TC'] == 'FE')| (self.df_ventas['TC'] == 'CR'))
                ]
            else:
                # Filtrado inicial por fecha y modelo (sin filtro de vendedor)
                df_filtrado = self.df_ventas[
                    (self.df_ventas['FECHA'] >= fecha_desde) &
                    (self.df_ventas['FECHA'] <= fecha_hasta) &
                    ((self.df_ventas['TC'] == 'FC') | (self.df_ventas['TC'] == 'NC') | (self.df_ventas['TC'] == 'ND')| (self.df_ventas['TC'] == 'CR')| (self.df_ventas['TC'] == 'FE')| (self.df_ventas['TC'] == 'CR'))
                ]
            
            # Mostrar la ventana ReportLts con los datos filtrados
            self.winLts = ReportLts(df_filtrado,df_ventas=self.df_ventas)
            self.winLts.show()

        except Exception as e:
            widget.QMessageBox.warning(self, "Error", str(e))
            print(f"Error detallado: {e}")
            print(f"Tipo de fecha_desde: {type(fecha_desde) if 'fecha_desde' in locals() else 'No definida'}")
            print(f"Tipo de columna FECHA: {type(self.df_ventas['FECHA'].iloc[0]) if len(self.df_ventas) > 0 else 'DataFrame vacío'}")
    
    def IIBB(self):
        
        mes_anio_dialog = MesAnioDialog(self)
        if mes_anio_dialog.exec_() == widget.QDialog.Accepted:
            mes = mes_anio_dialog.mes_seleccionado
            anio = mes_anio_dialog.anio_seleccionado

            # Cargar bases de datos
            bdClient = pd.DataFrame(iter(DBF(os.path.join(config.DBF_BASE_PATH, 'ctaclien.DBF'), encoding=config.DBF_ENCODING)))
            # ivatemp.DBF (~71 MB): lectura vía DuckDB, solo las columnas que usa el informe.
            ivatemp = dbf_io.leer_dbf(
                os.path.join(config.DBF_BASE_PATH, 'ivatemp.DBF'),
                dbf_io.COLUMNAS_IVATEMP,
            )
            # Convertir columnas de fecha en `ivatemp` a formato datetime
            ivatemp['FECHA'] = pd.to_datetime(ivatemp['FECHA'], errors='coerce')

            # Filtrar `ivatemp` por mes, año y otros criterios
            ivatemp_filtrado = ivatemp[
                (ivatemp['FECHA'].dt.month == mes) &
                (ivatemp['FECHA'].dt.year == anio) &
                ((ivatemp['NROEST'] == '00002') | (ivatemp['NROEST'] == '00003'))

            ]
            total_ingresos_brutos = 0
            resultados = []
            for _, row in ivatemp_filtrado.iterrows():
                cuenta = row['CUENTA']
                nc = str(row['NC']).split()[0].zfill(12)  
                neto = row['NETO']
                perce_1 = row['PERCE_1']

                # Buscar información del cliente en bdClient
                cliente = bdClient[bdClient['CNUMERO'] == cuenta]
                cnombre = cliente['CNOMBRE'].values[0] if not cliente.empty else ''
                # Verificar si el campo de ingresos brutos (ingbrut) está vacío
                ingbrut = cliente['INGBRUT'].values[0] if not cliente.empty else ''
                # Si el campo está vacío, asignar "000-000000-0"
                ingbrut = "000-000000-0" if not ingbrut.strip() else ingbrut
                cuit = str(cliente['CUIT'].values[0]).replace('-', '') if not cliente.empty else ''
                cdirec = cliente['CDIREC'].values[0] if not cliente.empty else ''

                # Ignorar filas donde PERCE_1 es 0
                if perce_1 != 0:
                    percent = 3.00
                    perce_1_83 = round(perce_1 * 0.83333327,2)
                    perce_1_16 = round(perce_1 * 0.1666667,2)
                    tc = row['TC']
                    if tc == "FC":
                        tc = "FA"
                    elif tc == "NC":
                        tc = "CA"
                    # Agregar resultado
                    resultados.append([
                    cnombre,
                    cuit,
                    cdirec,
                    ingbrut,
                    row["FECHA"].strftime("%d/%m/%Y"),
                    tc,
                    nc,
                    neto,
                    percent,
                    perce_1_83,
                    perce_1_16
                ])
                # Calcular el total de ingresos brutos a pagar
                total_ingresos_brutos += perce_1

            # Crear DataFrame con los resultados
            columnas_salida = ['CNOMBRE', 'CUIT', 'CDIREC','INGBRUT', 'FECHA', 'TC', 'NC', 'NETO','PERCENT', 'PERCE_1_83', 'PERCE_1_16']
            df_resultados = pd.DataFrame(resultados, columns=columnas_salida)

            # Guardar el archivo sin cabeceras y con tabulación
            output_path = os.path.join(config.OUTPUT_PATH, f'salib {mes}-{anio}.txt')
            df_resultados.to_csv(
            output_path,
            sep='\t',
            index=False,
            header=False,)
            
            # Mensaje de confirmación del archivo guardado
            mensaje = f"Archivo IIBB.\nGuardado en: {output_path}"
            msg_box = widget.QMessageBox()
            msg_box.setIcon(widget.QMessageBox.Information)  # Icono de información
            msg_box.setWindowTitle("Informe Generado")
            msg_box.setText(mensaje)
            msg_box.setStandardButtons(widget.QMessageBox.Ok)  # Botón de aceptar
            msg_box.exec_()

            # Mostrar ventana con el total de ingresos brutos
            mensaje_total = f"RESUMEN INGRESOS BRUTOS - {mes}/{anio}\n\n"
            mensaje_total += f"Total de Ingresos Brutos a Pagar: ${total_ingresos_brutos:,.2f}\n"
            mensaje_total += f"Cantidad de comprobantes procesados: {len(df_resultados)}"
            
            msg_box_total = widget.QMessageBox()
            msg_box_total.setIcon(widget.QMessageBox.Information)
            msg_box_total.setWindowTitle("Total Ingresos Brutos")
            msg_box_total.setText(mensaje_total)
            msg_box_total.setStandardButtons(widget.QMessageBox.Ok)
            msg_box_total.exec_()

    def keyPressEvent(self, event):
        if event.key() == Qt.Qt.Key_Return or event.key() == Qt.Qt.Key_Enter:
            # Verifica cuál botón tiene el foco y simula un clic
            if self.botonThalamus.hasFocus():
                self.botonThalamus.click()
            elif self.botonLitros.hasFocus():
                self.botonLitros.click()
            elif self.botonMensual.hasFocus():
                self.botonMensual.click()
            elif self.botonSalib.hasFocus():
                self.botonSalib.click()
            elif self.botonEcheq.hasFocus():
                self.botonEcheq.click()
            elif self.botonSellIn.hasFocus():
                self.botonSellIn.click()

    def pedidosCaller(self):
        self.pedidos = VentanaProgramarPedido()
        self.pedidos.show()

    def actualizar_precios_mana_horeb(self):
        ruta_mana  = os.path.join(config.DBF_BASE_PATH,  'abmartic.DBF')
        ruta_horeb = os.path.join(config.DBF_HOREB_PATH, 'abmartic.DBF')

        self.label_carga.setText("Actualizando precios, por favor espere...")
        self.frame_carga.setVisible(True)
        for boton in self.botones_principales:
            boton.setEnabled(False)

        self.update_thread = ProgressBar.ActualizarPreciosThread(
            ruta_mana,
            ruta_horeb,
            os.path.join(config.EXCEL_PRECIOS_PATH, 'Lista de precios Mana.xlsm'),
            os.path.join(config.EXCEL_PRECIOS_PATH, 'Lista Valvoline.xlsx')
        )
        self.update_thread.progress_actualizado.connect(self.on_update_progress)
        self.update_thread.finalizado.connect(self.on_update_finished)
        self.update_thread.start()

    def on_update_progress(self, mensaje):
        """Actualiza el mensaje en la barra de carga integrada"""
        self.label_carga.setText(mensaje)

    def on_update_finished(self, exito, mensaje):
        """Oculta la barra de carga y muestra el resultado"""
        self.frame_carga.setVisible(False)
        self.label_carga.setText("Cargando base de datos, por favor espere...")
        for boton in self.botones_principales:
            boton.setEnabled(True)

        if exito:
            widget.QMessageBox.information(self, "Actualizar Precios", mensaje)
        else:
            widget.QMessageBox.critical(self, "Error", mensaje)
        



if __name__ == "__main__":
    app = widget.QApplication(sys.argv)
    app.setWindowIcon(gui.QIcon(resource_path("src/Distribuidora/shell.ico")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 