from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QDialogButtonBox, QMessageBox
)
import datetime
import pandas as pd


class DateRangeDialog(QDialog):
    def __init__(self,parent = None,enable_seller=True):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Período y Vendedor")

        # Layout principal
        layout = QVBoxLayout()

        # Campo para la fecha inicial
        layout.addWidget(QLabel("Fecha Desde (dd/mm o dd/mm/yyyy):"))
        self.fecha_desde = QLineEdit()
        layout.addWidget(self.fecha_desde)

        # Campo para la fecha final
        layout.addWidget(QLabel("Fecha Hasta (dd/mm o dd/mm/yyyy):"))
        self.fecha_hasta = QLineEdit()
        layout.addWidget(self.fecha_hasta)

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

    def validar_fechas(self):
        try:
            fecha_desde = self.completar_fecha(self.fecha_desde.text())
            fecha_hasta = self.completar_fecha(self.fecha_hasta.text())

            # Validar que "desde" no sea mayor que "hasta"
            if fecha_desde > fecha_hasta:
                raise ValueError("La fecha inicial no puede ser mayor que la fecha final.")

            # Guardar las fechas procesadas como pd.Timestamp para compatibilidad con pandas
            self.fecha_desde_procesada = pd.Timestamp(fecha_desde)
            self.fecha_hasta_procesada = pd.Timestamp(fecha_hasta)

            # Guardar el vendedor seleccionado
            vendedor_seleccionado = self.combo_vendedor.currentText()
            if vendedor_seleccionado == "TODOS":
                self.vendedor_procesado = None  # Sin filtro de vendedor
            else:
                self.vendedor_procesado = int(self.combo_vendedor.currentData())  # Número del vendedor

            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Error en las Fechas", str(e))

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
