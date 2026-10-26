"""Tarjeta "Ubicación" del detalle de un pedido: mapita reducido del cliente.

- Con enlace cargado: mapa chico con el pin; al tocarlo se abre el enlace en Google Maps.
  El botón "Cambiar" permite pegar otro enlace (vacío = quitarlo).
- Sin enlace: invita a cargarlo.

La ubicación vive en el cliente (`cliente.ubicacion_maps` + `ubicacion_lat/lng`), así se
carga una sola vez y vale para todos sus pedidos. Las coordenadas se leen del enlace al
guardarlo (ver `controllers/ubicacion_maps.py`); el mapa se arma con teselas de
OpenStreetMap en un hilo aparte, para no congelar la ventana si no hay internet.
"""
from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from src.controllers import ubicacion_maps as um

ANCHO_MAPA = 216
ALTO_MAPA = 84
ZOOM = 16

# Los hilos en marcha se guardan acá: si la ventana se cierra antes de que terminen,
# Qt no puede destruir un QThread vivo (cierra el programa).
_hilos_vivos = set()


def guardar_ubicacion(conexion, id_cliente, enlace, coordenadas):
    """Guarda (o quita, si `enlace` es None) la ubicación del cliente. `conexion` es una
    función que devuelve una conexión a la base de Pedidos."""
    lat, lng = coordenadas if (enlace and coordenadas) else (None, None)
    conn = conexion()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE Cliente SET ubicacion_maps = %s, ubicacion_lat = %s, ubicacion_lng = %s "
            "WHERE id_cliente = %s",
            (enlace or None, lat, lng, id_cliente),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class _CargaMapa(QThread):
    """Arma la imagen del mapa (descarga/lee las teselas y dibuja el pin)."""
    listo = pyqtSignal(object)   # QImage
    fallo = pyqtSignal()

    def __init__(self, lat, lng):
        super().__init__()
        self._lat, self._lng = lat, lng

    def run(self):
        try:
            img = QImage(ANCHO_MAPA, ALTO_MAPA, QImage.Format_ARGB32)
            img.fill(QColor("#e2e8f0"))
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            for tx, ty, dx, dy in um.plan_teselas(self._lat, self._lng, ZOOM, ANCHO_MAPA, ALTO_MAPA):
                tesela = QImage()
                tesela.loadFromData(um.descargar_tesela(ZOOM, tx, ty))
                p.drawImage(dx, dy, tesela)
            self._dibujar_pin(p)
            self._dibujar_atribucion(p)
            p.end()
            self.listo.emit(img)
        except Exception:
            self.fallo.emit()

    @staticmethod
    def _dibujar_pin(p):
        cx, cy = ANCHO_MAPA / 2, ALTO_MAPA / 2
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(QColor("#dc2626"))
        p.drawEllipse(int(cx - 7), int(cy - 7), 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(cx - 2), int(cy - 2), 4, 4)

    @staticmethod
    def _dibujar_atribucion(p):
        # La licencia de OpenStreetMap exige mostrar la atribución sobre el mapa.
        p.setFont(QFont("Segoe UI", 6))
        texto = "© OpenStreetMap"
        ancho = p.fontMetrics().horizontalAdvance(texto) + 6
        p.fillRect(ANCHO_MAPA - ancho, ALTO_MAPA - 11, ancho, 11, QColor(255, 255, 255, 190))
        p.setPen(QColor("#475569"))
        p.drawText(ANCHO_MAPA - ancho + 3, ALTO_MAPA - 3, texto)


class _MapaTocable(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class TarjetaUbicacion(QFrame):
    """`conexion`: función sin argumentos que devuelve una conexión a la base de Pedidos."""

    def __init__(self, conexion, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedWidth(ANCHO_MAPA + 24)
        self._conexion = conexion
        self._id_cliente = None
        self._enlace = None
        self._coordenadas = None
        self._token = 0   # descarta el resultado de un mapa viejo si el cliente cambió

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 7, 12, 8)
        raiz.setSpacing(4)

        cab = QHBoxLayout()
        titulo = QLabel("UBICACIÓN")
        titulo.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; background: transparent; border: none;")
        cab.addWidget(titulo)
        cab.addStretch(1)
        self.btn_cambiar = QPushButton("Cambiar")
        self.btn_cambiar.setCursor(Qt.PointingHandCursor)
        self.btn_cambiar.setFlat(True)
        self.btn_cambiar.setStyleSheet(
            "QPushButton { color: #2563eb; border: none; background: transparent; padding: 0px;"
            " font-size: 10px; font-weight: 700; } QPushButton:hover { color: #1d4ed8; }"
        )
        self.btn_cambiar.clicked.connect(self.cambiar)
        cab.addWidget(self.btn_cambiar)
        raiz.addLayout(cab)

        self.mapa = _MapaTocable()
        self.mapa.setFixedSize(ANCHO_MAPA, ALTO_MAPA)
        self.mapa.setAlignment(Qt.AlignCenter)
        self.mapa.setCursor(Qt.PointingHandCursor)
        self.mapa.setToolTip("Abrir en Google Maps")
        self.mapa.clicked.connect(self.abrir_en_maps)
        raiz.addWidget(self.mapa)

        self.vacio = QWidget()
        self.vacio.setFixedSize(ANCHO_MAPA, ALTO_MAPA)
        vl = QVBoxLayout(self.vacio)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(6)
        self.lbl_vacio = QLabel("Este cliente no tiene\nubicación cargada")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("font-size: 10px; color: #94a3b8; background: transparent; border: none;")
        vl.addWidget(self.lbl_vacio, 1)
        self.btn_cargar = QPushButton("Cargar enlace de Maps")
        self.btn_cargar.setCursor(Qt.PointingHandCursor)
        self.btn_cargar.setStyleSheet(
            "QPushButton { background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;"
            " border-radius: 5px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            " QPushButton:hover { background-color: #dbeafe; }"
        )
        self.btn_cargar.clicked.connect(self.cambiar)
        vl.addWidget(self.btn_cargar)
        raiz.addWidget(self.vacio)

        self._pintar_estado_vacio()

    # ── estado ─────────────────────────────────────────────────────────────
    def mostrar(self, id_cliente, enlace, lat, lng):
        coordenadas = (lat, lng) if (lat is not None and lng is not None) else None
        sin_cambios = (id_cliente, enlace, coordenadas) == (self._id_cliente, self._enlace, self._coordenadas)
        self._id_cliente, self._enlace, self._coordenadas = id_cliente, enlace, coordenadas
        if sin_cambios:
            return   # el detalle recarga sus datos varias veces: no volver a dibujar el mismo mapa
        self._token += 1
        if not enlace:
            self._pintar_estado_vacio()
            return
        self.vacio.hide()
        self.mapa.show()
        self.btn_cambiar.show()
        if coordenadas:
            self.mapa.setPixmap(QPixmap())
            self.mapa.setText("Cargando mapa…")
            self._estilo_mapa(texto=True)
            self._cargar_mapa(*coordenadas)
        else:
            self.mapa.setPixmap(QPixmap())
            self.mapa.setText("No pude ubicar el enlace en el mapa.\nTocá para abrirlo en Google Maps.")
            self._estilo_mapa(texto=True)

    def _pintar_estado_vacio(self):
        self.mapa.hide()
        self.vacio.show()
        self.btn_cambiar.hide()

    def _estilo_mapa(self, texto):
        self.mapa.setStyleSheet(
            "background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px;"
            " font-size: 10px; color: #64748b;" if texto else "border: 1px solid #e2e8f0; border-radius: 6px;"
        )

    def _cargar_mapa(self, lat, lng):
        token = self._token
        hilo = _CargaMapa(lat, lng)
        _hilos_vivos.add(hilo)
        hilo.listo.connect(lambda img, t=token: self._mapa_listo(t, img))
        hilo.fallo.connect(lambda t=token: self._mapa_fallo(t))
        hilo.finished.connect(lambda h=hilo: (_hilos_vivos.discard(h), h.deleteLater()))
        hilo.start()

    def _mapa_listo(self, token, img):
        if token != self._token:
            return
        self.mapa.setText("")
        self.mapa.setPixmap(QPixmap.fromImage(img))
        self._estilo_mapa(texto=False)

    def _mapa_fallo(self, token):
        if token != self._token:
            return
        self.mapa.setText("Mapa no disponible (sin internet).\nTocá para abrirlo en Google Maps.")
        self._estilo_mapa(texto=True)

    # ── acciones ───────────────────────────────────────────────────────────
    def abrir_en_maps(self):
        if self._enlace:
            QDesktopServices.openUrl(QUrl(self._enlace))

    def cambiar(self):
        if self._id_cliente is None:
            return
        texto, ok = QInputDialog.getText(
            self, "Ubicación del cliente",
            "Pegá el enlace de Google Maps del cliente\n(dejalo vacío para quitar la ubicación):",
            QLineEdit.Normal, self._enlace or "",
        )
        if not ok:
            return
        texto = texto.strip()
        if texto and not um.es_enlace_valido(texto):
            QMessageBox.warning(self, "Enlace no válido",
                                "Tiene que ser un enlace que empiece con http:// o https://")
            return
        coordenadas = None
        if texto:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                coordenadas = um.resolver_coordenadas(texto)
            finally:
                QApplication.restoreOverrideCursor()
        try:
            guardar_ubicacion(self._conexion, self._id_cliente, texto or None, coordenadas)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar la ubicación: {e}")
            return
        if texto and not coordenadas:
            QMessageBox.information(
                self, "Ubicación guardada",
                "Guardé el enlace, pero no pude leer las coordenadas para dibujar el mapa "
                "(se puede abrir igual en Google Maps).\n\nSi es un enlace corto, probá con el enlace "
                "completo que aparece al abrir el lugar en Maps.")
        self.mostrar(self._id_cliente, texto or None, *(coordenadas or (None, None)))
