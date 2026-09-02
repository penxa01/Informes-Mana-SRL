"""Sección LITROS (incluye Sell In como modo). Se implementa en F2a."""
from src.ui.paginas._stub import PaginaStub


class PaginaLitros(PaginaStub):
    titulo = "Litros"
    fase = "F2a"
    necesita_ventas = True
