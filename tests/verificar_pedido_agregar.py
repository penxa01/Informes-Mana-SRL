"""Verifica en Pedidos: (1) la fecha de entrega se refleja al recargar la grilla
y (2) agregar productos a un pedido ya creado.

La parte de base corre dentro de UNA transaccion que se revierte: commit() y
close() de las conexiones que usa la app quedan anulados.

    QT_QPA_PLATFORM=offscreen python tests/verificar_pedido_agregar.py
"""
import datetime as dt
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMessageBox, QTableWidget

from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallas.append(nombre)


# Los cuadros de aviso no deben bloquear la prueba.
for m in ("information", "warning", "critical"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: None))

# ── 1. la celda de fecha no queda tapada por el chip "Sin programar" ──────────
tabla = QTableWidget(1, 6)
ventana = pp.VentanaProgramarPedido.__new__(pp.VentanaProgramarPedido)
hoy = dt.date(2026, 10, 21)
pp.VentanaProgramarPedido._fila_pedido(ventana, tabla, 0, 1, "Cliente", "20", hoy, None, "pendiente")
check("sin fecha: hay chip", tabla.cellWidget(0, 3) is not None)
pp.VentanaProgramarPedido._fila_pedido(ventana, tabla, 0, 1, "Cliente", "20", hoy, hoy, "programado")
check("con fecha: el chip viejo desaparece", tabla.cellWidget(0, 3) is None)
check("con fecha: se ve el texto", tabla.item(0, 3) is not None and tabla.item(0, 3).text() == "21/10/2026")

# ── 2. agregar productos (transaccion revertida) ──────────────────────────────
try:
    con = pp._conexion()
except Exception as e:  # sin base disponible no se puede seguir
    print("SIN BASE:", e)
    sys.exit(1 if fallas else 0)

class _Proxy:
    """commit() y close() no hacen nada: todo se revierte al final."""
    def __init__(self, real):
        self._real = real

    def commit(self):
        pass

    def close(self):
        pass

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


real = con
con = _Proxy(real)
pp._conexion = lambda: con

try:
    cur = con.cursor()
    cur.execute("SELECT id_cliente FROM Cliente LIMIT 1")
    id_cliente = cur.fetchone()[0]
    cur.execute("SELECT id_producto FROM Producto ORDER BY id_producto LIMIT 2")
    prods = [r[0] for r in cur.fetchall()]
    cur.execute("INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido) VALUES (%s, CURRENT_DATE, 'pendiente') "
                "RETURNING id_pedido", (id_cliente,))
    id_pedido = cur.fetchone()[0]
    cur.execute("INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario) VALUES (%s,%s,2,0)",
                (id_pedido, prods[0]))

    d = pp.VentanaDetallePedido(id_pedido, None, None)
    check("pedido pendiente: barra de agregar habilitada", not d._barra_agregar.isHidden())
    check("catalogo cargado en el combo", d.combo_producto.count() > 0)

    def cantidad(prod):
        cur.execute("SELECT cantidad FROM DetallePedido WHERE id_pedido=%s AND id_producto=%s", (id_pedido, prod))
        return [r[0] for r in cur.fetchall()]

    # producto nuevo -> fila nueva
    d.line_producto.setText(str(prods[1]))
    idx = d.combo_producto.findData((prods[1], dict(d.todos_los_productos)[prods[1]]))
    d.combo_producto.setCurrentIndex(max(idx, 0))
    d.spin_cantidad.setValue(3)
    d.agregar_producto()
    check("producto nuevo: se inserta con su cantidad", cantidad(prods[1]) == [3])
    check("grilla muestra 2 articulos", d.tabla_productos.rowCount() == 2)

    # producto existente -> suma
    d.line_producto.setText(str(prods[0]))
    d.combo_producto.setCurrentIndex(max(d.combo_producto.findData((prods[0], dict(d.todos_los_productos)[prods[0]])), 0))
    d.spin_cantidad.setValue(5)
    d.agregar_producto()
    check("producto existente: suma 2+5 sin duplicar fila", cantidad(prods[0]) == [7])
    check("la grilla sigue en 2 articulos", d.tabla_productos.rowCount() == 2)
    check("el pendiente de entrega refleja lo nuevo", d.tabla_entrega_parcial.rowCount() == 2)

    # pedido entregado -> no se puede
    cur.execute("UPDATE DetallePedido SET cantidad_entregada = cantidad WHERE id_pedido=%s", (id_pedido,))
    cur.execute("UPDATE Pedido SET estado_pedido='entregado', fecha_entrega=CURRENT_DATE WHERE id_pedido=%s",
                (id_pedido,))
    d.cargar_datos_pedido()
    check("entregado: se oculta la barra", d._barra_agregar.isHidden())
    d.agregar_producto()
    check("entregado: agregar no modifica nada", cantidad(prods[0]) == [7] and d.tabla_productos.rowCount() == 2)
finally:
    real.rollback()
    real.close()

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
sys.exit(1 if fallas else 0)
