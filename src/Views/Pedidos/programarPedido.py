import psycopg2
import os
import socket
import hashlib

from PyQt5.QtWidgets import (
    QAction, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit, QSpinBox,
    QMessageBox, QFormLayout, QGroupBox, QLineEdit, QComboBox,
    QSplitter, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QObject, QPropertyAnimation, QRect, QEasingCurve, QPointF, QSize
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap, QPainter, QPainterPath, QPen

from datetime import date, datetime
from dbfread import DBF

from src.controllers import config
from src.Views.Pedidos.mapa_ubicacion import TarjetaUbicacion

# ── Conexión única a PostgreSQL ─────────────────────────────────────────────
# Antes había 6 copias idénticas de esto con host y credenciales hardcodeados.
# OJO: la BD de Pedidos NO es la de `config.DB_*` (eso apunta a un postgres
# local de otro módulo). Estos son los valores reales del módulo Pedidos,
# ahora en un solo lugar y sobreescribibles por variable de entorno, más un
# timeout para que la UI no se cuelgue si la BD no responde.
_PEDIDOS_DB_HOST = os.getenv("PEDIDOS_DB_HOST", config.DB_HOST)   # config.DB_HOST: servidor -> localhost, resto -> servidor
_PEDIDOS_DB_NAME = os.getenv("PEDIDOS_DB_NAME", "pedidosMana")
_PEDIDOS_DB_USER = os.getenv("PEDIDOS_DB_USER", "postgres")
_PEDIDOS_DB_PASSWORD = os.getenv("PEDIDOS_DB_PASSWORD", "manapedidos2025")


def _conexion():
    return psycopg2.connect(
        host=socket.gethostbyname(_PEDIDOS_DB_HOST),
        database=_PEDIDOS_DB_NAME,
        user=_PEDIDOS_DB_USER,
        password=_PEDIDOS_DB_PASSWORD,
        connect_timeout=6,
    )


# ── Paleta / helpers de estilo (Tailwind slate + blue, igual que el resto) ──
_ESTADO_PILL = {
    "pendiente":  ("#fef3c7", "#92400e", "#fde68a"),
    "programado": ("#dbeafe", "#1e40af", "#bfdbfe"),
    "en camino":  ("#e0e7ff", "#3730a3", "#c7d2fe"),
    "entregado":  ("#d1fae5", "#065f46", "#a7f3d0"),
}
_ESTADO_PILL_DEFECTO = ("#f1f5f9", "#475569", "#e2e8f0")


def _pill_estado(estado):
    """QLabel con forma de pill coloreada según el estado del pedido."""
    txt = str(estado or "").strip()
    bg, fg, borde = _ESTADO_PILL.get(txt.lower(), _ESTADO_PILL_DEFECTO)
    lbl = QLabel(txt.capitalize() or "—")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"QLabel {{ background-color: {bg}; color: {fg}; border: 1px solid {borde};"
        " border-radius: 9px; padding: 1px 10px; font-size: 10px; font-weight: 700; }"
    )
    return lbl


def _centrar(w):
    """Envuelve un widget en un contenedor transparente centrado (para meterlo
    en una celda de tabla con `setCellWidget`). El estilo se scopea con
    objectName para NO pisar el estilo del widget hijo."""
    c = QWidget()
    c.setObjectName("celdaCentrada")
    c.setStyleSheet("QWidget#celdaCentrada { background: transparent; }")
    lay = QHBoxLayout(c)
    lay.setContentsMargins(4, 3, 4, 3)
    lay.addStretch(1)
    lay.addWidget(w)
    lay.addStretch(1)
    return c


def _borrar_pedido(id_pedido):
    """Borra el pedido y sus líneas en una sola transacción (físico, sin vuelta atrás)."""
    conn = _conexion()
    try:
        cur = conn.cursor()
        # Primero los detalles (clave foránea), después el pedido.
        cur.execute("DELETE FROM DetallePedido WHERE id_pedido = %s", (id_pedido,))
        cur.execute("DELETE FROM Pedido WHERE id_pedido = %s", (id_pedido,))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_QSS_DIALOGO_PEDIDO = """
    QDialog { background-color: #f1f5f9; }
    QWidget { font-family: 'Segoe UI', Arial, sans-serif; color: #334155; }
    QLabel { background: transparent; }
    QFrame#card { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }
    QFrame#kpi { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
    QTableWidget {
        background-color: white; alternate-background-color: #f8fafc;
        selection-background-color: #dbeafe; selection-color: #1e293b;
        border: none; font-size: 11px;
    }
    QTableWidget::item { padding: 2px 8px; border: none; }
    QHeaderView::section {
        background-color: #f1f5f9; color: #475569; padding: 5px 8px;
        border: none; border-bottom: 1px solid #e2e8f0; font-weight: 700; font-size: 10px;
    }
    QTableCornerButton::section { background-color: #f1f5f9; border: none; }
    QDateEdit, QSpinBox, QLineEdit, QComboBox {
        border: 1px solid #cbd5e1; border-radius: 5px; padding: 3px 6px;
        background-color: white; font-size: 11px;
    }
    QDateEdit:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
    QPushButton { border-radius: 6px; padding: 6px 14px; font-size: 11px; font-weight: 700; }
    QPushButton#btnOk { background-color: #059669; color: white; border: none; }
    QPushButton#btnOk:hover { background-color: #047857; }
    QPushButton#btnOkOutline { background-color: white; color: #047857; border: 1px solid #6ee7b7; }
    QPushButton#btnOkOutline:hover { background-color: #ecfdf5; }
    QPushButton#btnInfo { background-color: #2563eb; color: white; border: none; }
    QPushButton#btnInfo:hover { background-color: #1d4ed8; }
    QPushButton#btnDanger { background-color: white; color: #dc2626; border: 1px solid #fca5a5; }
    QPushButton#btnDanger:hover { background-color: #fef2f2; }
    QPushButton#btnNeutral { background-color: #475569; color: white; border: none; }
    QPushButton#btnNeutral:hover { background-color: #334155; }
    QPushButton#btnGhost { background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
    QPushButton#btnGhost:hover { background-color: #dbeafe; }
    QPushButton#btnDelIcon { background-color: transparent; color: #94a3b8; border: none; font-weight: 700; padding: 0px; }
    QPushButton#btnDelIcon:hover { color: #dc2626; background-color: #fef2f2; border-radius: 4px; }
"""


# Columnas de las grillas de Pedidos (None = estira). Angostas a propósito: ahora
# las dos grillas comparten el ancho de la ventana, una al lado de la otra.
_ANCHOS_TABLA_PEDIDOS = [48, None, 88, 104, 116, 72]


def _icono_ojo(color="#ffffff", lado=16):
    """Ojito dibujado a mano (no depende de la tipografía ni de emojis)."""
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setPen(QPen(c, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    medio, ancho, alto = lado / 2, lado - 2, lado * 0.32
    contorno = QPainterPath()
    contorno.moveTo(1, medio)
    contorno.quadTo(medio, medio - alto * 2, lado - 1, medio)
    contorno.quadTo(medio, medio + alto * 2, 1, medio)
    p.drawPath(contorno)
    p.setBrush(c)
    p.drawEllipse(QPointF(medio, medio), lado * 0.16, lado * 0.16)
    p.end()
    return QIcon(pm)


def _celda_cliente(nombre, subtitulo=""):
    """Widget para la celda 'Cliente': avatar con la inicial + nombre (+ subtítulo)."""
    cont = QWidget()
    cont.setObjectName("celdaCliente")
    cont.setStyleSheet("QWidget#celdaCliente { background: transparent; }")
    h = QHBoxLayout(cont)
    h.setContentsMargins(8, 2, 8, 2)
    h.setSpacing(8)

    inicial = (str(nombre).strip()[:1] or "?").upper()
    avatar = QLabel(inicial)
    avatar.setFixedSize(24, 24)
    avatar.setAlignment(Qt.AlignCenter)
    avatar.setStyleSheet(
        "background-color: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe;"
        " border-radius: 5px; font-size: 11px; font-weight: 800;"
    )
    h.addWidget(avatar)

    col = QVBoxLayout()
    col.setSpacing(0)
    lbl_nombre = QLabel(str(nombre))
    lbl_nombre.setStyleSheet("font-size: 11px; font-weight: 700; color: #0f172a; background: transparent;")
    col.addWidget(lbl_nombre)
    if subtitulo:
        lbl_sub = QLabel(str(subtitulo))
        lbl_sub.setStyleSheet("font-size: 9px; color: #94a3b8; background: transparent;")
        col.addWidget(lbl_sub)
    h.addLayout(col)
    h.addStretch(1)
    return cont


class NotificationWidget(QWidget):
    """Widget de notificación tipo toast"""
    
    def __init__(self, titulo, mensaje, tipo="info", duracion=5000):
        super().__init__()
        self.duracion = duracion
        self.tipo = tipo
        
        # Configuración de la ventana
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(350)      # el alto se ajusta al texto más abajo (mínimo 80)

        # Layout principal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Contenedor principal
        container = QFrame()
        container.setObjectName("notificationContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(15, 10, 15, 10)
        
        # Título
        titulo_label = QLabel(titulo)
        titulo_label.setFont(QFont("Arial", 10, QFont.Bold))
        titulo_label.setObjectName("notificationTitle")
        container_layout.addWidget(titulo_label)
        
        # Mensaje
        mensaje_label = QLabel(mensaje)
        mensaje_label.setFont(QFont("Arial", 9))
        mensaje_label.setWordWrap(True)
        mensaje_label.setObjectName("notificationMessage")
        container_layout.addWidget(mensaje_label)
        
        layout.addWidget(container)
        # Alto según el mensaje: con 3 líneas de texto, 80 px lo cortaban.
        self.setFixedHeight(max(80, layout.totalHeightForWidth(350)))

        # Aplicar estilos según el tipo
        self.aplicar_estilos()
        
        # Timer para auto-cerrar
        self.timer = QTimer()
        self.timer.timeout.connect(self.cerrar_notificacion)
        self.timer.setSingleShot(True)
        self.timer.start(self.duracion)
        
        # Posicionar en la esquina superior derecha
        self.posicionar()
        
        # Animación de entrada
        self.animar_entrada()
    
    def aplicar_estilos(self):
        colores = {
            "info": {"bg": "#2196F3", "text": "white"},
            "success": {"bg": "#4CAF50", "text": "white"},
            "warning": {"bg": "#FF9800", "text": "white"},
            "error": {"bg": "#f44336", "text": "white"},
            "update": {"bg": "#9C27B0", "text": "white"}
        }
        
        color = colores.get(self.tipo, colores["info"])
        
        self.setStyleSheet(f"""
            #notificationContainer {{
                background-color: {color["bg"]};
                color: {color["text"]};
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            #notificationTitle {{
                color: {color["text"]};
                font-weight: bold;
            }}
            #notificationMessage {{
                color: {color["text"]};
                opacity: 0.9;
            }}
        """)
    
    def _area(self):
        """Área útil (sin barra de tareas) del monitor donde está el sistema; no el principal."""
        from src.ui import ventanas
        return ventanas.area_disponible(self)

    def posicionar(self):
        """Posicionar la notificación en la esquina superior derecha"""
        area = self._area()
        x = area.right() - self.width() - 20 + 1
        y = area.top() + 50  # Desde arriba
        self.move(x, y)

    def animar_entrada(self):
        """Animación de entrada desde la derecha"""
        area = self._area()
        y = area.top() + 50
        start_x = area.right() + 1
        end_x = area.right() - self.width() - 20 + 1

        self.move(start_x, y)

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setStartValue(QRect(start_x, y, self.width(), self.height()))
        self.animation.setEndValue(QRect(end_x, y, self.width(), self.height()))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()
    
    def cerrar_notificacion(self):
        """Cerrar la notificación con animación"""
        self.animar_salida()
    
    def animar_salida(self):
        """Animación de salida hacia la derecha"""
        start_x = self.x()
        end_x = self._area().right() + 1
        
        self.animation_out = QPropertyAnimation(self, b"geometry")
        self.animation_out.setDuration(300)
        self.animation_out.setStartValue(QRect(start_x, self.y(), self.width(), self.height()))
        self.animation_out.setEndValue(QRect(end_x, self.y(), self.width(), self.height()))
        self.animation_out.setEasingCurve(QEasingCurve.InCubic)
        self.animation_out.finished.connect(self.close)
        self.animation_out.start()
    
    def mousePressEvent(self, event):
        """Cerrar al hacer clic"""
        self.cerrar_notificacion()

class NotificationManager(QObject):
    """Gestor de notificaciones"""
    
    def __init__(self):
        super().__init__()
        self.notifications = []
        self.max_notifications = 3
    
    def show_notification(self, titulo, mensaje, tipo="info", duracion=5000):
        """Mostrar una notificación"""
        # Limitar el número de notificaciones simultáneas
        if len(self.notifications) >= self.max_notifications:
            # Cerrar la más antigua
            oldest = self.notifications.pop(0)
            if oldest and not oldest.isHidden():
                oldest.cerrar_notificacion()
        
        # Crear nueva notificación
        notification = NotificationWidget(titulo, mensaje, tipo, duracion)
        
        # Ajustar posición si hay otras notificaciones
        if self.notifications:
            y_offset = sum(n.height() + 10 for n in self.notifications)   # apiladas, según el alto de cada una
            area = notification._area()              # monitor donde está el sistema, sin barra de tareas
            x = area.right() - notification.width() - 20 + 1
            y = area.top() + 50 + y_offset
            notification.move(x, y)
        
        self.notifications.append(notification)
        notification.show()
        
        # Eliminar de la lista cuando se cierre
        notification.finished = lambda: self.notifications.remove(notification) if notification in self.notifications else None
        notification.closeEvent = lambda event: (notification.finished() if hasattr(notification, 'finished') else None, event.accept())[1]

class DatabaseSyncManager(QObject):
    """Gestor de sincronización con la base de datos con notificaciones"""
    
    # Señales para notificar cambios
    pedidos_pendientes_changed = pyqtSignal()
    pedidos_entregados_changed = pyqtSignal()
    pedido_updated = pyqtSignal(int)  # ID del pedido actualizado
    
    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_for_changes)
        
        # Estados anteriores para detectar cambios
        self.last_pendientes_hash = ""
        self.last_entregados_hash = ""
        self.last_check_time = datetime.now()
        
        # Datos anteriores para comparación detallada
        self.last_pendientes_data = []
        self.last_entregados_data = []
        
        # Flag para cambios locales (no notificar)
        self.cambios_locales = False
        self.local_changes_timer = QTimer()
        self.local_changes_timer.setSingleShot(True)
        self.local_changes_timer.timeout.connect(lambda: setattr(self, 'cambios_locales', False))
        
        # Gestor de notificaciones
        self.notification_manager = NotificationManager()
        
        # Configurar timer (verificar cada 8 segundos)
        self.timer.start(8000)
    
    def marcar_cambio_local(self):
        """Marcar que el próximo cambio es local (no notificar)"""
        self.cambios_locales = True
        # Resetear el flag después de 5 segundos por seguridad
        self.local_changes_timer.start(5000)
    
    def obtener_conexion(self):
        return _conexion()
    
    def check_for_changes(self):
        """Verificar cambios en la base de datos"""
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Verificar cambios en pedidos pendientes
            cursor.execute("""
                SELECT p.id_pedido, p.estado_pedido, p.fecha_entrega, 
                       c.nombre, p.fecha_pedido
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido IN ('pendiente', 'programado', 'en camino')
                ORDER BY p.id_pedido
            """)
            
            pendientes_data = cursor.fetchall()
            pendientes_hash = hashlib.md5(str(pendientes_data).encode()).hexdigest()
            
            if pendientes_hash != self.last_pendientes_hash and self.last_pendientes_hash != "":
                if not self.cambios_locales:
                    self.detectar_cambios_pendientes(self.last_pendientes_data, pendientes_data)
                self.last_pendientes_hash = pendientes_hash
                self.last_pendientes_data = pendientes_data.copy()
                self.pedidos_pendientes_changed.emit()
            elif self.last_pendientes_hash == "":
                self.last_pendientes_hash = pendientes_hash
                self.last_pendientes_data = pendientes_data.copy()
            
            # Verificar cambios en pedidos entregados (última semana)
            cursor.execute("""
                SELECT p.id_pedido, c.nombre, p.fecha_pedido, p.fecha_entrega
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido = 'entregado'
                AND p.fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY p.id_pedido
            """)
            
            entregados_data = cursor.fetchall()
            entregados_hash = hashlib.md5(str(entregados_data).encode()).hexdigest()
            
            if entregados_hash != self.last_entregados_hash and self.last_entregados_hash != "":
                if not self.cambios_locales:
                    self.detectar_cambios_entregados(self.last_entregados_data, entregados_data)
                self.last_entregados_hash = entregados_hash
                self.last_entregados_data = entregados_data.copy()
                self.pedidos_entregados_changed.emit()
            elif self.last_entregados_hash == "":
                self.last_entregados_hash = entregados_hash
                self.last_entregados_data = entregados_data.copy()
            
            cursor.close()
            conn.close()
            
            # Resetear flag de cambios locales después de verificar
            if self.cambios_locales:
                self.cambios_locales = False
                self.local_changes_timer.stop()
            
        except Exception as e:
            print(f"Error verificando cambios: {e}")
    
    def detectar_cambios_pendientes(self, datos_anteriores, datos_actuales):
        """Detectar qué cambios específicos ocurrieron en pedidos pendientes"""
        # Convertir a diccionarios para facilitar comparación
        anteriores_dict = {row[0]: row for row in datos_anteriores}  # id_pedido como clave
        actuales_dict = {row[0]: row for row in datos_actuales}
        
        # Pedidos nuevos
        nuevos_ids = set(actuales_dict.keys()) - set(anteriores_dict.keys())
        for id_pedido in nuevos_ids:
            pedido = actuales_dict[id_pedido]
            cliente = pedido[3]  # nombre del cliente
            self.notification_manager.show_notification(
                "🆕 Nuevo Pedido",
                f"Pedido #{id_pedido} creado para {cliente}",
                "success"
            )
        
        # Pedidos con cambios de estado
        for id_pedido in actuales_dict.keys():
            if id_pedido in anteriores_dict:
                anterior = anteriores_dict[id_pedido]
                actual = actuales_dict[id_pedido]
                
                estado_anterior = anterior[1]  # estado_pedido
                estado_actual = actual[1]
                cliente = actual[3]  # nombre del cliente
                
                if estado_anterior != estado_actual:
                    self.notification_manager.show_notification(
                        "📝 Estado Actualizado",
                        f"Pedido #{id_pedido} de {cliente}: {estado_anterior} → {estado_actual}",
                        "update"
                    )
                
                # Verificar cambios en fecha de entrega
                fecha_anterior = anterior[2]  # fecha_entrega
                fecha_actual = actual[2]
                
                if fecha_anterior != fecha_actual:
                    if fecha_actual and not fecha_anterior:
                        fecha_str = fecha_actual.strftime('%d/%m/%Y')
                        self.notification_manager.show_notification(
                            "📅 Entrega Programada",
                            f"Pedido #{id_pedido} programado para {fecha_str}",
                            "info"
                        )
        
        # Pedidos eliminados/movidos
        eliminados_ids = set(anteriores_dict.keys()) - set(actuales_dict.keys())
        for id_pedido in eliminados_ids:
            pedido_anterior = anteriores_dict[id_pedido]
            cliente = pedido_anterior[3]
            self.notification_manager.show_notification(
                "✅ Pedido Completado",
                f"Pedido #{id_pedido} de {cliente} fue entregado o eliminado",
                "success"
            )
    
    def detectar_cambios_entregados(self, datos_anteriores, datos_actuales):
        """Detectar qué cambios específicos ocurrieron en pedidos entregados"""
        anteriores_dict = {row[0]: row for row in datos_anteriores}  # id_pedido como clave
        actuales_dict = {row[0]: row for row in datos_actuales}
        
        # Nuevos pedidos entregados
        nuevos_entregados = set(actuales_dict.keys()) - set(anteriores_dict.keys())
        for id_pedido in nuevos_entregados:
            pedido = actuales_dict[id_pedido]
            cliente = pedido[1]  # nombre del cliente
            fecha_entrega = pedido[3]  # fecha_entrega
            fecha_str = fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else "Hoy"
            
            self.notification_manager.show_notification(
                "🚚 Entrega Completada",
                f"Pedido #{id_pedido} de {cliente} entregado el {fecha_str}",
                "success"
            )
    
    def force_refresh(self):
        """Refleja de inmediato un cambio hecho desde la propia app.

        Recarga los dos paneles YA (emitiendo las señales que están conectadas a
        `cargar_pedidos_*`) y resincroniza el baseline de detección de cambios
        para que el poll de 8 s no lo vuelva a disparar como si fuera externo.

        Nota: NO alcanza con blanquear los hashes + `check_for_changes()`, porque
        con el hash en "" ese método entra por la rama 'primer arranque', guarda
        el hash nuevo y **no emite** ninguna señal → los paneles quedaban
        congelados en el estado previo (p. ej. un pedido entregado seguía
        apareciendo en 'Pendientes')."""
        self.cambios_locales = True   # es un cambio nuestro: no auto-notificar
        self.last_pendientes_hash = ""
        self.last_entregados_hash = ""
        self.check_for_changes()      # recomputa y guarda el baseline nuevo
        self.pedidos_pendientes_changed.emit()
        self.pedidos_entregados_changed.emit()

class ImportThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self):
        super().__init__()
        self.ruta_dbf = "D:\\tiempo\\vtiempoges\\GESTION\\MANA2014"
    
    def run(self):
        try:
            self.importar_datos()
            self.finished.emit(True, "Importación completada exitosamente")
        except Exception as e:
            self.finished.emit(False, f"Error en la importación: {str(e)}")
    
    def obtener_conexion(self):
        return _conexion()
    
    def importar_datos(self):
        conn = self.obtener_conexion()
        cursor = conn.cursor()
        
        try:
            # Importar clientes
            self.status.emit("Importando clientes...")
            ruta_clientes = os.path.join(self.ruta_dbf, "ctaclien.dbf")
            
            if os.path.exists(ruta_clientes):
                # Primero, agregar las nuevas columnas si no existen
                try:
                    cursor.execute("ALTER TABLE Cliente ADD COLUMN IF NOT EXISTS cuit VARCHAR(15)")
                    cursor.execute("ALTER TABLE Cliente ADD COLUMN IF NOT EXISTS localidad VARCHAR(100)")
                    cursor.execute("ALTER TABLE Cliente ADD COLUMN IF NOT EXISTS tasacero VARCHAR(1)")
                    conn.commit()
                except:
                    pass
                
                table = DBF(ruta_clientes, encoding=config.DBF_ENCODING)
                total_clientes = len(table)
                
                for i, record in enumerate(table):
                    try:
                        # Construir dirección completa
                        direccion_completa = ""
                        if record.get('CDIREC'):
                            direccion_completa = record['CDIREC']
                        if record.get('LOCALIDAD'):
                            if direccion_completa:
                                direccion_completa += f", {record['LOCALIDAD']}"
                            else:
                                direccion_completa = record['LOCALIDAD']
                        
                        cursor.execute("""
                            INSERT INTO Cliente (id_cliente, nombre, direccion, telefono, cuit, localidad, tasacero)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id_cliente) DO UPDATE SET
                                nombre = EXCLUDED.nombre,
                                direccion = EXCLUDED.direccion,
                                telefono = EXCLUDED.telefono,
                                cuit = EXCLUDED.cuit,
                                localidad = EXCLUDED.localidad,
                                tasacero = EXCLUDED.tasacero
                        """, (
                            record.get('CNUMERO'),
                            record.get('CNOMBRE', '').strip() if record.get('CNOMBRE') else '',
                            direccion_completa.strip(),
                            record.get('TELEFONO', '').strip() if record.get('TELEFONO') else '',
                            record.get('CUIT', '').strip() if record.get('CUIT') else '',
                            record.get('LOCALIDAD', '').strip() if record.get('LOCALIDAD') else '',
                            record.get('TASACERO', '') if record.get('TASACERO') else ''
                        ))
                        
                        progress = int((i + 1) / total_clientes * 50)
                        self.progress.emit(progress)
                        
                    except Exception as e:
                        print(f"Error procesando cliente {record}: {e}")
                        continue
                
                conn.commit()
                self.status.emit(f"Importados {total_clientes} clientes")
            
            # Importar productos
            self.status.emit("Importando productos...")
            ruta_productos = os.path.join(self.ruta_dbf, "abmartic.dbf")
            
            if os.path.exists(ruta_productos):
                # Agregar columna stock si no existe
                try:
                    cursor.execute("ALTER TABLE Producto ADD COLUMN IF NOT EXISTS stock_disponible INTEGER DEFAULT 0")
                    conn.commit()
                except:
                    pass
                
                table = DBF(ruta_productos, encoding=config.DBF_ENCODING)
                total_productos = len(table)
                
                for i, record in enumerate(table):
                    try:
                        cursor.execute("""
                            INSERT INTO Producto (id_producto, nombre, stock_disponible)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (id_producto) DO UPDATE SET
                                nombre = EXCLUDED.nombre
                        """, (
                            record.get('CODART', '').strip() if record.get('CODART') else '',
                            record.get('DESC', '').strip() if record.get('DESC') else '',
                            0  # Stock inicial en 0
                        ))
                        
                        progress = 50 + int((i + 1) / total_productos * 50)
                        self.progress.emit(progress)
                        
                    except Exception as e:
                        print(f"Error procesando producto {record}: {e}")
                        continue
                
                conn.commit()
                self.status.emit(f"Importados {total_productos} productos")
            
            self.progress.emit(100)
            
        finally:
            cursor.close()
            conn.close()

class DialogoNuevoPedido(QDialog):
    # Señal para notificar cuando se crea un nuevo pedido
    pedido_creado = pyqtSignal(int)  # ID del nuevo pedido

    _NP_NUM, _NP_ID, _NP_DESC, _NP_CANT, _NP_DEL = range(5)

    def __init__(self, parent=None, sync_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Pedido")
        self.resize(820, 620)
        self.setMinimumSize(680, 520)
        self.pedido_fue_creado = False
        self.sync_manager = sync_manager
        self.todos_los_clientes = []
        self.todos_los_productos = []

        self.setStyleSheet(_QSS_DIALOGO_PEDIDO)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(10)

        enc = QHBoxLayout()
        titulo = QLabel("Nuevo Pedido")
        titulo.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        enc.addWidget(titulo)
        chip = QLabel("Borrador")
        chip.setStyleSheet(
            "background-color: #fffbeb; color: #92400e; border: 1px solid #fde68a;"
            " border-radius: 9px; padding: 1px 10px; font-size: 10px; font-weight: 700;"
        )
        enc.addWidget(chip)
        enc.addStretch(1)
        raiz.addLayout(enc)

        # ── Sección 1: Información del pedido ───────────────────────────────
        card_info = QFrame()
        card_info.setObjectName("card")
        cil = QVBoxLayout(card_info)
        cil.setContentsMargins(14, 10, 14, 12)
        cil.setSpacing(8)
        cil.addWidget(self._subtitulo("Información del Pedido"))

        grid = QHBoxLayout()
        grid.setSpacing(10)
        col_cli = QVBoxLayout()
        col_cli.setSpacing(3)
        col_cli.addWidget(self._label_campo("Cliente *"))
        fila_cli = QHBoxLayout()
        fila_cli.setSpacing(6)
        self.line_cliente = QLineEdit()
        self.line_cliente.setPlaceholderText("Escriba para buscar cliente…")
        self.line_cliente.textChanged.connect(self.filtrar_clientes)
        fila_cli.addWidget(self.line_cliente, 1)
        self.combo_cliente = QComboBox()
        self.combo_cliente.currentIndexChanged.connect(self._actualizar_info_cliente)
        fila_cli.addWidget(self.combo_cliente, 1)
        col_cli.addLayout(fila_cli)
        self.info_cliente = QLabel("")
        self.info_cliente.setStyleSheet("font-size: 10px; color: #64748b;")
        col_cli.addWidget(self.info_cliente)
        grid.addLayout(col_cli, 3)

        col_fecha = QVBoxLayout()
        col_fecha.setSpacing(3)
        col_fecha.addWidget(self._label_campo("Fecha de Pedido *"))
        self.date_pedido = QDateEdit()
        self.date_pedido.setDate(QDate.currentDate())
        self.date_pedido.setCalendarPopup(True)
        self.date_pedido.setDisplayFormat("dd/MM/yyyy")
        col_fecha.addWidget(self.date_pedido)
        col_fecha.addStretch(1)
        grid.addLayout(col_fecha, 1)
        cil.addLayout(grid)
        raiz.addWidget(card_info)

        self.cargar_clientes()

        # ── Sección 2: Productos ───────────────────────────────────────────
        card_prod = QFrame()
        card_prod.setObjectName("card")
        cpl = QVBoxLayout(card_prod)
        cpl.setContentsMargins(14, 10, 14, 12)
        cpl.setSpacing(8)

        fila_sub = QHBoxLayout()
        fila_sub.addWidget(self._subtitulo("Productos del Pedido"))
        fila_sub.addStretch(1)
        self._badge_np = QLabel("0 artículos en orden")
        self._badge_np.setStyleSheet(
            "font-size: 10px; font-family: Consolas; color: #475569; background-color: #f1f5f9;"
            " border: 1px solid #e2e8f0; border-radius: 5px; padding: 1px 7px;"
        )
        fila_sub.addWidget(self._badge_np)
        cpl.addLayout(fila_sub)

        agregar = QHBoxLayout()
        agregar.setSpacing(6)
        self.line_producto = QLineEdit()
        self.line_producto.setPlaceholderText("Buscar producto…")
        self.line_producto.textChanged.connect(self.filtrar_productos)
        agregar.addWidget(self.line_producto, 2)
        self.combo_producto = QComboBox()
        agregar.addWidget(self.combo_producto, 3)
        self.spin_cantidad = QSpinBox()
        self.spin_cantidad.setMinimum(1)
        self.spin_cantidad.setMaximum(9999)
        self.spin_cantidad.setValue(1)
        self.spin_cantidad.setAlignment(Qt.AlignCenter)
        self.spin_cantidad.setMaximumWidth(80)
        agregar.addWidget(self.spin_cantidad)
        btn_agregar = QPushButton("＋ Agregar")
        btn_agregar.setObjectName("btnOk")
        btn_agregar.clicked.connect(self.agregar_producto)
        agregar.addWidget(btn_agregar)
        cpl.addLayout(agregar)
        self.cargar_productos()

        self.tabla_productos = QTableWidget()
        self.tabla_productos.setColumnCount(5)
        self.tabla_productos.setHorizontalHeaderLabels(["#", "ID Producto", "Descripción", "Cantidad", ""])
        self.tabla_productos.verticalHeader().setVisible(False)
        self.tabla_productos.verticalHeader().setDefaultSectionSize(28)
        self.tabla_productos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_productos.setShowGrid(False)
        self.tabla_productos.setAlternatingRowColors(True)
        h = self.tabla_productos.horizontalHeader()
        h.setStretchLastSection(False)
        for i, w in ((0, 36), (1, 110), (3, 90), (4, 42)):
            h.setSectionResizeMode(i, QHeaderView.Fixed)
            self.tabla_productos.setColumnWidth(i, w)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        cpl.addWidget(self.tabla_productos, 1)

        self._resumen_np = QLabel("Líneas activas: 0   •   Total bultos: 0 un.")
        self._resumen_np.setStyleSheet("font-size: 10px; color: #64748b; padding-top: 2px;")
        cpl.addWidget(self._resumen_np)
        raiz.addWidget(card_prod, 1)

        # ── acciones ───────────────────────────────────────────────────────
        acc = QHBoxLayout()
        acc.addStretch(1)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("btnNeutral")
        btn_cancelar.clicked.connect(self.reject)
        acc.addWidget(btn_cancelar)
        btn_crear = QPushButton("✓ Crear Pedido")
        btn_crear.setObjectName("btnOk")
        btn_crear.clicked.connect(self.crear_pedido)
        acc.addWidget(btn_crear)
        raiz.addLayout(acc)

    # ── helpers de UI ──────────────────────────────────────────────────────
    @staticmethod
    def _subtitulo(txt):
        lbl = QLabel(txt.upper())
        lbl.setStyleSheet("font-size: 10px; font-weight: 800; color: #334155;")
        return lbl

    @staticmethod
    def _label_campo(txt):
        lbl = QLabel(txt)
        lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        return lbl

    def obtener_conexion(self):
        return _conexion()

    def cargar_clientes(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id_cliente, nombre, cuit FROM Cliente ORDER BY nombre")
            self.todos_los_clientes = cursor.fetchall()
            cursor.close()
            conn.close()
            self._poblar_combo_clientes(self.todos_los_clientes)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar clientes: {str(e)}")

    def _poblar_combo_clientes(self, clientes):
        self.combo_cliente.blockSignals(True)
        self.combo_cliente.clear()
        for id_cliente, nombre, cuit in clientes:
            self.combo_cliente.addItem(f"{nombre} (ID: {id_cliente})", (id_cliente, cuit))
        self.combo_cliente.blockSignals(False)
        self._actualizar_info_cliente()

    def _actualizar_info_cliente(self):
        data = self.combo_cliente.currentData()
        if data and data[1]:
            self.info_cliente.setText(f"CUIT: {data[1]}")
        else:
            self.info_cliente.setText("")

    def filtrar_clientes(self):
        texto = self.line_cliente.text().lower()
        self._poblar_combo_clientes(
            [c for c in self.todos_los_clientes if texto in str(c[1]).lower()])

    def cargar_productos(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id_producto, nombre FROM Producto ORDER BY nombre")
            self.todos_los_productos = cursor.fetchall()
            cursor.close()
            conn.close()
            self._poblar_combo_productos(self.todos_los_productos)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar productos: {str(e)}")

    def _poblar_combo_productos(self, productos):
        self.combo_producto.clear()
        for id_producto, nombre in productos:
            self.combo_producto.addItem(f"{id_producto} — {nombre}", (id_producto, nombre))

    def filtrar_productos(self):
        texto = self.line_producto.text().lower()
        self._poblar_combo_productos(
            [p for p in self.todos_los_productos
             if texto in str(p[1]).lower() or texto in str(p[0]).lower()])

    def agregar_producto(self):
        data = self.combo_producto.currentData()
        if data is None:
            QMessageBox.warning(self, "Advertencia", "Seleccione un producto")
            return
        id_producto, nombre_producto = data
        cantidad = self.spin_cantidad.value()

        for i in range(self.tabla_productos.rowCount()):
            if self.tabla_productos.item(i, self._NP_ID).text() == id_producto:
                QMessageBox.warning(self, "Advertencia", "El producto ya está en el pedido")
                return

        fila = self.tabla_productos.rowCount()
        self.tabla_productos.insertRow(fila)
        self.tabla_productos.setItem(fila, self._NP_NUM, QTableWidgetItem(""))
        it_id = QTableWidgetItem(str(id_producto))
        it_id.setFont(QFont("Consolas", 8))
        it_id.setForeground(QColor("#0369a1"))
        self.tabla_productos.setItem(fila, self._NP_ID, it_id)
        self.tabla_productos.setItem(fila, self._NP_DESC, QTableWidgetItem(str(nombre_producto)))
        it_cant = QTableWidgetItem(str(cantidad))
        it_cant.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        it_cant.setFont(QFont("Consolas", 8, QFont.Bold))
        self.tabla_productos.setItem(fila, self._NP_CANT, it_cant)

        btn_eliminar = QPushButton("✕")
        btn_eliminar.setObjectName("btnDelIcon")
        btn_eliminar.setFixedWidth(28)
        btn_eliminar.clicked.connect(self._quitar_fila_producto)
        self.tabla_productos.setCellWidget(fila, self._NP_DEL, btn_eliminar)

        self.spin_cantidad.setValue(1)
        self._actualizar_resumen_productos()

    def _quitar_fila_producto(self):
        btn = self.sender()
        for i in range(self.tabla_productos.rowCount()):
            if self.tabla_productos.cellWidget(i, self._NP_DEL) is btn:
                self.tabla_productos.removeRow(i)
                break
        self._actualizar_resumen_productos()

    def _actualizar_resumen_productos(self):
        n = self.tabla_productos.rowCount()
        total = 0
        for i in range(n):
            it_n = self.tabla_productos.item(i, self._NP_NUM)
            if it_n is not None:
                it_n.setText(str(i + 1))
                it_n.setTextAlignment(Qt.AlignCenter)
                it_n.setForeground(QColor("#94a3b8"))
            try:
                total += int(self.tabla_productos.item(i, self._NP_CANT).text())
            except (AttributeError, ValueError):
                pass
        self._badge_np.setText(f"{n} artículo{'s' if n != 1 else ''} en orden")
        self._resumen_np.setText(f"Líneas activas: {n}   •   Total bultos: {total} un.")

    def crear_pedido(self):
        data_cliente = self.combo_cliente.currentData()
        if data_cliente is None:
            QMessageBox.warning(self, "Advertencia", "Seleccione un cliente")
            return

        if self.tabla_productos.rowCount() == 0:
            QMessageBox.warning(self, "Advertencia", "Agregue al menos un producto")
            return

        try:
            # Marcar como cambio local antes de crear el pedido
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()

            conn = self.obtener_conexion()
            cursor = conn.cursor()

            # Crear el pedido
            cursor.execute("""
                INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido)
                VALUES (%s, %s, 'pendiente')
                RETURNING id_pedido
            """, (
                data_cliente[0],
                self.date_pedido.date().toPyDate()
            ))

            id_pedido = cursor.fetchone()[0]

            # Agregar productos al pedido
            for i in range(self.tabla_productos.rowCount()):
                id_producto = self.tabla_productos.item(i, self._NP_ID).text()
                cantidad = int(self.tabla_productos.item(i, self._NP_CANT).text())
                
                cursor.execute("""
                    INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario)
                    VALUES (%s, %s, %s, %s)
                """, (id_pedido, id_producto, cantidad, 0.00))  # Precio 0 por ahora
            
            conn.commit()
            cursor.close()
            conn.close()
            
            self.pedido_fue_creado = True
            
            # Emitir señal de pedido creado
            self.pedido_creado.emit(id_pedido)
            
            # Forzar actualización del sync manager
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
            QMessageBox.information(self, "Éxito", f"Pedido #{id_pedido} creado exitosamente!")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al crear el pedido: {str(e)}")
    
class VentanaDetallePedido(QDialog):
    # Señales para notificar cambios
    pedido_updated = pyqtSignal(int)
    pedido_deleted = pyqtSignal(int)
    
    def __init__(self, id_pedido, parent=None, sync_manager=None):
        super().__init__(parent)
        self.id_pedido = id_pedido
        self.parent_window = parent
        self.sync_manager = sync_manager
        self.setWindowTitle(f"Detalles del Pedido #{id_pedido}")
        self.resize(1040, 720)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(_QSS_DIALOGO_PEDIDO)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(10)

        # ── encabezado: título + estado ────────────────────────────────────
        enc = QHBoxLayout()
        titulo = QLabel(f"Detalles del Pedido #{id_pedido}")
        titulo.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        enc.addWidget(titulo)
        self._pill_header = _pill_estado("")
        enc.addWidget(self._pill_header)
        enc.addStretch(1)
        raiz.addLayout(enc)

        # Arriba: a la izquierda KPIs + programar entrega, a la derecha el mapita del cliente.
        superior = QHBoxLayout()
        superior.setSpacing(10)
        izquierda = QVBoxLayout()
        izquierda.setSpacing(10)

        # ── KPIs ───────────────────────────────────────────────────────────
        kpis = QHBoxLayout()
        kpis.setSpacing(8)
        self._kpi_cliente, self._kpi_cliente_sub, c1 = self._kpi("Cliente", "#0f172a")
        self._kpi_fpedido, _, c2 = self._kpi("Fecha de Pedido", "#0f172a")
        self._kpi_estado, self._kpi_estado_sub, c3 = self._kpi("Estado Actual", "#b45309")
        self._kpi_fentrega, self._kpi_fentrega_sub, c4 = self._kpi("Fecha de Entrega", "#be123c")
        for c in (c1, c2, c3, c4):
            kpis.addWidget(c)
        izquierda.addLayout(kpis)

        # ── programar entrega ──────────────────────────────────────────────
        prog = QFrame()
        prog.setObjectName("card")
        pl = QHBoxLayout(prog)
        pl.setContentsMargins(12, 8, 12, 8)
        pl.setSpacing(8)
        lbl_pe = QLabel("PROGRAMAR ENTREGA")
        lbl_pe.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b;")
        pl.addWidget(lbl_pe)
        self.date_entrega = QDateEdit()
        self.date_entrega.setDate(QDate.currentDate())
        self.date_entrega.setCalendarPopup(True)
        self.date_entrega.setDisplayFormat("dd/MM/yyyy")
        self.date_entrega.setMaximumWidth(140)
        pl.addWidget(self.date_entrega)
        self.btn_programar = QPushButton("Programar")
        self.btn_programar.setObjectName("btnOk")
        self.btn_programar.clicked.connect(self.programar_entrega)
        pl.addWidget(self.btn_programar)
        self.btn_en_camino = QPushButton("En Camino")
        self.btn_en_camino.setObjectName("btnInfo")
        self.btn_en_camino.clicked.connect(self.marcar_en_camino)
        pl.addWidget(self.btn_en_camino)
        pl.addStretch(1)
        izquierda.addWidget(prog)

        superior.addLayout(izquierda, 1)
        self.tarjeta_ubicacion = TarjetaUbicacion(self.obtener_conexion)
        superior.addWidget(self.tarjeta_ubicacion)
        raiz.addLayout(superior)

        # ── productos del pedido ───────────────────────────────────────────
        card_prod = QFrame()
        card_prod.setObjectName("card")
        cpl = QVBoxLayout(card_prod)
        cpl.setContentsMargins(0, 0, 0, 0)
        cpl.setSpacing(0)
        cab_prod = self._cabecera_card("Productos del Pedido")
        self._badge_prod = cab_prod[1]
        cpl.addWidget(cab_prod[0])

        # Agregar productos sobre la marcha (solo mientras el pedido no esté entregado)
        self._barra_agregar = QFrame()
        ba = QHBoxLayout(self._barra_agregar)
        ba.setContentsMargins(12, 8, 12, 8)
        ba.setSpacing(6)
        self.line_producto = QLineEdit()
        self.line_producto.setPlaceholderText("Buscar producto para agregar…")
        self.line_producto.textChanged.connect(self.filtrar_productos)
        ba.addWidget(self.line_producto, 2)
        self.combo_producto = QComboBox()
        ba.addWidget(self.combo_producto, 3)
        self.spin_cantidad = QSpinBox()
        self.spin_cantidad.setMinimum(1)
        self.spin_cantidad.setMaximum(9999)
        self.spin_cantidad.setAlignment(Qt.AlignCenter)
        self.spin_cantidad.setMaximumWidth(80)
        ba.addWidget(self.spin_cantidad)
        btn_agregar = QPushButton("＋ Agregar")
        btn_agregar.setObjectName("btnOk")
        btn_agregar.clicked.connect(self.agregar_producto)
        ba.addWidget(btn_agregar)
        cpl.addWidget(self._barra_agregar)
        self.todos_los_productos = []
        self._cargar_catalogo_productos()

        self.tabla_productos = QTableWidget()
        self.tabla_productos.setColumnCount(7)
        self.tabla_productos.setHorizontalHeaderLabels(
            ["#", "SKU", "Descripción", "Solicitado", "Entregado", "A Entregar", "Estado"])
        self._preparar_tabla_detalle(self.tabla_productos, [40, 90, None, 90, 90, 90, 110])
        cpl.addWidget(self.tabla_productos)
        raiz.addWidget(card_prod, 1)

        # ── entrega parcial ────────────────────────────────────────────────
        card_par = QFrame()
        card_par.setObjectName("card")
        cparl = QVBoxLayout(card_par)
        cparl.setContentsMargins(0, 0, 0, 0)
        cparl.setSpacing(0)
        cab_par = self._cabecera_card("Entrega Parcial / Remisión Directa")
        cparl.addWidget(cab_par[0])
        self.tabla_entrega_parcial = QTableWidget()
        self.tabla_entrega_parcial.setColumnCount(4)
        self.tabla_entrega_parcial.setHorizontalHeaderLabels(
            ["SKU", "Descripción", "Pendiente", "Cant. a Entregar"])
        self._preparar_tabla_detalle(self.tabla_entrega_parcial, [110, None, 100, 150])
        self.tabla_entrega_parcial.setMaximumHeight(180)
        cparl.addWidget(self.tabla_entrega_parcial)
        raiz.addWidget(card_par)

        # ── acciones ───────────────────────────────────────────────────────
        acc = QHBoxLayout()
        self.btn_entrega_parcial = QPushButton("Entrega Parcial")
        self.btn_entrega_parcial.setObjectName("btnOkOutline")
        self.btn_entrega_parcial.clicked.connect(self.realizar_entrega_parcial)
        acc.addWidget(self.btn_entrega_parcial)
        self.btn_entrega_completa = QPushButton("Entrega Completa")
        self.btn_entrega_completa.setObjectName("btnOk")
        self.btn_entrega_completa.clicked.connect(self.realizar_entrega_completa)
        acc.addWidget(self.btn_entrega_completa)
        acc.addStretch(1)
        self.btn_eliminar_pedido = QPushButton("Eliminar Pedido")
        self.btn_eliminar_pedido.setObjectName("btnDanger")
        self.btn_eliminar_pedido.clicked.connect(self.eliminar_pedido)
        acc.addWidget(self.btn_eliminar_pedido)
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("btnNeutral")
        btn_cerrar.clicked.connect(self.close)
        acc.addWidget(btn_cerrar)
        raiz.addLayout(acc)

        self.cargar_datos_pedido()
        self.cargar_productos_pedido()
        self.cargar_tabla_entrega_parcial()

    def _kpi(self, titulo, color_valor):
        card = QFrame()
        card.setObjectName("kpi")
        card.setMinimumWidth(120)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 7, 12, 8)
        v.setSpacing(1)
        t = QLabel(titulo.upper())
        t.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; background: transparent; border: none;")
        val = QLabel("—")
        val.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {color_valor}; background: transparent; border: none;")
        sub = QLabel("")
        sub.setStyleSheet("font-size: 9px; color: #94a3b8; background: transparent; border: none;")
        v.addWidget(t)
        v.addWidget(val)
        v.addWidget(sub)
        return val, sub, card

    def _cabecera_card(self, titulo):
        cab = QFrame()
        cab.setObjectName("cardHeader")
        cab.setStyleSheet("QFrame#cardHeader { background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;"
                          " border-top-left-radius: 8px; border-top-right-radius: 8px; }")
        h = QHBoxLayout(cab)
        h.setContentsMargins(12, 6, 12, 6)
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet("font-size: 10px; font-weight: 800; color: #334155; background: transparent;")
        h.addWidget(lbl)
        badge = QLabel("")
        badge.setStyleSheet("font-size: 10px; color: #64748b; background: transparent;")
        h.addWidget(badge)
        h.addStretch(1)
        return cab, badge

    def _preparar_tabla_detalle(self, tabla, anchos):
        tabla.verticalHeader().setVisible(False)
        tabla.verticalHeader().setDefaultSectionSize(30)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setSelectionBehavior(QTableWidget.SelectRows)
        tabla.setShowGrid(False)
        tabla.setAlternatingRowColors(True)
        header = tabla.horizontalHeader()
        header.setStretchLastSection(False)
        for i, w in enumerate(anchos):
            if w is None:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(i, QHeaderView.Fixed)
                tabla.setColumnWidth(i, w)

    def obtener_conexion(self):
        return _conexion()

    def cargar_datos_pedido(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT c.nombre, c.cuit, p.fecha_pedido, p.estado_pedido, p.fecha_entrega,
                       c.id_cliente, c.ubicacion_maps, c.ubicacion_lat, c.ubicacion_lng
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.id_pedido = %s
            """, (self.id_pedido,))

            resultado = cursor.fetchone()
            cursor.close()
            conn.close()
            if not resultado:
                return
            (nombre_cliente, cuit, fecha_pedido, estado, fecha_entrega,
             id_cliente, ubicacion, ubicacion_lat, ubicacion_lng) = resultado

            self.tarjeta_ubicacion.mostrar(id_cliente, ubicacion, ubicacion_lat, ubicacion_lng)
            self._kpi_cliente.setText(str(nombre_cliente))
            self._kpi_cliente_sub.setText(f"CUIT {cuit}" if cuit else "")
            self._kpi_fpedido.setText(fecha_pedido.strftime('%d/%m/%Y') if fecha_pedido else "—")

            self._barra_agregar.setVisible(str(estado).lower() != "entregado")

            bg, fg, _ = _ESTADO_PILL.get(str(estado).lower(), _ESTADO_PILL_DEFECTO)
            self._kpi_estado.setText(str(estado).upper())
            self._kpi_estado.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {fg}; background: transparent; border: none;")
            self._pill_header.setText(str(estado).capitalize())
            self._pill_header.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border-radius: 9px; padding: 1px 10px;"
                " font-size: 10px; font-weight: 700;"
            )

            if fecha_entrega:
                self._kpi_fentrega.setText(fecha_entrega.strftime('%d/%m/%Y'))
                self._kpi_fentrega.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a; background: transparent; border: none;")
                self._kpi_fentrega_sub.setText("Programada" if str(estado).lower() != "entregado" else "Entregado")
                self.date_entrega.setDate(fecha_entrega)
            else:
                self._kpi_fentrega.setText("Sin programar")
                self._kpi_fentrega.setStyleSheet("font-size: 13px; font-weight: 800; color: #be123c; background: transparent; border: none;")
                self._kpi_fentrega_sub.setText("Acción requerida abajo")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los datos: {str(e)}")

    def _cargar_catalogo_productos(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id_producto, nombre FROM Producto ORDER BY nombre")
            self.todos_los_productos = cursor.fetchall()
            cursor.close()
            conn.close()
            self.filtrar_productos()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar productos: {str(e)}")

    def filtrar_productos(self):
        texto = self.line_producto.text().lower()
        self.combo_producto.clear()
        for id_producto, nombre in self.todos_los_productos:
            if texto in str(nombre).lower() or texto in str(id_producto).lower():
                self.combo_producto.addItem(f"{id_producto} — {nombre}", (id_producto, nombre))

    def agregar_producto(self):
        """Suma un producto al pedido ya creado; si ya estaba, incrementa la cantidad."""
        data = self.combo_producto.currentData()
        if data is None:
            QMessageBox.warning(self, "Advertencia", "Seleccione un producto")
            return
        id_producto, nombre = data
        cantidad = self.spin_cantidad.value()

        try:
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()

            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT estado_pedido FROM Pedido WHERE id_pedido = %s", (self.id_pedido,))
            fila = cursor.fetchone()
            if not fila or str(fila[0]).lower() == "entregado":
                cursor.close()
                conn.close()
                QMessageBox.warning(self, "Advertencia",
                                    "El pedido ya fue entregado: no se pueden agregar productos.")
                self.cargar_datos_pedido()
                return

            cursor.execute("""
                SELECT id_detalle FROM DetallePedido
                WHERE id_pedido = %s AND id_producto = %s
                ORDER BY id_detalle LIMIT 1
            """, (self.id_pedido, id_producto))
            existente = cursor.fetchone()
            if existente:
                cursor.execute("UPDATE DetallePedido SET cantidad = cantidad + %s WHERE id_detalle = %s",
                               (cantidad, existente[0]))
            else:
                cursor.execute("""
                    INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario)
                    VALUES (%s, %s, %s, %s)
                """, (self.id_pedido, id_producto, cantidad, 0.00))
            conn.commit()
            cursor.close()
            conn.close()

            self.spin_cantidad.setValue(1)
            self.cargar_datos_pedido()
            self.cargar_productos_pedido()
            self.cargar_tabla_entrega_parcial()

            self.pedido_updated.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo agregar el producto: {str(e)}")

    def cargar_productos_pedido(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT dp.id_producto, p.nombre, dp.cantidad, dp.cantidad_entregada, dp.estado_entrega
                FROM DetallePedido dp
                JOIN Producto p ON dp.id_producto = p.id_producto
                WHERE dp.id_pedido = %s
                ORDER BY dp.id_detalle
            """, (self.id_pedido,))

            productos = cursor.fetchall()
            cursor.close()
            conn.close()

            self.tabla_productos.setRowCount(len(productos))
            self._badge_prod.setText(f"{len(productos)} artículo{'s' if len(productos) != 1 else ''}")
            mono = QFont("Consolas", 8)
            for i, (id_producto, nombre, cantidad, entregada, estado_entrega) in enumerate(productos):
                it_n = QTableWidgetItem(str(i + 1))
                it_n.setTextAlignment(Qt.AlignCenter)
                it_n.setForeground(QColor("#94a3b8"))
                self.tabla_productos.setItem(i, 0, it_n)

                it_sku = QTableWidgetItem(str(id_producto))
                it_sku.setFont(mono)
                it_sku.setForeground(QColor("#0369a1"))
                self.tabla_productos.setItem(i, 1, it_sku)
                self.tabla_productos.setItem(i, 2, QTableWidgetItem(str(nombre)))

                for col, val, color in ((3, cantidad, "#475569"), (4, entregada, "#94a3b8")):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    it.setFont(mono)
                    it.setForeground(QColor(color))
                    self.tabla_productos.setItem(i, col, it)

                it_ae = QTableWidgetItem(str(cantidad - entregada))
                it_ae.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it_ae.setFont(QFont("Consolas", 8, QFont.Bold))
                it_ae.setForeground(QColor("#047857"))
                self.tabla_productos.setItem(i, 5, it_ae)

                self.tabla_productos.setCellWidget(i, 6, _centrar(_pill_estado(estado_entrega)))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los productos: {str(e)}")

    def cargar_tabla_entrega_parcial(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT dp.id_producto, p.nombre, dp.cantidad, dp.cantidad_entregada
                FROM DetallePedido dp
                JOIN Producto p ON dp.id_producto = p.id_producto
                WHERE dp.id_pedido = %s AND dp.cantidad_entregada < dp.cantidad
                ORDER BY dp.id_detalle
            """, (self.id_pedido,))

            productos_pendientes = cursor.fetchall()
            cursor.close()
            conn.close()

            self.tabla_entrega_parcial.setRowCount(len(productos_pendientes))
            for i, (id_producto, nombre, cantidad, cantidad_entregada) in enumerate(productos_pendientes):
                pendiente = cantidad - cantidad_entregada
                it_sku = QTableWidgetItem(str(id_producto))
                it_sku.setFont(QFont("Consolas", 8))
                it_sku.setForeground(QColor("#0369a1"))
                self.tabla_entrega_parcial.setItem(i, 0, it_sku)
                self.tabla_entrega_parcial.setItem(i, 1, QTableWidgetItem(str(nombre)))
                it_p = QTableWidgetItem(str(pendiente))
                it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it_p.setForeground(QColor("#b45309"))
                it_p.setFont(QFont("Consolas", 8, QFont.Bold))
                self.tabla_entrega_parcial.setItem(i, 2, it_p)

                spin_entregar = QSpinBox()
                spin_entregar.setMinimum(0)
                spin_entregar.setMaximum(pendiente)
                spin_entregar.setValue(pendiente)
                spin_entregar.setAlignment(Qt.AlignCenter)
                self.tabla_entrega_parcial.setCellWidget(i, 3, spin_entregar)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los productos pendientes: {str(e)}")
    
    def programar_entrega(self):
        fecha_entrega = self.date_entrega.date().toPyDate()
        
        try:
            # Marcar como cambio local
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()
            
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE Pedido 
                SET estado_pedido = 'programado', fecha_entrega = %s
                WHERE id_pedido = %s
            """, (fecha_entrega, self.id_pedido))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "Éxito", "Pedido programado exitosamente!")
            self.cargar_datos_pedido()
            
            # Emitir señal y forzar actualización
            self.pedido_updated.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo programar el pedido: {str(e)}")
    
    def marcar_en_camino(self):
        try:
            # Marcar como cambio local
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()
            
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE Pedido 
                SET estado_pedido = 'en camino'
                WHERE id_pedido = %s
            """, (self.id_pedido,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "Éxito", "Pedido marcado como En Camino!")
            self.cargar_datos_pedido()
            
            # Emitir señal y forzar actualización
            self.pedido_updated.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo actualizar el pedido: {str(e)}")
    
    def realizar_entrega_parcial(self):
        try:
            # Marcar como cambio local
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()
            
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            productos_entregados = []
            
            # Procesar cada producto de la tabla de entrega parcial
            for i in range(self.tabla_entrega_parcial.rowCount()):
                id_producto = self.tabla_entrega_parcial.item(i, 0).text()
                cantidad_a_entregar = self.tabla_entrega_parcial.cellWidget(i, 3).value()
                
                if cantidad_a_entregar > 0:
                    cursor.execute("""
                        UPDATE DetallePedido
                        SET cantidad_entregada = cantidad_entregada + %s
                        WHERE id_pedido = %s AND id_producto = %s
                    """, (cantidad_a_entregar, self.id_pedido, id_producto))
                    
                    productos_entregados.append((id_producto, cantidad_a_entregar))
            
            # Verificar si el pedido está completamente entregado
            cursor.execute("""
                SELECT COUNT(*) FROM DetallePedido
                WHERE id_pedido = %s AND cantidad_entregada < cantidad
            """, (self.id_pedido,))
            
            productos_pendientes = cursor.fetchone()[0]
            
            # Actualizar estado del pedido si está completo. La fecha de entrega
            # es la fecha real en que se terminó de entregar (hoy), no una fecha
            # programada vieja — si no, el panel "Entregados (última semana)" lo
            # filtraba y el pedido desaparecía de ambos paneles.
            if productos_pendientes == 0:
                fecha_actual = date.today()
                cursor.execute("""
                    UPDATE Pedido
                    SET estado_pedido = 'entregado',
                        fecha_entrega = %s
                    WHERE id_pedido = %s
                """, (fecha_actual, self.id_pedido))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            if productos_entregados:
                mensaje = f"Entrega parcial realizada!\nProductos entregados: {len(productos_entregados)}"
                QMessageBox.information(self, "Éxito", mensaje)
            else:
                QMessageBox.information(self, "Información", "No hay productos para entregar")
            
            # Recargar datos
            self.cargar_datos_pedido()
            self.cargar_productos_pedido()
            self.cargar_tabla_entrega_parcial()
            
            # Emitir señal y forzar actualización
            self.pedido_updated.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo realizar la entrega: {str(e)}")
    
    def realizar_entrega_completa(self):
        respuesta = QMessageBox.question(
            self, "Confirmar entrega completa",
            "¿Está seguro de que desea marcar este pedido como entregado completamente?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if respuesta == QMessageBox.No:
            return
        
        try:
            # Marcar como cambio local
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()
            
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Actualizar todas las cantidades entregadas a la cantidad total.
            # (estado_entrega es una columna GENERATED en la BD: se recalcula
            # sola a partir de cantidad_entregada, no hay que tocarla.)
            cursor.execute("""
                UPDATE DetallePedido
                SET cantidad_entregada = cantidad
                WHERE id_pedido = %s
            """, (self.id_pedido,))

            # Estado + fecha de entrega REAL (hoy). No se usa COALESCE: si el
            # pedido estaba programado para una fecha vieja, conservarla hacía
            # que el panel "Entregados (última semana)" lo filtrara y el pedido
            # quedara fuera de ambos paneles.
            fecha_actual = date.today()
            cursor.execute("""
                UPDATE Pedido
                SET estado_pedido = 'entregado',
                    fecha_entrega = %s
                WHERE id_pedido = %s
            """, (fecha_actual, self.id_pedido))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            QMessageBox.information(self, "Éxito", "Pedido marcado como Entregado Completamente!")
            
            # Recargar datos
            self.cargar_datos_pedido()
            self.cargar_productos_pedido()
            self.cargar_tabla_entrega_parcial()
            
            # Emitir señal y forzar actualización
            self.pedido_updated.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo marcar el pedido como entregado: {str(e)}")
    
    def eliminar_pedido(self):
        respuesta = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Está seguro de que desea eliminar el pedido #{self.id_pedido}?\n\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if respuesta == QMessageBox.No:
            return
        
        try:
            # Marcar como cambio local
            if self.sync_manager:
                self.sync_manager.marcar_cambio_local()
            
            _borrar_pedido(self.id_pedido)

            QMessageBox.information(self, "Éxito", f"Pedido #{self.id_pedido} eliminado correctamente!")
            
            # Emitir señales y forzar actualización
            self.pedido_deleted.emit(self.id_pedido)
            if self.sync_manager:
                self.sync_manager.force_refresh()
            
            self.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el pedido: {str(e)}")

class VentanaHistorialCompleto(QDialog):
    def __init__(self, parent=None, sync_manager=None):
        super().__init__(parent)
        self.sync_manager = sync_manager
        self.setWindowTitle("Historial Completo de Pedidos Entregados")
        self.setMinimumSize(900, 600)
        
        layout = QVBoxLayout(self)
        
        # Título
        titulo = QLabel("HISTORIAL COMPLETO DE PEDIDOS ENTREGADOS")
        titulo.setFont(QFont("Arial", 14, QFont.Bold))
        titulo.setStyleSheet("color: #4CAF50; padding: 8px; background-color: #E8F5E8; border-radius: 5px; margin-bottom: 10px;")
        layout.addWidget(titulo)
        
        # Filtros
        filtros_frame = QGroupBox("Filtros de Búsqueda")
        filtros_layout = QHBoxLayout(filtros_frame)
        
        filtros_layout.addWidget(QLabel("Cliente:"))
        self.filtro_cliente = QLineEdit()
        self.filtro_cliente.setPlaceholderText("Buscar por nombre de cliente...")
        self.filtro_cliente.textChanged.connect(self.filtrar_pedidos)
        filtros_layout.addWidget(self.filtro_cliente)
        
        filtros_layout.addWidget(QLabel("Desde:"))
        self.date_desde = QDateEdit()
        self.date_desde.setDate(QDate.currentDate().addDays(-30))
        self.date_desde.setCalendarPopup(True)
        self.date_desde.dateChanged.connect(self.filtrar_pedidos)
        filtros_layout.addWidget(self.date_desde)
        
        filtros_layout.addWidget(QLabel("Hasta:"))
        self.date_hasta = QDateEdit()
        self.date_hasta.setDate(QDate.currentDate())
        self.date_hasta.setCalendarPopup(True)
        self.date_hasta.dateChanged.connect(self.filtrar_pedidos)
        filtros_layout.addWidget(self.date_hasta)
        
        btn_filtrar = QPushButton("Aplicar Filtros")
        btn_filtrar.clicked.connect(self.filtrar_pedidos)
        filtros_layout.addWidget(btn_filtrar)
        
        layout.addWidget(filtros_frame)
        
        # Tabla de pedidos
        self.tabla_historial = QTableWidget()
        self.tabla_historial.setColumnCount(5)
        self.tabla_historial.setHorizontalHeaderLabels([
            "ID", "Cliente", "Fecha Pedido", "Fecha Entrega", "Acciones"
        ])
        self.tabla_historial.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_historial.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.tabla_historial)
        
        # Botones
        botones_layout = QHBoxLayout()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.close)
        botones_layout.addStretch()
        botones_layout.addWidget(btn_cerrar)
        layout.addLayout(botones_layout)
        
        # Cargar datos iniciales
        self.cargar_historial_completo()
        
        # Aplicar estilos
        self.aplicar_estilos()
    
    def obtener_conexion(self):
        return _conexion()
    
    def cargar_historial_completo(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.id_pedido, c.nombre, p.fecha_pedido, p.fecha_entrega
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido = 'entregado'
                ORDER BY p.fecha_entrega DESC
            """)
            
            self.todos_los_pedidos = cursor.fetchall()
            self.mostrar_pedidos(self.todos_los_pedidos)
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar el historial: {str(e)}")
    
    def mostrar_pedidos(self, pedidos):
        self.tabla_historial.setRowCount(len(pedidos))
        
        for i, (id_pedido, cliente, fecha_pedido, fecha_entrega) in enumerate(pedidos):
            self.tabla_historial.setItem(i, 0, QTableWidgetItem(str(id_pedido)))
            self.tabla_historial.setItem(i, 1, QTableWidgetItem(cliente))
            self.tabla_historial.setItem(i, 2, QTableWidgetItem(fecha_pedido.strftime('%d/%m/%Y')))
            self.tabla_historial.setItem(i, 3, QTableWidgetItem(
                fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else "Sin fecha"
            ))
            
            btn_ver = QPushButton("Ver")
            btn_ver.setStyleSheet("background-color: #4CAF50; color: white; border: none; padding: 4px 8px; border-radius: 3px; font-weight: bold;")
            btn_ver.clicked.connect(lambda checked, pid=id_pedido: self.ver_detalle_pedido(pid))
            self.tabla_historial.setCellWidget(i, 4, btn_ver)
    
    def filtrar_pedidos(self):
        cliente_filtro = self.filtro_cliente.text().lower()
        fecha_desde = self.date_desde.date().toPyDate()
        fecha_hasta = self.date_hasta.date().toPyDate()
        
        pedidos_filtrados = []
        for pedido in self.todos_los_pedidos:
            id_pedido, cliente, fecha_pedido, fecha_entrega = pedido
            
            # Filtro por cliente
            if cliente_filtro and cliente_filtro not in cliente.lower():
                continue
            
            # Filtro por fecha de entrega
            if fecha_entrega and (fecha_entrega < fecha_desde or fecha_entrega > fecha_hasta):
                continue
            
            pedidos_filtrados.append(pedido)
        
        self.mostrar_pedidos(pedidos_filtrados)
    
    def ver_detalle_pedido(self, id_pedido):
        detalle_window = VentanaDetallePedido(id_pedido, self, self.sync_manager)
        detalle_window.exec_()
    
    def aplicar_estilos(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 3px;
                padding-top: 10px;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 3px;
                selection-background-color: #e3f2fd;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
        """)

class VentanaProgramarPedido(QWidget):
    """Gestión de pedidos. Widget embebible.

    `sync_manager`: si no se pasa, se crea uno propio (uso legacy standalone).
    Las acciones de barra quedan en `self.acciones_toolbar`.
    """

    def __init__(self, sync_manager=None, parent=None):
        super().__init__(parent)
        # El alto mínimo era 600: sumado a la barra de secciones y la de estado obligaba a la
        # ventana principal a medir 680 px y se cortaba en monitores de 1280x720.
        self.setMinimumSize(900, 500)
        self.acciones_toolbar = []

        self.sync_manager = sync_manager or DatabaseSyncManager()
        self.sync_manager.pedidos_pendientes_changed.connect(self.cargar_pedidos_pendientes)
        self.sync_manager.pedidos_entregados_changed.connect(self.cargar_pedidos_entregados)

        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(8)
        layout_principal.setContentsMargins(10, 8, 10, 8)

        self.crear_barra_estado(layout_principal)
        self.crear_barra_herramientas(layout_principal)   # llena self.acciones_toolbar
        self.crear_kpis(layout_principal)
        self.crear_panel_principal(layout_principal)

        self.aplicar_estilos()
        self.cargar_todos_los_pedidos()

    # ── barra de sincronización ─────────────────────────────────────────────
    def crear_barra_estado(self, layout):
        barra = QFrame()
        barra.setObjectName("syncBar")
        barra.setStyleSheet(
            "#syncBar { background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; }"
        )
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(12, 5, 12, 5)
        fila.setSpacing(8)

        self.sync_indicator = QLabel("●")
        self.sync_indicator.setStyleSheet("color: #10b981; font-size: 12px; background: transparent;")
        fila.addWidget(self.sync_indicator)

        self.status_label = QLabel("Sincronizando automáticamente cada 8 segundos…")
        self.status_label.setStyleSheet("color: #065f46; font-weight: 600; font-size: 11px; background: transparent;")
        fila.addWidget(self.status_label)
        fila.addStretch(1)

        self.reloj_label = QLabel("")
        self.reloj_label.setStyleSheet(
            "color: #047857; font-family: Consolas; font-size: 10px; background-color: #d1fae5;"
            " border-radius: 4px; padding: 1px 6px;"
        )
        fila.addWidget(self.reloj_label)
        layout.addWidget(barra)

        self.indicator_timer = QTimer(self)
        self.indicator_timer.timeout.connect(self.animate_sync_indicator)
        self.indicator_timer.start(1000)
        self.indicator_state = True
        self.animate_sync_indicator()

    def animate_sync_indicator(self):
        self.sync_indicator.setStyleSheet(
            f"color: {'#10b981' if self.indicator_state else '#cbd5e1'}; font-size: 12px; background: transparent;"
        )
        self.reloj_label.setText(datetime.now().strftime("%H:%M:%S"))
        self.indicator_state = not self.indicator_state

    def crear_barra_herramientas(self, layout):
        """Construye las QAction de barra (las muestra quien embeba el widget)."""
        nuevo = QAction("＋ Nuevo Pedido", self)
        nuevo.triggered.connect(self.nuevo_pedido)

        importar = QAction("Importar DBF", self)
        importar.triggered.connect(self.importar_dbf)

        actualizar = QAction("↻ Actualizar", self)
        actualizar.triggered.connect(self.forzar_actualizacion)

        self.acciones_toolbar = [nuevo, importar, actualizar]

    # ── KPIs ────────────────────────────────────────────────────────────────
    def crear_kpis(self, layout):
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self._kpi_pendientes = self._kpi_card("Pedidos Pendientes", "#b45309", "#fffbeb", "#fde68a")
        self._kpi_semana = self._kpi_card("Entregados (Semana)", "#047857", "#ecfdf5", "#a7f3d0")
        self._kpi_historico = self._kpi_card("Entregados (Histórico)", "#334155", "#f8fafc", "#e2e8f0")
        self._kpi_despacho = self._kpi_card("Tiempo Prom. Despacho", "#1d4ed8", "#eff6ff", "#bfdbfe")
        for _, card in (self._kpi_pendientes, self._kpi_semana, self._kpi_historico, self._kpi_despacho):
            fila.addWidget(card)
        layout.addLayout(fila)

    def _kpi_card(self, titulo, color_valor, bg, borde):
        card = QFrame()
        card.setObjectName("kpiCard")
        card.setStyleSheet(f"#kpiCard {{ background-color: {bg}; border: 1px solid {borde}; border-radius: 8px; }}")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 7, 12, 8)
        v.setSpacing(1)
        t = QLabel(titulo.upper())
        t.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; background: transparent; border: none;")
        val = QLabel("—")
        val.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {color_valor}; background: transparent; border: none;")
        v.addWidget(t)
        v.addWidget(val)
        return val, card

    def _actualizar_kpis(self):
        try:
            conn = self.obtener_conexion()
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM Pedido WHERE estado_pedido IN ('pendiente','programado','en camino')")
            self._kpi_pendientes[0].setText(str(cur.fetchone()[0]))
            cur.execute("SELECT count(*) FROM Pedido WHERE estado_pedido='entregado' AND fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'")
            self._kpi_semana[0].setText(str(cur.fetchone()[0]))
            cur.execute("SELECT count(*) FROM Pedido WHERE estado_pedido='entregado'")
            self._kpi_historico[0].setText(str(cur.fetchone()[0]))
            cur.execute("""
                SELECT AVG(fecha_entrega - fecha_pedido)
                FROM Pedido
                WHERE estado_pedido='entregado' AND fecha_entrega IS NOT NULL AND fecha_entrega >= fecha_pedido
            """)
            dias = cur.fetchone()[0]
            self._kpi_despacho[0].setText(f"{float(dias):.0f} días" if dias is not None else "—")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Error actualizando KPIs de pedidos: {e}")

    # ── paneles ─────────────────────────────────────────────────────────────
    def crear_panel_principal(self, layout):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("splitPedidos")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        layout.addWidget(splitter, 1)

        # Entregados a la izquierda, pendientes a la derecha.
        self.crear_panel_entregados(splitter)
        self.crear_panel_pendientes(splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 500])

    def _tarjeta_panel(self, titulo, color_pto, extra_widget=None):
        """QFrame blanco con encabezado (punto de color + título + badge de conteo
        + widget extra) y un layout listo para meterle la tabla. Devuelve
        (frame, layout_cuerpo, label_badge)."""
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setStyleSheet("#panelCard { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }")
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        cab = QFrame()
        cab.setObjectName("cardHeader")
        cab.setStyleSheet("QFrame#cardHeader { background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;"
                          " border-top-left-radius: 8px; border-top-right-radius: 8px; }")
        cab.setFixedHeight(36)   # misma altura en ambas tarjetas: el botón de la izquierda las desalineaba
        h = QHBoxLayout(cab)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(8)
        pto = QLabel("●")
        pto.setStyleSheet(f"color: {color_pto}; font-size: 11px; background: transparent;")
        h.addWidget(pto)
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet("font-size: 11px; font-weight: 800; color: #334155; background: transparent;")
        h.addWidget(lbl)
        badge = QLabel("(0)")
        badge.setStyleSheet(
            f"color: {color_pto}; font-size: 10px; font-weight: 800; background-color: #eff6ff;"
            " border-radius: 8px; padding: 0px 7px;"
        )
        h.addWidget(badge, 0, Qt.AlignVCenter)   # sin esto se estira a todo el alto de la cabecera
        h.addStretch(1)
        if extra_widget is not None:
            h.addWidget(extra_widget)
        v.addWidget(cab)

        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        v.addLayout(cuerpo, 1)
        return panel, cuerpo, badge

    def _preparar_tabla(self, tabla, anchos):
        """anchos: lista por columna (None = Stretch)."""
        tabla.verticalHeader().setVisible(False)
        tabla.verticalHeader().setDefaultSectionSize(34)
        tabla.setSelectionBehavior(QTableWidget.SelectRows)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setShowGrid(False)
        tabla.setAlternatingRowColors(True)
        header = tabla.horizontalHeader()
        header.setStretchLastSection(False)
        for i, w in enumerate(anchos):
            if w is None:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(i, QHeaderView.Fixed)
                tabla.setColumnWidth(i, w)

    def crear_panel_pendientes(self, parent):
        self.tabla_pendientes = QTableWidget()
        self.tabla_pendientes.setColumnCount(6)
        self.tabla_pendientes.setHorizontalHeaderLabels(
            ["ID", "Cliente", "Fecha Pedido", "Fecha Entrega", "Estado", "Acciones"])
        self._preparar_tabla(self.tabla_pendientes, _ANCHOS_TABLA_PEDIDOS)

        panel, cuerpo, badge = self._tarjeta_panel("Pedidos Pendientes", "#2563eb")
        self.contador_pendientes = badge
        cuerpo.addWidget(self.tabla_pendientes)
        panel.setMinimumWidth(480)
        parent.addWidget(panel)

    def crear_panel_entregados(self, parent):
        btn_historial = QPushButton("Ver Historial Completo")
        btn_historial.setObjectName("btn_historial")
        btn_historial.clicked.connect(self.ver_historial_completo)

        self.tabla_entregados = QTableWidget()
        self.tabla_entregados.setColumnCount(6)
        self.tabla_entregados.setHorizontalHeaderLabels(
            ["ID", "Cliente", "Fecha Pedido", "Fecha Entrega", "Estado", "Acciones"])
        self._preparar_tabla(self.tabla_entregados, _ANCHOS_TABLA_PEDIDOS)

        panel, cuerpo, badge = self._tarjeta_panel("Pedidos Entregados — Última Semana", "#059669", btn_historial)
        self.contador_entregados = badge
        cuerpo.addWidget(self.tabla_entregados)
        panel.setMinimumWidth(480)
        parent.addWidget(panel)

    def _fila_pedido(self, tabla, i, id_pedido, cliente, cuit, fecha_pedido, fecha_entrega, estado,
                     eliminable=False):
        it_id = QTableWidgetItem(str(id_pedido))
        it_id.setTextAlignment(Qt.AlignCenter)
        it_id.setForeground(QColor("#1d4ed8"))
        it_id.setFont(QFont("Consolas", 9, QFont.Bold))
        tabla.setItem(i, 0, it_id)

        tabla.setCellWidget(i, 1, _celda_cliente(cliente, f"CUIT {cuit}" if cuit else ""))

        it_fp = QTableWidgetItem(fecha_pedido.strftime('%d/%m/%Y') if fecha_pedido else "—")
        it_fp.setTextAlignment(Qt.AlignCenter)
        it_fp.setFont(QFont("Consolas", 8))
        it_fp.setForeground(QColor("#475569"))
        tabla.setItem(i, 2, it_fp)

        if fecha_entrega:
            # Al recargar, la fila puede traer el chip "Sin programar" de la carga
            # anterior: un cellWidget tapa al item, así que hay que sacarlo.
            tabla.removeCellWidget(i, 3)
            it_fe = QTableWidgetItem(fecha_entrega.strftime('%d/%m/%Y'))
            it_fe.setTextAlignment(Qt.AlignCenter)
            it_fe.setFont(QFont("Consolas", 8))
            it_fe.setForeground(QColor("#065f46" if estado == "entregado" else "#334155"))
            tabla.setItem(i, 3, it_fe)
        else:
            chip = QLabel("Sin programar")
            chip.setAlignment(Qt.AlignCenter)
            chip.setStyleSheet(
                "QLabel { background-color: #fffbeb; color: #92400e; border: 1px solid #fde68a;"
                " border-radius: 8px; padding: 1px 8px; font-size: 10px; font-weight: 600; }"
            )
            tabla.setCellWidget(i, 3, _centrar(chip))

        tabla.setCellWidget(i, 4, _centrar(_pill_estado(estado)))

        btn_ver = QPushButton()
        btn_ver.setObjectName("btnVer")
        btn_ver.setIcon(_icono_ojo())
        btn_ver.setIconSize(QSize(16, 16))
        btn_ver.setFixedSize(30, 22)
        btn_ver.setToolTip("Ver detalle")
        btn_ver.setCursor(Qt.PointingHandCursor)
        # estilo inline: el más cercano al widget gana, así ningún stylesheet
        # ancestro lo deja blanco sobre blanco.
        btn_ver.setStyleSheet(
            "QPushButton { background-color: #2563eb; border: none;"
            " border-radius: 4px; padding: 0px; }"
            " QPushButton:hover { background-color: #1d4ed8; }"
            " QPushButton:pressed { background-color: #1e40af; }"
        )
        btn_ver.clicked.connect(lambda _=False, pid=id_pedido: self.ver_detalle_pedido(pid))

        acciones = QWidget()
        acciones.setObjectName("celdaCentrada")
        acciones.setStyleSheet("QWidget#celdaCentrada { background: transparent; }")
        fila = QHBoxLayout(acciones)
        fila.setContentsMargins(4, 3, 4, 3)
        fila.setSpacing(4)
        fila.addStretch(1)
        fila.addWidget(btn_ver)
        if eliminable:
            btn_del = QPushButton("✕")
            btn_del.setToolTip("Eliminar pedido (el cliente lo canceló)")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedSize(26, 22)
            btn_del.setStyleSheet(
                "QPushButton { background-color: #ffffff; color: #dc2626; border: 1px solid #fca5a5;"
                " border-radius: 4px; padding: 0px; font-size: 11px; font-weight: 700; }"
                " QPushButton:hover { background-color: #fef2f2; }"
                " QPushButton:pressed { background-color: #fee2e2; }"
            )
            btn_del.clicked.connect(
                lambda _=False, pid=id_pedido, nombre=cliente: self.eliminar_pedido(pid, nombre))
            fila.addWidget(btn_del)
        fila.addStretch(1)
        tabla.setCellWidget(i, 5, acciones)

    def obtener_conexion(self):
        return _conexion()
    
    def nuevo_pedido(self):
        dialogo = DialogoNuevoPedido(self, self.sync_manager)
        # Conectar señal de pedido creado
        dialogo.pedido_creado.connect(self.on_pedido_creado)
        dialogo.exec_()
    
    def on_pedido_creado(self, id_pedido):
        """Manejar creación de nuevo pedido"""
        # Actualizar estado
        self.status_label.setText(f"✅ Nuevo pedido #{id_pedido} creado y sincronizado")
        QTimer.singleShot(3000, lambda: self.status_label.setText("🔄 Sincronizando automáticamente cada 8 segundos..."))
    
    def importar_dbf(self):
        # Mostrar diálogo de confirmación
        respuesta = QMessageBox.question(
            self, "Importar DBF",
            "¿Desea importar los datos desde los archivos DBF?\n\nRuta: D:\\tiempo\\vtiempoges\\GESTION\\MANA2014",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if respuesta == QMessageBox.Yes:
            # Crear y ejecutar hilo de importación
            self.import_thread = ImportThread()
            self.import_thread.finished.connect(self.importacion_terminada)
            self.import_thread.start()
            
            # Actualizar estado
            self.status_label.setText("📥 Importando datos desde DBF...")
            QMessageBox.information(self, "Importando", "Importación iniciada. Se notificará cuando termine.")
    
    def importacion_terminada(self, exitoso, mensaje):
        if exitoso:
            QMessageBox.information(self, "Éxito", mensaje)
            self.status_label.setText("✅ Importación completada y sincronizada")
            # Forzar actualización después de importar
            self.sync_manager.force_refresh()
        else:
            QMessageBox.critical(self, "Error", mensaje)
            self.status_label.setText("❌ Error en la importación")
        
        # Restaurar mensaje normal después de 3 segundos
        QTimer.singleShot(3000, lambda: self.status_label.setText("🔄 Sincronizando automáticamente cada 8 segundos..."))
    
    def forzar_actualizacion(self):
        """Forzar actualización manual"""
        self.status_label.setText("🔄 Actualizando manualmente...")
        self.sync_manager.force_refresh()
        QTimer.singleShot(1000, lambda: self.status_label.setText("✅ Actualización manual completada"))
        QTimer.singleShot(3000, lambda: self.status_label.setText("🔄 Sincronizando automáticamente cada 8 segundos..."))
    
    def cargar_todos_los_pedidos(self):
        self.cargar_pedidos_pendientes()
        self.cargar_pedidos_entregados()
    
    def cargar_pedidos_pendientes(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT p.id_pedido, c.nombre, c.cuit, p.fecha_pedido, p.fecha_entrega, p.estado_pedido
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido IN ('pendiente', 'programado', 'en camino')
                ORDER BY p.fecha_pedido DESC
            """)
            pedidos = cursor.fetchall()
            cursor.close()
            conn.close()

            self.tabla_pendientes.setRowCount(len(pedidos))
            self.contador_pendientes.setText(f"({len(pedidos)})")
            for i, (id_pedido, cliente, cuit, fecha_pedido, fecha_entrega, estado) in enumerate(pedidos):
                self._fila_pedido(self.tabla_pendientes, i, id_pedido, cliente, cuit,
                                  fecha_pedido, fecha_entrega, estado, eliminable=True)

            self._actualizar_kpis()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar pedidos pendientes: {str(e)}")

    def cargar_pedidos_entregados(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()

            # Solo pedidos entregados de la última semana
            cursor.execute("""
                SELECT p.id_pedido, c.nombre, c.cuit, p.fecha_pedido, p.fecha_entrega, p.estado_pedido
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido = 'entregado'
                AND p.fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY p.fecha_entrega DESC
            """)
            pedidos = cursor.fetchall()
            cursor.close()
            conn.close()

            self.tabla_entregados.setRowCount(len(pedidos))
            self.contador_entregados.setText(f"({len(pedidos)})")
            for i, (id_pedido, cliente, cuit, fecha_pedido, fecha_entrega, estado) in enumerate(pedidos):
                self._fila_pedido(self.tabla_entregados, i, id_pedido, cliente, cuit,
                                  fecha_pedido, fecha_entrega, estado)

            self._actualizar_kpis()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar pedidos entregados: {str(e)}")
    
    def ver_historial_completo(self):
        historial_window = VentanaHistorialCompleto(self, self.sync_manager)
        historial_window.exec_()
    
    def ver_detalle_pedido(self, id_pedido):
        detalle_window = VentanaDetallePedido(id_pedido, self, self.sync_manager)
        # Conectar señales de la ventana de detalle
        detalle_window.pedido_updated.connect(self.on_pedido_actualizado)
        detalle_window.pedido_deleted.connect(self.on_pedido_eliminado)
        detalle_window.exec_()
    
    def on_pedido_actualizado(self, id_pedido):
        """Manejar actualización de pedido"""
        self.status_label.setText(f"✅ Pedido #{id_pedido} actualizado y sincronizado")
        QTimer.singleShot(3000, lambda: self.status_label.setText("🔄 Sincronizando automáticamente cada 8 segundos..."))
    
    def eliminar_pedido(self, id_pedido, cliente):
        """Borra un pedido pendiente desde la grilla (ej. el cliente lo canceló)."""
        respuesta = QMessageBox.question(
            self, "Eliminar pedido",
            f"¿Eliminar el pedido #{id_pedido} de {cliente}?\n\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if respuesta != QMessageBox.Yes:
            return
        try:
            self.sync_manager.marcar_cambio_local()
            _borrar_pedido(id_pedido)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el pedido: {e}")
            return
        self.on_pedido_eliminado(id_pedido)
        self.sync_manager.force_refresh()

    def on_pedido_eliminado(self, id_pedido):
        """Manejar eliminación de pedido"""
        self.status_label.setText(f"🗑️ Pedido #{id_pedido} eliminado y sincronizado")
        QTimer.singleShot(3000, lambda: self.status_label.setText("🔄 Sincronizando automáticamente cada 8 segundos..."))
    
    def closeEvent(self, event):
        """Limpiar recursos al cerrar"""
        if hasattr(self, 'sync_manager'):
            self.sync_manager.timer.stop()
        if hasattr(self, 'indicator_timer'):
            self.indicator_timer.stop()
        event.accept()
    
    def aplicar_estilos(self):
        self.setStyleSheet("""
            VentanaProgramarPedido { background-color: #f1f5f9; }
            QWidget { font-family: 'Segoe UI', Arial, sans-serif; color: #334155; }
            QLabel { background: transparent; }
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #1e293b;
                border: none;
                font-size: 11px;
            }
            QTableWidget::item { padding: 2px 8px; border: none; }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                font-weight: 700;
                font-size: 10px;
            }
            QTableCornerButton::section { background-color: #f8fafc; border: none; }
            QPushButton#btnVer {
                background-color: #2563eb; color: white; border: none;
                border-radius: 4px; padding: 3px 12px; font-size: 10px; font-weight: 700;
                min-width: 0px;
            }
            QPushButton#btnVer:hover { background-color: #1d4ed8; }
            QPushButton#btn_historial {
                background-color: #ffffff; color: #b45309; border: 1px solid #fcd34d;
                border-radius: 5px; padding: 3px 10px; font-size: 10px; font-weight: 700;
            }
            QPushButton#btn_historial:hover { background-color: #fffbeb; }
            QSplitter#splitPedidos::handle { background-color: transparent; width: 8px; }
        """)
