import os
import shutil

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
import PyQt5.QtCore as Qt
import pandas as pd
import dbf

from src.controllers import config
from src.controllers import dbf_io
from src.controllers import echeq_io


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
        # fachist.DBF (~81 MB): se lee vía DuckDB con caché Parquet. Si el DBF no
        # cambió desde la última conversión, la carga es casi instantánea.
        # Solo se traen las columnas que usa la app (dbf_io.COLUMNAS_VENTAS).
        ruta = os.path.join(config.DBF_BASE_PATH, "fachist.DBF")
        cache = os.path.join(config.CACHE_PATH, "fachist.parquet")
        df = dbf_io.leer_dbf_cacheado(ruta, cache, dbf_io.COLUMNAS_VENTAS)
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
        # Construir dict de actualizaciones desde ambos Excel (una sola vez)
        # Valvoline itera después, por lo que sus valores sobreescriben PRECIO1/7
        # para SKUs que aparezcan en ambas listas (comportamiento idéntico al original)
        updates = {}

        self.progress_actualizado.emit("Leyendo Lista Mana...")
        for _, row in excel_precios.iloc[1:].iterrows():
            try:
                sku = str(row['SKU']).strip()
                if not sku or sku == 'nan':
                    continue
                updates[sku] = {
                    'PRECIO1': round(float(row['Precio de venta s/IVA']), 2),
                    'PRECIO7': round(float(row['Lista Gerardo']) / 1.21, 2),
                    'PRECIO8': round(float(row['Lista Ecominera S/IVA']), 2),
                    'PRECIO9': round(float(row['Lista Luis Richarte']) / 1.21, 2),
                }
            except Exception as e:
                print(f"Error procesando SKU Mana: {e}")

        self.progress_actualizado.emit("Leyendo Lista Valvoline...")
        for _, row in excel_valvoline.iloc[1:].iterrows():
            try:
                sku = str(row['CODIGO']).strip()
                if not sku or sku == 'nan':
                    continue
                valvoline = {
                    'PRECIO1': round(float(row['PRECIO S/IVA']), 2),
                    'PRECIO7': round(float(row['LISTA GERARDO']), 2),
                }
                if sku in updates:
                    updates[sku].update(valvoline)
                else:
                    updates[sku] = valvoline
            except Exception as e:
                print(f"Error procesando SKU Valvoline: {e}")

        # Pasada única por el DBF — O(n+m) en lugar de O(n*m)
        self.progress_actualizado.emit("Actualizando base de datos...")
        abmartic = dbf.Table(ruta)
        abmartic.open(mode=dbf.READ_WRITE)
        try:
            for art in abmartic:
                codart   = art.CODART.strip()
                artiprov = art.ARTIPROV.strip()
                update = updates.get(codart) or (updates.get(artiprov) if artiprov else None)
                if update:
                    with art:
                        for field, value in update.items():
                            setattr(art, field, value)
        finally:
            abmartic.close()


class EcheqLoadThread(Qt.QThread):
    """Carga los e-cheques desde ECHEQ_PATH, con caché por archivo (ver
    `echeq_io.cargar_echeqs_cacheado`): solo relee del disco los Excel nuevos
    o modificados desde la última carga."""
    completado = Qt.pyqtSignal(pd.DataFrame)

    COLUMNAS = echeq_io.COLUMNAS  # compatibilidad: código viejo que referencia EcheqLoadThread.COLUMNAS

    def run(self):
        cache = os.path.join(config.CACHE_PATH, "echeqs.pkl")
        df = echeq_io.cargar_echeqs_cacheado(config.ECHEQ_PATH, cache)
        self.completado.emit(df)
