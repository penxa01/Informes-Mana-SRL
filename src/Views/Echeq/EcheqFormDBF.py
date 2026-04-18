import PyQt5.QtWidgets as widget

class Form(widget.QDialog):
    """Formulario para ingresar datos de un cheque."""
    def __init__(self, campos):
        super().__init__()
        self.setWindowTitle("Añadir Cheque")
        self.setModal(True)
        self.campos = campos
        self.datos = {}

        # Layout principal
        self.layout = widget.QGridLayout(self)

        # Campos de entrada
        self.inputs = {}
        for idx, campo in enumerate(campos):
            label = widget.QLabel(campo)
            input_field = widget.QLineEdit()
            self.inputs[campo] = input_field

            # Añadir el label y el campo de entrada al layout
            row = idx // 2  # Dos columnas
            col = idx % 2   # Alternar entre dos columnas
            self.layout.addWidget(label, row, col * 2)  # Columna para el label
            self.layout.addWidget(input_field, row, col * 2 + 1)  # Columna para el input

        # Botones
        self.botones = widget.QHBoxLayout()
        self.boton_guardar = widget.QPushButton("Guardar")
        self.boton_guardar.clicked.connect(self.accept)
        self.botones.addWidget(self.boton_guardar)

        self.boton_cancelar = widget.QPushButton("Cancelar")
        self.boton_cancelar.clicked.connect(self.reject)
        self.botones.addWidget(self.boton_cancelar)

        # Añadir los botones al layout principal
        self.layout.addLayout(self.botones, len(campos) // 2 + 1, 0, 1, 2)  # Colocar botones en la última fila

        # Ajustar el espaciado
        self.layout.setSpacing(10)  # Espaciado entre widgets
        self.layout.setContentsMargins(10, 10, 10, 10)  # Márgenes del layout

    def obtener_datos(self):
        """Obtener los datos ingresados en el formulario."""
        for campo, input_field in self.inputs.items():
            self.datos[campo] = input_field.text()
        return self.datos