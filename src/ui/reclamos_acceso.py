"""Acceso a los reclamos desde cualquier parte de la app (Inicio → Cobranzas, alerta de la barra de estado).

El modal de reclamos (`Views/CuentasCorrientes/Reclamos.py`) necesita `ctacorr` y `ctaclien` (DBF, por la caché Parquet).
Antes los cargaba la sección Cuentas Corrientes; ahora los carga este objeto la primera vez que se pide un reclamo y
los reutiliza un rato (se vuelven a leer si pasaron más de `VIGENCIA_S`, por si cambiaron facturas).
"""
import time
from datetime import date

import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.controllers import cuentas_corrientes_io as cc_io
from src.controllers import reclamos_db as rdb
from src.Views.CuentasCorrientes.Reclamos import ReclamosDialog

#: Las facturas que se pueden reclamar son las emitidas desde esta fecha (el default que tenía Cuentas Corrientes).
FECHA_DESDE = date(2024, 1, 1)
VIGENCIA_S = 10 * 60


class _CargaThread(core.QThread):
    """Lee ctacorr + ctaclien (caché Parquet) fuera del hilo de la UI."""
    completado = core.pyqtSignal(object, object)
    fallo = core.pyqtSignal(str)

    def run(self):
        try:
            ctacorr, clientes = cc_io.cargar_datos()
        except Exception as e:  # el hilo no puede propagar: se informa por señal
            self.fallo.emit(str(e))
            return
        self.completado.emit(ctacorr, clientes)


class AccesoReclamos(core.QObject):
    def __init__(self, ventana, parent=None):
        super().__init__(parent)
        self._ventana = ventana          # padre de los diálogos
        self._ctacorr = None
        self._clientes = None
        self._cargados_en = 0.0
        self._hilo = None
        self._cuenta_pendiente = None

    def abrir(self, cuenta=None):
        """Abre el modal de reclamos (con `cuenta` preseleccionada si viene), cargando los datos si hace falta."""
        if self._ctacorr is not None and time.time() - self._cargados_en < VIGENCIA_S:
            self._mostrar(cuenta)
            return
        if self._hilo is not None and self._hilo.isRunning():
            self._cuenta_pendiente = cuenta
            return
        self._cuenta_pendiente = cuenta
        widget.QApplication.setOverrideCursor(core.Qt.WaitCursor)
        self._hilo = _CargaThread()
        self._hilo.completado.connect(self._al_cargar)
        self._hilo.fallo.connect(self._al_fallar)
        self._hilo.start()

    def esperar(self):
        if self._hilo is not None:
            self._hilo.wait(8000)

    def _al_cargar(self, ctacorr, clientes):
        widget.QApplication.restoreOverrideCursor()
        self._ctacorr, self._clientes = ctacorr, clientes
        self._cargados_en = time.time()
        cuenta, self._cuenta_pendiente = self._cuenta_pendiente, None
        core.QTimer.singleShot(0, lambda: self._mostrar(cuenta))

    def _al_fallar(self, mensaje):
        widget.QApplication.restoreOverrideCursor()
        widget.QMessageBox.warning(self._ventana, "Reclamos", f"No se pudieron leer las cuentas corrientes:\n{mensaje}")

    def _mostrar(self, cuenta):
        widget.QApplication.setOverrideCursor(core.Qt.WaitCursor)
        try:
            con = rdb.conectar()
            rdb.asegurar_esquema(con)
            con.commit()
        except Exception as e:
            widget.QApplication.restoreOverrideCursor()
            widget.QMessageBox.warning(self._ventana, "Reclamos", f"No se pudo conectar a la base de datos de Pedidos:\n{e}")
            return
        widget.QApplication.restoreOverrideCursor()
        try:
            ReclamosDialog(con, self._ctacorr, self._clientes, FECHA_DESDE, cuenta, self._ventana).exec_()
        finally:
            con.close()
