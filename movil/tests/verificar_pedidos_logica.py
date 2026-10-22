"""Validación de líneas de un pedido (movil/api/pedidos.py): sin base.

Correr desde la raíz:  python movil/tests/verificar_pedidos_logica.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from movil.api import pedidos

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def lanza(fn, *args, **kw):
    try:
        fn(*args, **kw)
        return None
    except ValueError as e:
        return str(e)


print("=== validar_lineas ===")
check("pedido vacío", lanza(pedidos.validar_lineas, []) is not None)
check("una línea normal", pedidos.validar_lineas([("01VA133", 5)]) == [("01VA133", 5)])
check("líneas repetidas se suman", pedidos.validar_lineas([("01VA133", 5), ("01VA133", 3)]) == [("01VA133", 8)])
check("mantiene el orden de aparición",
      pedidos.validar_lineas([("B", 1), ("A", 1), ("B", 2)]) == [("B", 3), ("A", 1)])
check("cantidad mínima (1) ok", pedidos.validar_lineas([("A", 1)]) == [("A", 1)])
check("cantidad máxima (9999) ok", pedidos.validar_lineas([("A", 9999)]) == [("A", 9999)])
check("cantidad 0 inválida", lanza(pedidos.validar_lineas, [("A", 0)]) is not None)
check("cantidad negativa inválida", lanza(pedidos.validar_lineas, [("A", -1)]) is not None)
check("cantidad 10000 inválida", lanza(pedidos.validar_lineas, [("A", 10000)]) is not None)

lineas_al_limite = [(f"P{i}", 1) for i in range(pedidos.MAX_LINEAS)]
check(f"{pedidos.MAX_LINEAS} productos distintos: ok", len(pedidos.validar_lineas(lineas_al_limite)) == pedidos.MAX_LINEAS)
lineas_de_mas = lineas_al_limite + [("PX", 1)]
check(f"{pedidos.MAX_LINEAS + 1} productos distintos: rechazado", lanza(pedidos.validar_lineas, lineas_de_mas) is not None)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
