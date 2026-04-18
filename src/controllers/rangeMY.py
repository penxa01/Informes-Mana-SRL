from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QDialogButtonBox, QMessageBox
)
import datetime


class DateYearRangeDialog(QDialog):
    def __init__(self, parent=None, enable_seller=True):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Período y Vendedor")

        # Layout principal
        layout = QVBoxLayout()

        # Desplegable para la fecha inicial
        layout.addWidget(QLabel("Fecha Desde (MM/YYYY):"))
        self.fecha_desde = QComboBox()
        self.llenar_combo_fechas(self.fecha_desde)
        self.fecha_desde.currentTextChanged.connect(self.on_fecha_desde_changed)
        layout.addWidget(self.fecha_desde)
        
        # Campo manual para fecha desde (inicialmente oculto)
        self.fecha_desde_manual = QLineEdit()
        self.fecha_desde_manual.setPlaceholderText("dd/mm")
        self.fecha_desde_manual.setVisible(False)
        layout.addWidget(self.fecha_desde_manual)

        # Desplegable para la fecha final
        layout.addWidget(QLabel("Fecha Hasta (MM/YYYY):"))
        self.fecha_hasta = QComboBox()
        self.llenar_combo_fechas(self.fecha_hasta)
        self.fecha_hasta.currentTextChanged.connect(self.on_fecha_hasta_changed)
        layout.addWidget(self.fecha_hasta)
        
        # Campo manual para fecha hasta (inicialmente oculto)
        self.fecha_hasta_manual = QLineEdit()
        self.fecha_hasta_manual.setPlaceholderText("dd/mm")
        self.fecha_hasta_manual.setVisible(False)
        layout.addWidget(self.fecha_hasta_manual)

        # Desplegable para seleccionar Vendedor
        layout.addWidget(QLabel("Seleccionar Vendedor:"))
        self.combo_vendedor = QComboBox()
        self.combo_vendedor.setEnabled(enable_seller)
        self.vendedor_mapping = {
            "1": "ROMULO SANCHEZ",
            "3": "MIGUEL ORTUÑO",
            "4": "JOSE BANCO",
            "5": "DIEGO CALDERON",
            "6": "MATIAS BARATA",
            "9": "MARTIN MOYA"
        }

        # Agregar opción TODOS y vendedores al desplegable
        self.combo_vendedor.addItem("TODOS")  # Opción predeterminada
        for numero, nombre in self.vendedor_mapping.items():
            self.combo_vendedor.addItem(nombre, numero)

        layout.addWidget(self.combo_vendedor)

        # Botones Aceptar y Cancelar
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.validar_fechas)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

        self.setLayout(layout)

    def llenar_combo_fechas(self, combo):
        """
        Llena el combo con fechas en formato MM/YYYY desde hace 2 años hasta la fecha actual.
        """
        hoy = datetime.date.today()
        fecha_limite = datetime.date(hoy.year - 2, hoy.month, 1)
        
        # Lista para almacenar las fechas
        fechas = []
        
        # Generar fechas desde la fecha límite hasta hoy
        fecha_actual = fecha_limite
        while fecha_actual <= hoy:
            fecha_str = fecha_actual.strftime("%m/%Y")
            fechas.append((fecha_str, fecha_actual))
            
            # Avanzar al siguiente mes
            if fecha_actual.month == 12:
                fecha_actual = datetime.date(fecha_actual.year + 1, 1, 1)
            else:
                fecha_actual = datetime.date(fecha_actual.year, fecha_actual.month + 1, 1)
        
        # Llenar el combo (en orden cronológico inverso para que la fecha más reciente esté arriba)
        fechas.reverse()
        for fecha_str, fecha_obj in fechas:
            combo.addItem(fecha_str, fecha_obj)
        
        # Agregar opción manual al final
        combo.addItem("MANUAL", "manual")

    def on_fecha_desde_changed(self, text):
        """Mostrar/ocultar campo manual para fecha desde"""
        if text == "MANUAL":
            self.fecha_desde_manual.setVisible(True)
        else:
            self.fecha_desde_manual.setVisible(False)

    def on_fecha_hasta_changed(self, text):
        """Mostrar/ocultar campo manual para fecha hasta"""
        if text == "MANUAL":
            self.fecha_hasta_manual.setVisible(True)
        else:
            self.fecha_hasta_manual.setVisible(False)

    def completar_fecha(self, fecha_str):
        """
        Completa el año actual si no está incluido en la fecha ingresada.
        """
        hoy = datetime.date.today()
        partes = fecha_str.split("/")

        if len(partes) == 2:  # Formato dd/mm
            dia, mes = map(int, partes)
            return datetime.date(hoy.year, mes, dia)
        elif len(partes) == 3:  # Formato dd/mm/yyyy
            dia, mes, anio = map(int, partes)
            return datetime.date(anio, mes, dia)
        else:
            raise ValueError("Formato de fecha inválido. Use dd/mm o dd/mm/yyyy.")

    def validar_fechas(self):
        try:
            # Procesar fecha desde
            if self.fecha_desde.currentText() == "MANUAL":
                if not self.fecha_desde_manual.text().strip():
                    raise ValueError("Debe ingresar una fecha manual para 'Desde'.")
                fecha_desde = self.completar_fecha(self.fecha_desde_manual.text().strip())
                self.fecha_desde_manual_seleccionada = True
            else:
                fecha_desde = self.fecha_desde.currentData()
                self.fecha_desde_manual_seleccionada = False

            # Procesar fecha hasta
            if self.fecha_hasta.currentText() == "MANUAL":
                if not self.fecha_hasta_manual.text().strip():
                    raise ValueError("Debe ingresar una fecha manual para 'Hasta'.")
                fecha_hasta = self.completar_fecha(self.fecha_hasta_manual.text().strip())
                self.fecha_hasta_manual_seleccionada = True
            else:
                fecha_hasta = self.fecha_hasta.currentData()
                self.fecha_hasta_manual_seleccionada = False

            # Validar que "desde" no sea mayor que "hasta"
            if fecha_desde > fecha_hasta:
                raise ValueError("La fecha inicial no puede ser mayor que la fecha final.")

            # Guardar las fechas procesadas
            self.fecha_desde_procesada = fecha_desde
            self.fecha_hasta_procesada = fecha_hasta

            # Guardar el vendedor seleccionado
            vendedor_seleccionado = self.combo_vendedor.currentText()
            if vendedor_seleccionado == "TODOS":
                self.vendedor_procesado = None  # Sin filtro de vendedor
            else:
                self.vendedor_procesado = int(self.combo_vendedor.currentData())  # Número del vendedor

            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Error en las Fechas", str(e))