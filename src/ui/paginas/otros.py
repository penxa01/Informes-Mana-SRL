"""Sección OTROS (Thalamus / Ventas Mensuales / IIBB / Actualizar Precios). Se implementa en F2e."""
from src.ui.paginas._stub import PaginaStub


class PaginaOtros(PaginaStub):
    titulo = "Otros"
    fase = "F2e"
    necesita_ventas = True
