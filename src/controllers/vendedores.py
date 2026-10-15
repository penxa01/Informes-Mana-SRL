"""Vendedores del sistema de gestión: código (``VENDEDOR`` de ctaclien) -> nombre.

OJO: la misma tabla está duplicada en ``ui/paginas/litros.py`` (``_VENDEDORES``) y
``ui/paginas/otros.py`` (``_COD_VENDEDOR``), y otra más en ``RangeFechas.py`` /
``rangeMY.py``. Acá queda la copia para Cuentas Corrientes; unificarlas es una
limpieza pendiente (si entra un vendedor nuevo hay que tocar todas).
"""

VENDEDORES = {
    1: "ROMULO SANCHEZ", 3: "MIGUEL ORTUÑO", 4: "JOSE BANCO",
    5: "DIEGO CALDERON", 6: "MATIAS BARATA", 9: "MARTIN MOYA",
}


def nombre_vendedor(codigo):
    """Nombre del vendedor o ``None`` si el código no existe / no es numérico."""
    try:
        return VENDEDORES.get(int(float(str(codigo).strip())))
    except (TypeError, ValueError):
        return None
