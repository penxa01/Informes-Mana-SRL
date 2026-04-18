import os
import shutil

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
import PyQt5.QtCore as Qt
from dbfread import DBF
import pandas as pd
import dbf

from src.controllers import config


class InfoProgressBarWindow(QDialog):
    def __init__(self, mensaje="Cargando...", minimo=0, maximo=100, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Información")
        self.setFixedSize(200, 100)
        self.layout = QVBoxLayout(self)
        self.label = QLabel(mensaje)
        self.layout.addWidget(self.label)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(minimo)
        self.progress_bar.setMaximum(maximo)
        self.layout.addWidget(self.progress_bar)

    def actualizar_progreso(self, valor):
        self.progress_bar.setValue(valor)

    def actualizar_mensaje(self, mensaje):
        self.label.setText(mensaje)


class LoadDataThread(Qt.QThread):
    data_loaded = Qt.pyqtSignal(pd.DataFrame)

    def run(self):
        ruta = os.path.join(config.DBF_BASE_PATH, "fachist.DBF")
        df = pd.DataFrame(iter(DBF(ruta, encoding='latin1')))
        self.data_loaded.emit(df)


class ActualizarPreciosThread(Qt.QThread):
    """Actualiza precios en abmartic.DBF de MANA y luego copia el archivo a HOREB."""
    progress_actualizado = Qt.pyqtSignal(str)
    finalizado = Qt.pyqtSignal(bool, str)

    def __init__(self, ruta_mana, ruta_horeb, excel_precios_path, excel_valvoline_path):
        super().__init__()
        self.ruta_mana = ruta_mana
        self.ruta_horeb = ruta_horeb
        self.excel_precios_path = excel_precios_path
        self.excel_valvoline_path = excel_valvoline_path

    def run(self):
        try:
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

            self._actualizar_precios_dbf(self.ruta_mana, excel_precios, excel_valvoline)

            self.progress_actualizado.emit("Copiando base de datos a HOREB...")
            shutil.copy2(self.ruta_mana, self.ruta_horeb)
            self.progress_actualizado.emit("Copia a HOREB completada.")

            self.finalizado.emit(True, "Precios actualizados correctamente en MANA y replicados en HOREB.")

        except Exception as e:
            self.finalizado.emit(False, f"Error al actualizar precios: {str(e)}")

    def _actualizar_precios_dbf(self, ruta, excel_precios, excel_valvoline):
        cabecera = True
        abmartic = dbf.Table(ruta)
        abmartic.open(mode=dbf.READ_WRITE)

        try:
            self.progress_actualizado.emit("Actualizando Lista Mana...")
            for _, row in excel_precios.iterrows():
                if cabecera:
                    cabecera = False
                    continue
                try:
                    sku = str(row['SKU']).strip()
                    precio_sIVA      = round(float(row['Precio de venta s/IVA']), 2)
                    precio_gerardo   = round(float(row['Lista Gerardo']) / 1.21, 2)
                    precio_Luis      = round(float(row['Lista Luis Richarte']) / 1.21, 2)
                    precio_industria = round(float(row['Lista Ecominera S/IVA']), 2)

                    for art in abmartic:
                        if art.CODART.strip() == sku or art.ARTIPROV.strip() == sku:
                            with art:
                                setattr(art, 'PRECIO1', precio_sIVA)
                                setattr(art, 'PRECIO7', precio_gerardo)
                                setattr(art, 'PRECIO8', precio_industria)
                                setattr(art, 'PRECIO9', precio_Luis)
                            break
                except Exception as e:
                    print(f"Error procesando SKU {sku}: {e}")

            cabecera = True
            self.progress_actualizado.emit("Actualizando Lista Valvoline...")
            for _, row in excel_valvoline.iterrows():
                if cabecera:
                    cabecera = False
                    continue
                try:
                    sku            = str(row['CODIGO']).strip()
                    precio_sIVA    = round(float(row['PRECIO S/IVA']), 2)
                    precio_gerardo = round(float(row['LISTA GERARDO']), 2)

                    for art in abmartic:
                        if art.CODART.strip() == sku or art.ARTIPROV.strip() == sku:
                            with art:
                                setattr(art, 'PRECIO1', precio_sIVA)
                                setattr(art, 'PRECIO7', precio_gerardo)
                            break
                except Exception as e:
                    print(f"Error procesando SKU Valvoline {sku}: {e}")

        finally:
            abmartic.close()


class EcheqLoadThread(Qt.QThread):
    """Carga todos los archivos Excel de e-cheques desde ECHEQ_PATH."""
    completado = Qt.pyqtSignal(pd.DataFrame)

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
        direc = config.ECHEQ_PATH
        df = pd.DataFrame(columns=self.COLUMNAS)

        if not os.path.exists(direc):
            self.completado.emit(df)
            return

        for archivo in os.listdir(direc):
            try:
                archivo_path = os.path.join(direc, archivo)
                arch = pd.read_excel(archivo_path) if archivo.startswith('E') else pd.read_excel(archivo_path, header=1)
                arch.columns = arch.columns.str.strip()
                columnas_validas = [c for c in self.COLUMNAS if c in arch.columns]
                df = pd.concat([df, arch[columnas_validas]], ignore_index=True)
            except Exception:
                continue

        if 'Nro de Cheque' in df.columns:
            df = df.drop_duplicates(subset=['Nro de Cheque'], keep='last').reset_index(drop=True)

        self.completado.emit(df)
