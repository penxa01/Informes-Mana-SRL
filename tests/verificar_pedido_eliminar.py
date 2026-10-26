"""Verifica en Pedidos: (1) entregados a la izquierda y pendientes a la derecha,
(2) el boton de eliminar solo esta en pendientes y (3) eliminar borra el pedido
y sus lineas.

La parte de base corre dentro de UNA transaccion que se revierte: commit() y
close() de las conexiones que usa la app quedan anulados.

    QT_QPA_PLATFORM=offscreen python tests/verificar_pedido_eliminar.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton, QSplitter

from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallas.append(nombre)


try:
    real = pp._conexion()
except Exception as e:  # sin base disponible no se puede seguir
    print("SIN BASE:", e)
    sys.exit(1)


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


con = _Proxy(real)
pp._conexion = lambda: con

# Los cuadros de aviso no deben bloquear la prueba; la pregunta se contesta con lo que diga `respuesta`.
respuesta = {"valor": QMessageBox.Yes}
for m in ("information", "warning", "critical"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: None))
QMessageBox.question = staticmethod(lambda *a, **k: respuesta["valor"])

try:
    cur = con.cursor()
    cur.execute("SELECT id_cliente, nombre FROM Cliente LIMIT 1")
    id_cliente, nombre_cliente = cur.fetchone()
    cur.execute("SELECT id_producto FROM Producto LIMIT 1")
    id_prod = cur.fetchone()[0]
    cur.execute("INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido) VALUES (%s, CURRENT_DATE, 'pendiente') "
                "RETURNING id_pedido", (id_cliente,))
    id_pedido = cur.fetchone()[0]
    cur.execute("INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario) VALUES (%s,%s,2,0)",
                (id_pedido, id_prod))

    mgr = pp.DatabaseSyncManager()
    mgr.timer.stop()
    mgr.local_changes_timer.stop()
    ventana = pp.VentanaProgramarPedido(sync_manager=mgr)
    ventana.indicator_timer.stop()
    app.processEvents()

    # ── 1. disposicion ─────────────────────────────────────────────────────
    split = ventana.findChild(QSplitter, "splitPedidos")
    check("las grillas van una al lado de la otra", split.orientation() == Qt.Horizontal)
    check("entregados a la izquierda", split.widget(0).isAncestorOf(ventana.tabla_entregados))
    check("pendientes a la derecha", split.widget(1).isAncestorOf(ventana.tabla_pendientes))

    # ── 2. boton eliminar solo en pendientes ───────────────────────────────
    def fila_de(tabla):
        for r in range(tabla.rowCount()):
            if int(tabla.item(r, 0).text()) == id_pedido:
                return r
        return None

    def botones(tabla, fila):
        return [b.toolTip() for b in tabla.cellWidget(fila, 5).findChildren(QPushButton)]

    fila = fila_de(ventana.tabla_pendientes)
    check("el pedido de prueba esta en pendientes", fila is not None)
    check("pendientes: tiene ver (ojito) y eliminar",
          [t.split(" (")[0] for t in botones(ventana.tabla_pendientes, fila)] == ["Ver detalle", "Eliminar pedido"])
    ojo = ventana.tabla_pendientes.cellWidget(fila, 5).findChildren(QPushButton)[0]
    check("el ojito es un icono, no texto", ojo.text() == "" and not ojo.icon().isNull())

    # un entregado no ofrece el boton
    ventana._fila_pedido(ventana.tabla_entregados, 0, 999999, "X", "", None, None, "entregado")
    check("entregados: solo ver", botones(ventana.tabla_entregados, 0) == ["Ver detalle"])


    def lineas():
        cur.execute("SELECT count(*) FROM DetallePedido WHERE id_pedido=%s", (id_pedido,))
        n_det = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM Pedido WHERE id_pedido=%s", (id_pedido,))
        return n_det, cur.fetchone()[0]

    # ── 3. eliminar ────────────────────────────────────────────────────────
    respuesta["valor"] = QMessageBox.No
    ventana.eliminar_pedido(id_pedido, nombre_cliente)
    check("decir que No no borra nada", lineas() == (1, 1))

    respuesta["valor"] = QMessageBox.Yes
    ventana.eliminar_pedido(id_pedido, nombre_cliente)
    app.processEvents()
    check("decir que Si borra el pedido y sus lineas", lineas() == (0, 0))
    check("la grilla ya no lo muestra", fila_de(ventana.tabla_pendientes) is None)
    check("el estado avisa la baja", str(id_pedido) in ventana.status_label.text())
finally:
    real.rollback()
    real.close()

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
sys.exit(1 if fallas else 0)
