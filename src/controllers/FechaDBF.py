import PyQt5.QtWidgets as widget
from datetime import datetime, date

class Fecha(widget.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Fecha")
        
        # Configurar la disposición del diálogo
        layout = widget.QVBoxLayout()

        # Campo de entrada para la fecha
        self.input_fecha = widget.QLineEdit(self)
        self.input_fecha.setPlaceholderText("dd/mm/yyyy, dd/mm o dd")
        
        # Botón de aceptar
        self.boton_aceptar = widget.QPushButton("Aceptar", self)
        self.boton_aceptar.clicked.connect(self.aceptar)

        # Agregar widgets al layout
        layout.addWidget(widget.QLabel("Ingrese la fecha en formato dd/mm/yyyy, dd/mm o dd:"))
        layout.addWidget(self.input_fecha)
        layout.addWidget(self.boton_aceptar)

        self.setLayout(layout)

    def aceptar(self):
        fecha = self.input_fecha.text().strip()
        hoy = date.today()
        
        try:
            if '/' not in fecha:  # Formato: dd
                fecha = f"{fecha}/{hoy.month}/{hoy.year}"
            elif fecha.count('/') == 1:  # Formato: dd/mm
                fecha = f"{fecha}/{hoy.year}"
            
            # Validar la fecha final
            fecha_valida = datetime.strptime(fecha, "%d/%m/%Y")
            self.input_fecha.setText(fecha_valida.strftime("%d/%m/%Y"))  # Formatea correctamente
            self.accept()
        
        except ValueError:
            msg_box = widget.QMessageBox()
            msg_box.setIcon(widget.QMessageBox.Warning)
            msg_box.setWindowTitle("Fecha Inválida")
            msg_box.setText("Por favor ingrese una fecha válida en formato dd/mm/yyyy, dd/mm o dd.")
            msg_box.setStandardButtons(widget.QMessageBox.Ok)
            msg_box.exec_()
