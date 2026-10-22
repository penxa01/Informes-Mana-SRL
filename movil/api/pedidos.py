"""Reglas de negocio de un pedido cargado desde el celular: las mismas
validaciones que ya aplica la PC (ver `programarPedido.py`), para que un
pedido `origen='movil'` no se distinga de uno de escritorio salvo por eso.
"""
MAX_LINEAS = 100
CANTIDAD_MIN = 1
CANTIDAD_MAX = 9999


def validar_lineas(lineas):
    """`lineas` es una lista de `(id_producto, cantidad)`. Suma las líneas
    repetidas (mismo producto cargado dos veces) y valida cantidades. Lanza
    `ValueError` con el motivo; si no, devuelve la lista ya sumada."""
    if not lineas:
        raise ValueError("El pedido no tiene productos")
    merge = {}
    orden = []
    for id_producto, cantidad in lineas:
        if not (CANTIDAD_MIN <= cantidad <= CANTIDAD_MAX):
            raise ValueError(f"Cantidad inválida para {id_producto}: {cantidad}")
        if id_producto not in merge:
            orden.append(id_producto)
        merge[id_producto] = merge.get(id_producto, 0) + cantidad
    if len(orden) > MAX_LINEAS:
        raise ValueError(f"Demasiados productos distintos (máximo {MAX_LINEAS})")
    return [(id_producto, merge[id_producto]) for id_producto in orden]
