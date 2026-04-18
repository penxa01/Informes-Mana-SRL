from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
import PyQt5.QtCore as Qt
from dbfread import DBF
import pandas as pd
import dbf
import os

class InfoProgressBarWindow(QDialog):
    def __init__(self, mensaje="Cargando...", minimo=0, maximo=100, parent=None):
        super().__init__(parent)

        # Configuración de la ventana
        self.setWindowTitle("Información")
        self.setFixedSize(200, 100)

        # Layout principal
        self.layout = QVBoxLayout(self)

        # Etiqueta del mensaje
        self.label = QLabel(mensaje)
        self.layout.addWidget(self.label)

        # Barra de progreso
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(minimo)
        self.progress_bar.setMaximum(maximo)
        self.layout.addWidget(self.progress_bar)


    def actualizar_progreso(self, valor):
        """
        Actualiza el valor de la barra de progreso.
        """
        self.progress_bar.setValue(valor)

    def actualizar_mensaje(self, mensaje):
        """
        Actualiza el mensaje mostrado en la ventana.
        """
        self.label.setText(mensaje)

class LoadDataThread(Qt.QThread):
    data_loaded = Qt.pyqtSignal(pd.DataFrame)

    def run(self):
        # Cargar el DataFrame aquí
        df = pd.DataFrame(iter(DBF("d:/tiempo/vtiempoges/GESTION/MANA2014/fachist.DBF", encoding='latin1')))
        
        self.data_loaded.emit(df)


class ActualizarPreciosThread(Qt.QThread):
    """Hilo para actualizar precios sin bloquear la UI"""
    progress_actualizado = Qt.pyqtSignal(str)  # Emisor de mensajes de progreso
    finalizado = Qt.pyqtSignal(bool, str)  # Emisor de estado final (éxito, mensaje)
    
    def __init__(self, rutas_dbf, excel_precios_path, excel_valvoline_path):
        super().__init__()
        self.rutas_dbf = rutas_dbf  # Lista de rutas DBF a actualizar
        self.excel_precios_path = excel_precios_path
        self.excel_valvoline_path = excel_valvoline_path
    
    def run(self):
        try:
            # Cargar archivos Excel
            self.progress_actualizado.emit("Cargando archivos de precios...")
            excel_precios = pd.read_excel(
                self.excel_precios_path,
                sheet_name='Lista De Precios',
                header=2
            )
            excel_valvoline = pd.read_excel(
                self.excel_valvoline_path,
                sheet_name='Lista',
                header=1
            )
            
            total_rutas = len(self.rutas_dbf)
            
            # Procesar cada ruta DBF
            for idx, ruta in enumerate(self.rutas_dbf, 1):
                self.progress_actualizado.emit(f"Procesando base de datos {idx}/{total_rutas}...\n{ruta}")
                self._actualizar_precios_dbf(ruta, excel_precios, excel_valvoline, idx, total_rutas)
            
            self.finalizado.emit(True, "Los precios se han actualizado correctamente.")
            
        except Exception as e:
            self.finalizado.emit(False, f"Error al actualizar precios: {str(e)}")
    
    def _actualizar_precios_dbf(self, ruta, excel_precios, excel_valvoline, num_base, total_bases):
        """Actualiza los precios en un archivo DBF específico"""
        cabecera = True
        
        try:
            abmartic = dbf.Table(ruta)
            abmartic.open(mode=dbf.READ_WRITE)
            
            # Actualizar con precios de Lista Mana
            self.progress_actualizado.emit(f"Actualizando Lista Mana ({num_base}/{total_bases})...")
            for index, row in excel_precios.iterrows():
                if cabecera:
                    cabecera = False
                    continue
                
                try:
                    sku = str(row['SKU']).strip()
                    precio_sIVA = round(float(row['Precio de venta s/IVA']), 2)
                    precio_gerardo = round(float(row['Lista Gerardo']) / 1.21, 2)
                    precio_Luis = round(float(row['Lista Luis Richarte']) / 1.21, 2)
                    precio_industria = round(float(row['Lista Ecominera S/IVA']), 2)
                    
                    for art in abmartic:
                        if (art.CODART.strip() == sku.strip()) or (art.ARTIPROV.strip() == sku.strip()):
                            with art:
                                setattr(art, 'PRECIO1', precio_sIVA)
                                setattr(art, 'PRECIO7', precio_gerardo)
                                setattr(art, 'PRECIO8', precio_industria)
                                setattr(art, 'PRECIO9', precio_Luis)
                            break
                except Exception as e:
                    print(f"Error procesando SKU {sku}: {str(e)}")
                    continue
            
            # Actualizar con precios de Valvoline
            cabecera = True
            self.progress_actualizado.emit(f"Actualizando Lista Valvoline ({num_base}/{total_bases})...")
            for index, row in excel_valvoline.iterrows():
                if cabecera:
                    cabecera = False
                    continue
                
                try:
                    sku = str(row['CODIGO']).strip()
                    precio_sIVA = round(float(row['PRECIO S/IVA']), 2)
                    precio_gerardo = round(float(row['LISTA GERARDO']), 2)
                    
                    for art in abmartic:
                        if (art.CODART.strip() == sku.strip()) or (art.ARTIPROV.strip() == sku.strip()):
                            with art:
                                setattr(art, 'PRECIO1', precio_sIVA)
                                setattr(art, 'PRECIO7', precio_gerardo)
                            break
                except Exception as e:
                    print(f"Error procesando SKU Valvoline {sku}: {str(e)}")
                    continue
            
            abmartic.close()
            self.progress_actualizado.emit(f"Base de datos {num_base}/{total_bases} completada.")
            
        except Exception as e:
            raise Exception(f"Error en {ruta}: {str(e)}")


class EcheqLoadThread(Qt.QThread):
    """Hilo para cargar archivos E-cheques sin bloquear la UI"""
    completado = Qt.pyqtSignal(pd.DataFrame)

    DIREC = 'd:/tiempo/E-cheqs'
    COLUMNAS = [
        'Pagador Nombre Apellido/Razón Social', 'Unnamed: 1', 'Pagador Cuit',
        'Beneficiario Cuit', 'Beneficiario Nombre Apellido/Razón Social',
        'Tenedor Cuit', 'Tenedor Nombre Apellido/Razón Social', 'Banco Emisor',
        'CMC7', 'Endoso: fecha y hora', 'Endoso: tipo', 'Endoso: Estado',
        'Endoso: tipo de documento beneficiario',
        'Endoso: número de documento beneficiario',
        'Endoso: Razón social / Nombre y apellido beneficiario',
        'Endoso: tipo de documento emisor del endoso',
        'Endoso: número de documento emisor del endoso',
        'Endoso: Razón social / Nombre y emisor del endoso', 'Agrupador ID',
        'Nro de Cheque', 'Echeq id', 'Código Visualización', 'Fecha de Emisión',
        'Fecha de Pago', 'Tipo', 'Carácter', 'Modo', 'Monto', 'Estado',
        'Concepto', 'Motivo de Pago', 'Motivo de Repudio en Emisión',
        'Código de Referencia 1', 'Referencia 1', 'Código de Referencia 2',
        'Referencia 2', 'Código de Referencia 3', 'Unnamed: 37', 'Referencia 3',
        'Codigo de banco', 'Sucursal', 'Código Postal', 'Nro de cuenta',
        'Emisor Cuit', 'Razón Social Emisor'
    ]

    def run(self):
        df = pd.DataFrame(columns=self.COLUMNAS)
        if not os.path.exists(self.DIREC):
            self.completado.emit(df)
            return

        for archivo in os.listdir(self.DIREC):
            try:
                archivo_path = f"{self.DIREC}/{archivo}"
                if archivo.startswith('E'):
                    arch = pd.read_excel(archivo_path)
                else:
                    arch = pd.read_excel(archivo_path, header=1)

                arch.columns = arch.columns.str.strip()
                columnas_validas = [c for c in self.COLUMNAS if c in arch.columns]
                arch_filtrado = arch[columnas_validas]
                df = pd.concat([df, arch_filtrado], ignore_index=True)
            except Exception:
                continue

        # Eliminar duplicados usando Nro de Cheque como clave única
        if 'Nro de Cheque' in df.columns:
            df = df.drop_duplicates(subset=['Nro de Cheque'], keep='last')
            df = df.reset_index(drop=True)

        self.completado.emit(df)