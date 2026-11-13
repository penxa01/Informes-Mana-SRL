"""Entrega parcial en la PC (src/Views/Pedidos/programarPedido.py, `VentanaDetallePedido.realizar_entrega_parcial`):
si queda algo por entregar el pedido VUELVE A 'pendiente', sin fecha de entrega y con lo que falta (la misma regla que
el celular: movil/api/db.py, `entrega_parcial`); si no queda nada, pasa a 'entregado' con la fecha de hoy; y si no se
entregó nada, queda como estaba.

Corre dentro de UNA transacción que se revierte: commit() y close() de las conexiones que usa la app quedan
anulados, así que no queda nada en la base real.

    QT_QPA_PLATFORM=offscreen python tests/verificar_pedido_entrega_parcial.py
"""
import os
import sys
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMessageBox

from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond, extra=""):
    print(("OK   " if cond else "FALLA"), nombre, extra)
    if not cond:
        fallas.append(nombre)


mensajes = []
for m in ("information", "critical", "warning"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: mensajes.append(" ".join(str(x) for x in a[1:]))))

try:
    real = pp._conexion()
except Exception as e:  # sin base disponible no se puede seguir
    print("SIN BASE:", e)
    sys.exit(1)


class _Proxy:
    """commit(), rollback() y close() no hacen nada: todo se revierte al final, con la conexión real."""
    def __init__(self, real):
        self._real = real

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


real.autocommit = False
con = _Proxy(real)
pp._conexion = lambda: con
cur = con.cursor()
hoy = date.today()


def estado_de(pid):
    cur.execute("SELECT estado_pedido, fecha_entrega FROM pedido WHERE id_pedido = %s", (pid,))
    return cur.fetchone()


def entregadas(pid):
    cur.execute("SELECT cantidad_entregada FROM detallepedido WHERE id_pedido = %s ORDER BY id_detalle", (pid,))
    return [r[0] for r in cur.fetchall()]


def entregar(ventana, cantidades):
    """Pone esas cantidades en los spinbox de la tabla de entrega parcial (en orden) y aprieta "Entrega Parcial"."""
    mensajes.clear()
    for i, n in enumerate(cantidades):
        ventana.tabla_entrega_parcial.cellWidget(i, 3).setValue(n)
    ventana.realizar_entrega_parcial()


try:
    cur.execute("SELECT id_producto FROM producto ORDER BY id_producto LIMIT 3")
    productos = [r[0] for r in cur.fetchall()]
    cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega) "
                "SELECT id_cliente, CURRENT_DATE, 'programado', %s FROM cliente ORDER BY id_cliente LIMIT 1 RETURNING id_pedido",
                (hoy + timedelta(days=2),))
    pid = cur.fetchone()[0]
    for prod, cant in zip(productos, (5, 2, 4)):
        cur.execute("INSERT INTO detallepedido (id_pedido, id_producto, cantidad, cantidad_entregada, precio_unitario) "
                    "VALUES (%s, %s, %s, 0, 0)", (pid, prod, cant))

    v = pp.VentanaDetallePedido(pid, None, None)
    cambios = []
    v.pedido_updated.connect(cambios.append)

    print("=== entrega parcial que deja algo sin entregar ===")
    entregar(v, [2, 0, 0])   # 2 de 5 de la primera línea
    check("se anota lo entregado", entregadas(pid) == [2, 0, 0], entregadas(pid))
    check("el pedido VUELVE A PENDIENTE y sin fecha de entrega (había sido programado)", estado_de(pid) == ("pendiente", None), estado_de(pid))
    check("avisa que vuelve a pendiente", any("Pendiente" in m for m in mensajes), mensajes)
    check("avisa al resto de la PC que el pedido cambió", cambios == [pid], cambios)
    check("la tabla de entrega parcial muestra solo lo que falta (3 + 2 + 4)",
          [v.tabla_entrega_parcial.item(i, 2).text() for i in range(v.tabla_entrega_parcial.rowCount())] == ["3", "2", "4"])

    print("=== sin entregar nada: queda como estaba ===")
    cur.execute("UPDATE pedido SET estado_pedido = 'programado', fecha_entrega = %s WHERE id_pedido = %s", (hoy, pid))
    entregar(v, [0, 0, 0])
    check("no cambia el estado ni la fecha", estado_de(pid) == ("programado", hoy), estado_de(pid))
    check("no cambia lo entregado", entregadas(pid) == [2, 0, 0])

    print("=== otra entrega parcial más (de un pedido 'en camino') ===")
    cur.execute("UPDATE pedido SET estado_pedido = 'en camino' WHERE id_pedido = %s", (pid,))
    entregar(v, [0, 2, 0])
    check("vuelve a pendiente también desde 'en camino'", estado_de(pid) == ("pendiente", None) and entregadas(pid) == [2, 2, 0], (estado_de(pid), entregadas(pid)))

    print("=== la que completa todo ===")
    entregar(v, [3, 4])   # la tabla ya no trae la línea 2 (completa): quedan la 1 (faltan 3) y la 3 (faltan 4)
    check("queda todo entregado", entregadas(pid) == [5, 2, 4], entregadas(pid))
    check("el pedido pasa a 'entregado' con la fecha de HOY", estado_de(pid) == ("entregado", hoy), estado_de(pid))
    check("y no avisa que vuelve a pendiente", not any("vuelve a Pendiente" in m for m in mensajes), mensajes)
finally:
    real.rollback()
    real.close()

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S): {fallas}")
sys.exit(1 if fallas else 0)
