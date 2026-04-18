import sys
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton

class MesAnioDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Mes, Año y Jurisdicción")

        # Diccionario de meses con sus números correspondientes
        self.meses = {
            "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
            "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
        }
        
        # Diccionario de jurisdicciones
        self.jurisdicciones = {
            "San Juan": 1,
            "Mendoza": 3
        }

        # Layout principal
        layout = QVBoxLayout()

        # Desplegable para seleccionar el mes
        self.label_mes = QLabel("Selecciona el mes:")
        self.combo_mes = QComboBox()
        self.combo_mes.addItems(self.meses.keys())  # Agregar nombres de los meses

        # Campo de entrada para el año
        self.label_anio = QLabel("Ingresa el año:")
        self.input_anio = QLineEdit()
        self.input_anio.setPlaceholderText("Ejemplo: 2025")
        
        # Desplegable para seleccionar jurisdicción
        self.label_jurisdiccion = QLabel("Selecciona la jurisdicción:")
        self.combo_jurisdiccion = QComboBox()
        self.combo_jurisdiccion.addItems(self.jurisdicciones.keys())

        # Botón de aceptar
        self.boton_aceptar = QPushButton("Aceptar")
        self.boton_aceptar.clicked.connect(self.aceptar)

        # Agregar widgets al layout
        layout.addWidget(self.label_mes)
        layout.addWidget(self.combo_mes)
        layout.addWidget(self.label_anio)
        layout.addWidget(self.input_anio)
        layout.addWidget(self.label_jurisdiccion)
        layout.addWidget(self.combo_jurisdiccion)
        layout.addWidget(self.boton_aceptar)

        self.setLayout(layout)

        # Atributos para guardar los valores seleccionados
        self.mes_seleccionado = None
        self.anio_seleccionado = None
        self.jurisdiccion_seleccionada = None
        self.jurisdiccion_nombre = None

    def aceptar(self):
        mes_nombre = self.combo_mes.currentText()
        mes_numero = self.meses[mes_nombre]  # Obtener el número del mes seleccionado
        anio = self.input_anio.text()
        
        jurisdiccion_nombre = self.combo_jurisdiccion.currentText()
        jurisdiccion_numero = self.jurisdicciones[jurisdiccion_nombre]

        if anio.isdigit():  # Verificar si el año ingresado es un número
            self.mes_seleccionado = mes_numero
            self.anio_seleccionado = int(anio)
            self.jurisdiccion_seleccionada = jurisdiccion_numero
            self.jurisdiccion_nombre = jurisdiccion_nombre
            self.accept()  # Cierra la ventana
        else:
            self.label_anio.setText("Ingresa un año válido:")