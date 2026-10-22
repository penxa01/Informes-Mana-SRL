"""Vigía de reclamos sin novedades: cada tanto consulta la base y avisa cuáles llevan
``rdb.DIAS_SIN_NOVEDADES`` días o más sin actualizar su estado.

La consulta va en un hilo (una conexión corta a Postgres), así que una base lenta o caída no
congela la ventana. Un fallo se ignora en silencio —queda el último resultado bueno— porque es un
chequeo de fondo: avisar de "no pude chequear" cada 30 minutos sería peor que el problema.
"""
import os

import PyQt5.QtCore as core

from src.controllers import reclamos_db as rdb

INTERVALO_MIN = 30
DEMORA_INICIAL_SEG = 8          # que el arranque de la app no compita con esta consulta


class _ConsultaThread(core.QThread):
    resultado = core.pyqtSignal(object)
    fallo = core.pyqtSignal(str)

    def __init__(self, dias):
        super().__init__()
        self._dias = dias

    def run(self):
        con = None
        try:
            con = rdb.conectar()
            vencidos = rdb.reclamos_sin_novedades(con, self._dias)
        except Exception as e:  # base caída, tabla inexistente (todavía no se usó la función), etc.
            self.fallo.emit(str(e) or type(e).__name__)
            return
        finally:
            if con is not None:
                try:
                    con.rollback()
                    con.close()
                except Exception:  # noqa: BLE001
                    pass
        self.resultado.emit(vencidos)


class MonitorReclamos(core.QObject):
    """``cambio(df)`` se emite en cada chequeo exitoso con los reclamos vencidos (puede ser vacío)."""

    cambio = core.pyqtSignal(object)

    def __init__(self, parent=None, dias=None, intervalo_min=INTERVALO_MIN):
        super().__init__(parent)
        self.dias = rdb.dias_de_alerta(os.getenv("RECLAMOS_ALERTA_DIAS")) if dias is None else dias
        self.vencidos = None            # último resultado bueno (DataFrame) o None si nunca se pudo chequear
        self.ultimo_error = ""
        self._hilo = None
        self._timer = core.QTimer(self)
        self._timer.setInterval(int(intervalo_min * 60 * 1000))
        self._timer.timeout.connect(self.comprobar)

    def iniciar(self, demora_seg=DEMORA_INICIAL_SEG):
        """Primer chequeo tras ``demora_seg`` y luego cada ``intervalo_min`` minutos."""
        self._timer.start()
        core.QTimer.singleShot(int(demora_seg * 1000), self.comprobar)

    def comprobar(self):
        """Chequea ahora (si ya hay un chequeo en curso, no hace nada)."""
        if self._hilo is not None and self._hilo.isRunning():
            return
        hilo = _ConsultaThread(self.dias)
        hilo.resultado.connect(self._on_resultado)
        hilo.fallo.connect(self._on_fallo)
        self._hilo = hilo
        hilo.start()

    def esperar(self, ms=5000):
        """Bloquea hasta que termine el chequeo en curso (para cerrar la app sin destruir el hilo)."""
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.wait(ms)

    def _on_resultado(self, vencidos):
        self.vencidos = vencidos
        self.ultimo_error = ""
        self.cambio.emit(vencidos)

    def _on_fallo(self, mensaje):
        self.ultimo_error = mensaje
