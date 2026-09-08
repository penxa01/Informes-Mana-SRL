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
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QObject, QPropertyAnimation, QRect, QEasingCurve
from PyQt5.QtGui import QFont

from datetime import date, datetime
from dbfread import DBF

from src.controllers import config

class NotificationWidget(QWidget):
    """Widget de notificación tipo toast"""
    
    def __init__(self, titulo, mensaje, tipo="info", duracion=5000):
        super().__init__()
        self.duracion = duracion
        self.tipo = tipo
        
        # Configuración de la ventana
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(350, 80)
        
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
    
    def posicionar(self):
        """Posicionar la notificación en la esquina superior derecha"""
        screen = QApplication.desktop().screenGeometry()
        x = screen.width() - self.width() - 20
        y = 50  # Desde arriba
        self.move(x, y)
    
    def animar_entrada(self):
        """Animación de entrada desde la derecha"""
        screen = QApplication.desktop().screenGeometry()
        start_x = screen.width()
        end_x = screen.width() - self.width() - 20
        
        self.move(start_x, 50)
        
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setStartValue(QRect(start_x, 50, self.width(), self.height()))
        self.animation.setEndValue(QRect(end_x, 50, self.width(), self.height()))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()
    
    def cerrar_notificacion(self):
        """Cerrar la notificación con animación"""
        self.animar_salida()
    
    def animar_salida(self):
        """Animación de salida hacia la derecha"""
        screen = QApplication.desktop().screenGeometry()
        start_x = self.x()
        end_x = screen.width()
        
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
            y_offset = len(self.notifications) * 90  # Espaciado entre notificaciones
            screen = QApplication.desktop().screenGeometry()
            x = screen.width() - notification.width() - 20
            y = 50 + y_offset
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
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
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
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
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
    
    def __init__(self, parent=None, sync_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Pedido")
        self.setMinimumSize(700, 550)
        self.pedido_fue_creado = False
        self.sync_manager = sync_manager
        
        # Listas para almacenar todos los datos
        self.todos_los_clientes = []
        self.todos_los_productos = []
        
        layout = QVBoxLayout(self)
        
        # Información del pedido
        info_group = QGroupBox("Información del Pedido")
        info_layout = QFormLayout(info_group)
        
        # Cliente
        cliente_layout = QVBoxLayout()
        cliente_layout.addWidget(QLabel("Cliente:"))
        
        self.line_cliente = QLineEdit()
        self.line_cliente.setPlaceholderText("Escriba para buscar cliente...")
        self.line_cliente.textChanged.connect(self.filtrar_clientes)
        cliente_layout.addWidget(self.line_cliente)
        
        self.combo_cliente = QComboBox()
        self.combo_cliente.setMaximumHeight(30)
        self.cargar_clientes()
        cliente_layout.addWidget(self.combo_cliente)
        
        info_layout.addRow(cliente_layout)
        
        # Fecha del pedido
        self.date_pedido = QDateEdit()
        self.date_pedido.setDate(QDate.currentDate())
        self.date_pedido.setCalendarPopup(True)
        info_layout.addRow("Fecha de Pedido:", self.date_pedido)
        
        layout.addWidget(info_group)
        
        # Productos del pedido
        productos_group = QGroupBox("Productos del Pedido")
        productos_layout = QVBoxLayout(productos_group)
        
        # Agregar producto
        agregar_layout = QVBoxLayout()
        
        # Primera fila: Búsqueda de producto
        producto_search_layout = QVBoxLayout()
        producto_search_layout.addWidget(QLabel("Producto:"))
        self.line_producto = QLineEdit()
        self.line_producto.setPlaceholderText("Escriba para buscar producto...")
        self.line_producto.textChanged.connect(self.filtrar_productos)
        producto_search_layout.addWidget(self.line_producto)
        
        self.combo_producto = QComboBox()
        self.combo_producto.setMaximumHeight(30)
        self.cargar_productos()
        producto_search_layout.addWidget(self.combo_producto)
        
        agregar_layout.addLayout(producto_search_layout)
        
        # Segunda fila: Cantidad y botón agregar
        cantidad_layout = QHBoxLayout()
        cantidad_layout.addWidget(QLabel("Cantidad:"))
        self.spin_cantidad = QSpinBox()
        self.spin_cantidad.setMinimum(1)
        self.spin_cantidad.setMaximum(9999)
        self.spin_cantidad.setValue(1)
        cantidad_layout.addWidget(self.spin_cantidad)
        
        cantidad_layout.addStretch()
        
        btn_agregar = QPushButton("Agregar")
        btn_agregar.clicked.connect(self.agregar_producto)
        cantidad_layout.addWidget(btn_agregar)
        
        agregar_layout.addLayout(cantidad_layout)
        
        productos_layout.addLayout(agregar_layout)
        
        # Tabla de productos
        self.tabla_productos = QTableWidget()
        self.tabla_productos.setColumnCount(4)
        self.tabla_productos.setHorizontalHeaderLabels([
            "ID Producto", "Descripción", "Cantidad", "Eliminar"
        ])
        self.tabla_productos.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        productos_layout.addWidget(self.tabla_productos)
        
        layout.addWidget(productos_group)
        
        # Botones
        botones_layout = QHBoxLayout()
        btn_crear = QPushButton("Crear Pedido")
        btn_crear.clicked.connect(self.crear_pedido)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        
        botones_layout.addStretch()
        botones_layout.addWidget(btn_crear)
        botones_layout.addWidget(btn_cancelar)
        layout.addLayout(botones_layout)
        
        # Aplicar estilos específicos para esta ventana
        self.aplicar_estilos_dialogo()
    
    def obtener_conexion(self):
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
    def cargar_clientes(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id_cliente, nombre FROM Cliente ORDER BY nombre")
            clientes = cursor.fetchall()
            
            # Guardar todos los clientes
            self.todos_los_clientes = clientes
            
            # Cargar en el combo
            self.combo_cliente.clear()
            for id_cliente, nombre in clientes:
                self.combo_cliente.addItem(f"{nombre} (ID: {id_cliente})", id_cliente)
            
            cursor.close()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar clientes: {str(e)}")
    
    def filtrar_clientes(self):
        texto_busqueda = self.line_cliente.text().lower()
        self.combo_cliente.clear()
        
        for id_cliente, nombre in self.todos_los_clientes:
            if texto_busqueda in nombre.lower():
                self.combo_cliente.addItem(f"{nombre} (ID: {id_cliente})", id_cliente)
    
    def cargar_productos(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT id_producto, nombre FROM Producto ORDER BY nombre")
            productos = cursor.fetchall()
            
            # Guardar todos los productos
            self.todos_los_productos = productos
            
            # Cargar en el combo
            self.combo_producto.clear()
            for id_producto, nombre in productos:
                self.combo_producto.addItem(f"{nombre} ({id_producto})", id_producto)
            
            cursor.close()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar productos: {str(e)}")
    
    def filtrar_productos(self):
        texto_busqueda = self.line_producto.text().lower()
        self.combo_producto.clear()
        
        for id_producto, nombre in self.todos_los_productos:
            if texto_busqueda in nombre.lower() or texto_busqueda in id_producto.lower():
                self.combo_producto.addItem(f"{nombre} ({id_producto})", id_producto)
    
    def agregar_producto(self):
        if self.combo_producto.currentData() is None:
            QMessageBox.warning(self, "Advertencia", "Seleccione un producto")
            return
        
        id_producto = self.combo_producto.currentData()
        nombre_producto = self.combo_producto.currentText()
        cantidad = self.spin_cantidad.value()
        
        # Verificar si el producto ya está en la tabla
        for i in range(self.tabla_productos.rowCount()):
            if self.tabla_productos.item(i, 0).text() == id_producto:
                QMessageBox.warning(self, "Advertencia", "El producto ya está en el pedido")
                return
        
        # Agregar fila a la tabla
        fila = self.tabla_productos.rowCount()
        self.tabla_productos.insertRow(fila)
        
        self.tabla_productos.setItem(fila, 0, QTableWidgetItem(id_producto))
        self.tabla_productos.setItem(fila, 1, QTableWidgetItem(nombre_producto))
        self.tabla_productos.setItem(fila, 2, QTableWidgetItem(str(cantidad)))
        
        btn_eliminar = QPushButton("Eliminar")
        btn_eliminar.clicked.connect(lambda: self.eliminar_producto(fila))
        self.tabla_productos.setCellWidget(fila, 3, btn_eliminar)
    
    def eliminar_producto(self, fila):
        self.tabla_productos.removeRow(fila)
        # Reconectar botones después de eliminar
        for i in range(self.tabla_productos.rowCount()):
            btn = self.tabla_productos.cellWidget(i, 3)
            if btn:
                btn.clicked.disconnect()
                btn.clicked.connect(lambda checked, row=i: self.eliminar_producto(row))
    
    def crear_pedido(self):
        if self.combo_cliente.currentData() is None:
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
                self.combo_cliente.currentData(),
                self.date_pedido.date().toPyDate()
            ))
            
            id_pedido = cursor.fetchone()[0]
            
            # Agregar productos al pedido
            for i in range(self.tabla_productos.rowCount()):
                id_producto = self.tabla_productos.item(i, 0).text()
                cantidad = int(self.tabla_productos.item(i, 2).text())
                
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
    
    def aplicar_estilos_dialogo(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 5px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: white;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
            }
            QComboBox {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
                min-height: 20px;
            }
            QComboBox:focus {
                border: 2px solid #4CAF50;
            }
            QSpinBox {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
                min-width: 80px;
            }
            QDateEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: #333;
                margin-bottom: 4px;
            }
        """)

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
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Información del pedido
        info_frame = QGroupBox("Información del Pedido")
        info_layout = QFormLayout(info_frame)
        
        self.label_cliente = QLabel()
        self.label_fecha_pedido = QLabel()
        self.label_estado = QLabel()
        self.label_fecha_entrega = QLabel()
        
        info_layout.addRow("Cliente:", self.label_cliente)
        info_layout.addRow("Fecha de Pedido:", self.label_fecha_pedido)
        info_layout.addRow("Estado:", self.label_estado)
        info_layout.addRow("Fecha de Entrega:", self.label_fecha_entrega)
        
        layout.addWidget(info_frame)
        
        # Controles de programación
        prog_frame = QGroupBox("Programar Entrega")
        prog_layout = QHBoxLayout(prog_frame)
        
        prog_layout.addWidget(QLabel("Fecha de Entrega:"))
        self.date_entrega = QDateEdit()
        self.date_entrega.setDate(QDate.currentDate())
        self.date_entrega.setCalendarPopup(True)
        prog_layout.addWidget(self.date_entrega)
        
        self.btn_programar = QPushButton("Programar")
        self.btn_programar.clicked.connect(self.programar_entrega)
        prog_layout.addWidget(self.btn_programar)
        
        self.btn_en_camino = QPushButton("En Camino")
        self.btn_en_camino.clicked.connect(self.marcar_en_camino)
        prog_layout.addWidget(self.btn_en_camino)
        
        prog_layout.addStretch()
        layout.addWidget(prog_frame)
        
        # Tabla de productos
        productos_frame = QGroupBox("Productos del Pedido")
        productos_layout = QVBoxLayout(productos_frame)
        
        self.tabla_productos = QTableWidget()
        self.tabla_productos.setColumnCount(6)
        self.tabla_productos.setHorizontalHeaderLabels([
            "Producto", "Descripción", "Solicitado", "Entregado", "A Entregar", "Estado"
        ])
        self.tabla_productos.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        productos_layout.addWidget(self.tabla_productos)
        
        # Controles de entrega parcial
        entrega_parcial_frame = QGroupBox("Entrega Parcial")
        entrega_parcial_layout = QVBoxLayout(entrega_parcial_frame)
        
        # Tabla para modificar cantidades de entrega parcial
        self.tabla_entrega_parcial = QTableWidget()
        self.tabla_entrega_parcial.setColumnCount(4)
        self.tabla_entrega_parcial.setHorizontalHeaderLabels([
            "Producto", "Descripción", "Pendiente", "Cantidad a Entregar"
        ])
        self.tabla_entrega_parcial.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_entrega_parcial.setMaximumHeight(200)
        entrega_parcial_layout.addWidget(self.tabla_entrega_parcial)
        
        layout.addWidget(productos_frame)
        layout.addWidget(entrega_parcial_frame)
        
        # Botones de entrega
        botones_layout = QHBoxLayout()
        self.btn_entrega_parcial = QPushButton("Entrega Parcial")
        self.btn_entrega_parcial.clicked.connect(self.realizar_entrega_parcial)
        botones_layout.addWidget(self.btn_entrega_parcial)
        
        self.btn_entrega_completa = QPushButton("Entrega Completa")
        self.btn_entrega_completa.clicked.connect(self.realizar_entrega_completa)
        botones_layout.addWidget(self.btn_entrega_completa)
        
        self.btn_eliminar_pedido = QPushButton("Eliminar Pedido")
        self.btn_eliminar_pedido.clicked.connect(self.eliminar_pedido)
        self.btn_eliminar_pedido.setStyleSheet("background-color: #f44336;")  # Rojo para eliminar
        botones_layout.addWidget(self.btn_eliminar_pedido)
        
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.close)
        botones_layout.addWidget(btn_cerrar)
        
        botones_layout.addStretch()
        layout.addLayout(botones_layout)
        
        # Cargar datos
        self.cargar_datos_pedido()
        self.cargar_productos_pedido()
        self.cargar_tabla_entrega_parcial()
    
    def obtener_conexion(self):
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
    def cargar_datos_pedido(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT c.nombre, p.fecha_pedido, p.estado_pedido, p.fecha_entrega
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.id_pedido = %s
            """, (self.id_pedido,))
            
            resultado = cursor.fetchone()
            if resultado:
                nombre_cliente, fecha_pedido, estado, fecha_entrega = resultado
                self.label_cliente.setText(nombre_cliente)
                self.label_fecha_pedido.setText(fecha_pedido.strftime('%d/%m/%Y'))
                self.label_estado.setText(estado.upper())
                
                if fecha_entrega:
                    self.label_fecha_entrega.setText(fecha_entrega.strftime('%d/%m/%Y'))
                    self.date_entrega.setDate(fecha_entrega)
                else:
                    self.label_fecha_entrega.setText("Sin programar")
            
            cursor.close()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los datos: {str(e)}")
    
    def cargar_productos_pedido(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT dp.id_producto, p.nombre, dp.cantidad, dp.cantidad_entregada, dp.estado_entrega
                FROM DetallePedido dp
                JOIN Producto p ON dp.id_producto = p.id_producto
                WHERE dp.id_pedido = %s
            """, (self.id_pedido,))
            
            productos = cursor.fetchall()
            self.tabla_productos.setRowCount(len(productos))
            
            for i, (id_producto, nombre, cantidad, cantidad_entregada, estado_entrega) in enumerate(productos):
                self.tabla_productos.setItem(i, 0, QTableWidgetItem(id_producto))
                self.tabla_productos.setItem(i, 1, QTableWidgetItem(nombre))
                self.tabla_productos.setItem(i, 2, QTableWidgetItem(str(cantidad)))
                self.tabla_productos.setItem(i, 3, QTableWidgetItem(str(cantidad_entregada)))
                
                # A Entregar - Campo calculado y no modificable
                a_entregar = cantidad - cantidad_entregada
                item_a_entregar = QTableWidgetItem(str(a_entregar))
                item_a_entregar.setFlags(item_a_entregar.flags() & ~Qt.ItemIsEditable)  # No editable
                self.tabla_productos.setItem(i, 4, item_a_entregar)
                
                self.tabla_productos.setItem(i, 5, QTableWidgetItem(estado_entrega.capitalize()))
            
            cursor.close()
            conn.close()
            
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
            """, (self.id_pedido,))
            
            productos_pendientes = cursor.fetchall()
            self.tabla_entrega_parcial.setRowCount(len(productos_pendientes))
            
            for i, (id_producto, nombre, cantidad, cantidad_entregada) in enumerate(productos_pendientes):
                pendiente = cantidad - cantidad_entregada
                
                self.tabla_entrega_parcial.setItem(i, 0, QTableWidgetItem(id_producto))
                self.tabla_entrega_parcial.setItem(i, 1, QTableWidgetItem(nombre))
                self.tabla_entrega_parcial.setItem(i, 2, QTableWidgetItem(str(pendiente)))
                
                # SpinBox para cantidad a entregar
                spin_entregar = QSpinBox()
                spin_entregar.setMinimum(0)
                spin_entregar.setMaximum(pendiente)
                spin_entregar.setValue(pendiente)  # Por defecto, entregar todo lo pendiente
                self.tabla_entrega_parcial.setCellWidget(i, 3, spin_entregar)
            
            cursor.close()
            conn.close()
            
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
            
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Eliminar detalles del pedido primero (por foreign key)
            cursor.execute("DELETE FROM DetallePedido WHERE id_pedido = %s", (self.id_pedido,))
            
            # Eliminar el pedido
            cursor.execute("DELETE FROM Pedido WHERE id_pedido = %s", (self.id_pedido,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
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
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
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
        self.setMinimumSize(900, 600)
        self.acciones_toolbar = []

        self.sync_manager = sync_manager or DatabaseSyncManager()
        self.sync_manager.pedidos_pendientes_changed.connect(self.cargar_pedidos_pendientes)
        self.sync_manager.pedidos_entregados_changed.connect(self.cargar_pedidos_entregados)

        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(6)
        layout_principal.setContentsMargins(12, 8, 12, 8)

        self.crear_barra_estado(layout_principal)
        self.crear_barra_herramientas(layout_principal)   # llena self.acciones_toolbar
        self.crear_panel_principal(layout_principal)

        self.cargar_todos_los_pedidos()
        self.aplicar_estilos()
    
    def crear_barra_estado(self, layout):
        """Crear barra de estado de sincronización"""
        status_frame = QFrame()
        status_frame.setMaximumHeight(26)
        status_frame.setStyleSheet("background-color: #E8F5E8; border-radius: 3px; margin: 0px;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 2, 10, 2)

        self.status_label = QLabel("🔄 Sincronizando automáticamente cada 8 segundos...")
        self.status_label.setStyleSheet("color: #388E3C; font-weight: bold; font-size: 9px;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        # Indicador visual de sincronización
        self.sync_indicator = QLabel("●")
        self.sync_indicator.setStyleSheet("color: #4CAF50; font-size: 11px;")
        status_layout.addWidget(self.sync_indicator)

        layout.addWidget(status_frame)
        
        # Timer para animar el indicador
        self.indicator_timer = QTimer()
        self.indicator_timer.timeout.connect(self.animate_sync_indicator)
        self.indicator_timer.start(1000)  # Parpadear cada segundo
        self.indicator_state = True
    
    def animate_sync_indicator(self):
        """Animar indicador de sincronización"""
        if self.indicator_state:
            self.sync_indicator.setStyleSheet("color: #4CAF50; font-size: 12px;")
        else:
            self.sync_indicator.setStyleSheet("color: #cccccc; font-size: 12px;")
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
    
    def crear_panel_principal(self, layout):
        # Splitter vertical para las 2 secciones
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        # Panel de Pedidos Pendientes (arriba)
        self.crear_panel_pendientes(splitter)

        # Panel de Pedidos Entregados (abajo)
        self.crear_panel_entregados(splitter)

        # Proporción 60/40
        splitter.setSizes([420, 280])
    
    def crear_panel_pendientes(self, parent):
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Título con contador
        titulo_layout = QHBoxLayout()
        self.titulo_pendientes = QLabel("PEDIDOS PENDIENTES")
        self.titulo_pendientes.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.titulo_pendientes.setStyleSheet("color: #1565C0; padding: 5px 10px; background-color: #E3F2FD; border-radius: 4px;")
        titulo_layout.addWidget(self.titulo_pendientes)

        self.contador_pendientes = QLabel("(0)")
        self.contador_pendientes.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.contador_pendientes.setStyleSheet("color: #1565C0; padding-left: 4px;")
        titulo_layout.addWidget(self.contador_pendientes)

        titulo_layout.addStretch()
        layout.addLayout(titulo_layout)

        # Tabla
        self.tabla_pendientes = QTableWidget()
        self.tabla_pendientes.setColumnCount(6)
        self.tabla_pendientes.setHorizontalHeaderLabels([
            "ID", "Cliente", "Fecha Pedido", "Fecha Entrega", "Estado", "Acciones"
        ])
        header = self.tabla_pendientes.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla_pendientes.setColumnWidth(0, 45)
        self.tabla_pendientes.setColumnWidth(2, 95)
        self.tabla_pendientes.setColumnWidth(3, 95)
        self.tabla_pendientes.setColumnWidth(4, 100)
        self.tabla_pendientes.setColumnWidth(5, 65)
        self.tabla_pendientes.verticalHeader().setDefaultSectionSize(30)
        self.tabla_pendientes.verticalHeader().setVisible(False)
        self.tabla_pendientes.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_pendientes.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla_pendientes)

        parent.addWidget(panel)
    
    def crear_panel_entregados(self, parent):
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Título con botón de historial y contador
        titulo_layout = QHBoxLayout()
        self.titulo_entregados = QLabel("PEDIDOS ENTREGADOS — Última Semana")
        self.titulo_entregados.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.titulo_entregados.setStyleSheet("color: #2E7D32; padding: 5px 10px; background-color: #E8F5E8; border-radius: 4px;")
        titulo_layout.addWidget(self.titulo_entregados)

        self.contador_entregados = QLabel("(0)")
        self.contador_entregados.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.contador_entregados.setStyleSheet("color: #2E7D32; padding-left: 4px;")
        titulo_layout.addWidget(self.contador_entregados)

        titulo_layout.addStretch()

        btn_historial = QPushButton("Ver Historial Completo")
        btn_historial.clicked.connect(self.ver_historial_completo)
        btn_historial.setObjectName("btn_historial")
        titulo_layout.addWidget(btn_historial)

        layout.addLayout(titulo_layout)

        # Tabla
        self.tabla_entregados = QTableWidget()
        self.tabla_entregados.setColumnCount(5)
        self.tabla_entregados.setHorizontalHeaderLabels([
            "ID", "Cliente", "Fecha Pedido", "Fecha Entrega", "Acciones"
        ])
        header = self.tabla_entregados.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla_entregados.setColumnWidth(0, 45)
        self.tabla_entregados.setColumnWidth(2, 95)
        self.tabla_entregados.setColumnWidth(3, 95)
        self.tabla_entregados.setColumnWidth(4, 65)
        self.tabla_entregados.verticalHeader().setDefaultSectionSize(30)
        self.tabla_entregados.verticalHeader().setVisible(False)
        self.tabla_entregados.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_entregados.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla_entregados)

        parent.addWidget(panel)
    
    def obtener_conexion(self):
        ip = socket.gethostbyname("DESKTOP-R8E4V7S")
        return psycopg2.connect(
            host= ip,
            database="pedidosMana",
            user="postgres",
            password="manapedidos2025"
        )
    
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
                SELECT p.id_pedido, c.nombre, p.fecha_pedido, p.fecha_entrega, p.estado_pedido
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido IN ('pendiente', 'programado', 'en camino')
                ORDER BY p.fecha_pedido DESC
            """)
            
            pedidos = cursor.fetchall()
            self.tabla_pendientes.setRowCount(len(pedidos))
            
            # Actualizar contador
            self.contador_pendientes.setText(f"({len(pedidos)})")
            
            for i, (id_pedido, cliente, fecha_pedido, fecha_entrega, estado) in enumerate(pedidos):
                self.tabla_pendientes.setItem(i, 0, QTableWidgetItem(str(id_pedido)))
                self.tabla_pendientes.setItem(i, 1, QTableWidgetItem(cliente))
                self.tabla_pendientes.setItem(i, 2, QTableWidgetItem(fecha_pedido.strftime('%d/%m/%Y')))
                self.tabla_pendientes.setItem(i, 3, QTableWidgetItem(
                    fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else "Sin programar"
                ))
                self.tabla_pendientes.setItem(i, 4, QTableWidgetItem(estado.capitalize()))
                
                btn_ver = QPushButton("Ver")
                btn_ver.setStyleSheet("background-color: #4CAF50; color: white; border: none; padding: 4px 8px; border-radius: 3px; font-weight: bold;")
                btn_ver.clicked.connect(lambda checked, pid=id_pedido: self.ver_detalle_pedido(pid))
                self.tabla_pendientes.setCellWidget(i, 5, btn_ver)
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar pedidos pendientes: {str(e)}")
    
    def cargar_pedidos_entregados(self):
        try:
            conn = self.obtener_conexion()
            cursor = conn.cursor()
            
            # Solo pedidos entregados de la última semana
            cursor.execute("""
                SELECT p.id_pedido, c.nombre, p.fecha_pedido, p.fecha_entrega
                FROM Pedido p
                JOIN Cliente c ON p.id_cliente = c.id_cliente
                WHERE p.estado_pedido = 'entregado'
                AND p.fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY p.fecha_pedido DESC
            """)
            
            pedidos = cursor.fetchall()
            self.tabla_entregados.setRowCount(len(pedidos))
            
            # Actualizar contador
            self.contador_entregados.setText(f"({len(pedidos)})")
            
            for i, (id_pedido, cliente, fecha_pedido, fecha_entrega) in enumerate(pedidos):
                self.tabla_entregados.setItem(i, 0, QTableWidgetItem(str(id_pedido)))
                self.tabla_entregados.setItem(i, 1, QTableWidgetItem(cliente))
                self.tabla_entregados.setItem(i, 2, QTableWidgetItem(fecha_pedido.strftime('%d/%m/%Y')))
                self.tabla_entregados.setItem(i, 3, QTableWidgetItem(
                    fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else "Sin fecha"
                ))
                
                btn_ver = QPushButton("Ver")
                btn_ver.setStyleSheet("background-color: #4CAF50; color: white; border: none; padding: 4px 8px; border-radius: 3px; font-weight: bold;")
                btn_ver.clicked.connect(lambda checked, pid=id_pedido: self.ver_detalle_pedido(pid))
                self.tabla_entregados.setCellWidget(i, 4, btn_ver)
            
            cursor.close()
            conn.close()
            
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
            QDialog {
                background-color: #f0f2f5;
            }
            QGroupBox {
                font-size: 11px;
                font-weight: bold;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                margin-top: 4px;
                padding-top: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #555;
            }
            QPushButton#btn_toolbar_primary {
                background-color: #1976D2;
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
                min-width: 110px;
            }
            QPushButton#btn_toolbar_primary:hover {
                background-color: #1565C0;
            }
            QPushButton#btn_toolbar_primary:pressed {
                background-color: #0D47A1;
            }
            QPushButton#btn_toolbar_secondary {
                background-color: #546E7A;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
                min-width: 90px;
            }
            QPushButton#btn_toolbar_secondary:hover {
                background-color: #455A64;
            }
            QPushButton#btn_historial {
                background-color: #EF6C00;
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton#btn_historial:hover {
                background-color: #E65100;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
            QPushButton:disabled {
                background-color: #bdbdbd;
                color: #757575;
            }
            QTableWidget {
                gridline-color: #e0e0e0;
                background-color: white;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                font-size: 11px;
                selection-background-color: #E3F2FD;
                alternate-background-color: #fafafa;
            }
            QTableWidget::item {
                padding: 3px 6px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #BBDEFB;
                color: #1a1a1a;
            }
            QTableWidget::item:hover {
                background-color: #E3F2FD;
            }
            QHeaderView::section {
                background-color: #ECEFF1;
                color: #37474F;
                padding: 5px 6px;
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid #B0BEC5;
            }
            QFrame {
                background-color: white;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                margin: 1px;
            }
            QLineEdit {
                padding: 5px 7px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 11px;
            }
            QComboBox {
                padding: 5px 7px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 11px;
            }
            QSplitter::handle {
                background-color: #CFD8DC;
                height: 4px;
            }
        """)
