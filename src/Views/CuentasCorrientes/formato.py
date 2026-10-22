"""Formato de números para las pantallas de Cuentas Corrientes."""


def fmt_monto(valor):
    """1234567.5 -> '$ 1.234.567,50'."""
    return f"$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
