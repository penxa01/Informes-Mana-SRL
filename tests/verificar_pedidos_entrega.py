"""Regresión de la gestión de pedidos: entrega completa mueve el pedido a
'Entregados' y se ve al instante.

1. La SQL de `realizar_entrega_completa` deja el pedido 'entregado' con
   fecha_entrega = hoy y sale de la query de 'Pendientes' / entra en la de
   'Entregados (última semana)'.  ← se prueba en una transacción con ROLLBACK
   (no toca datos reales).
2. `DatabaseSyncManager.force_refresh()` emite `pedidos_pendientes_changed` y
   `pedidos_entregados_changed` (antes no emitía nada → los paneles quedaban
   congelados).

Requiere la BD PostgreSQL `pedidosMana` accesible.
Correr desde la raíz:  python tests/verificar_pedidos_entrega.py
"""
import os
import socket
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import PyQt5.QtWidgets as widget

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def conectar():
    ip = socket.gethostbyname("DESKTOP-R8E4V7S")
    return psycopg2.connect(host=ip, database="pedidosMana", user="postgres",
                            password="manapedidos2025", connect_timeout=5)


app = widget.QApplication([])

# ── 1. SQL de entrega completa (transacción + ROLLBACK) ─────────────────────
print("=== 1. entrega completa: SQL en transacción con ROLLBACK ===")
conn = conectar()
cur = conn.cursor()
try:
    cur.execute("SELECT id_cliente FROM Cliente LIMIT 1")
    id_cliente = cur.fetchone()[0]
    cur.execute("SELECT id_producto FROM Producto LIMIT 2")
    prods = [r[0] for r in cur.fetchall()]

    # pedido de prueba PROGRAMADO para una fecha vieja (el caso que se rompía)
    cur.execute("""
        INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega)
        VALUES (%s, CURRENT_DATE - 60, 'programado', CURRENT_DATE - 40)
        RETURNING id_pedido
    """, (id_cliente,))
    pid = cur.fetchone()[0]
    for p in prods:
        # estado_entrega es GENERATED ALWAYS en la BD: no se inserta ni se toca.
        cur.execute("""INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, cantidad_entregada, precio_unitario)
                       VALUES (%s, %s, 5, 0, 0)""", (pid, p))

    # query "Pendientes" del panel
    cur.execute("""SELECT count(*) FROM Pedido WHERE id_pedido=%s
                   AND estado_pedido IN ('pendiente','programado','en camino')""", (pid,))
    check("antes: el pedido está en Pendientes", cur.fetchone()[0] == 1)

    # --- SQL de realizar_entrega_completa (idéntica a la del código) ---
    cur.execute("UPDATE DetallePedido SET cantidad_entregada = cantidad WHERE id_pedido = %s", (pid,))
    cur.execute("UPDATE Pedido SET estado_pedido = 'entregado', fecha_entrega = CURRENT_DATE WHERE id_pedido = %s", (pid,))

    cur.execute("SELECT estado_pedido, fecha_entrega FROM Pedido WHERE id_pedido=%s", (pid,))
    estado, fentrega = cur.fetchone()
    check("después: estado = 'entregado'", estado == "entregado", estado)
    cur.execute("SELECT fecha_entrega = CURRENT_DATE FROM Pedido WHERE id_pedido=%s", (pid,))
    check("después: fecha_entrega = hoy (no la programada vieja)", cur.fetchone()[0] is True, str(fentrega))

    cur.execute("""SELECT count(*) FROM Pedido WHERE id_pedido=%s
                   AND estado_pedido IN ('pendiente','programado','en camino')""", (pid,))
    check("después: YA NO está en Pendientes", cur.fetchone()[0] == 0)
    cur.execute("""SELECT count(*) FROM Pedido WHERE id_pedido=%s
                   AND estado_pedido='entregado' AND fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'""", (pid,))
    check("después: SÍ está en Entregados (última semana)", cur.fetchone()[0] == 1)

    cur.execute("SELECT count(*) FROM DetallePedido WHERE id_pedido=%s AND estado_entrega='completa'", (pid,))
    check("líneas de detalle marcadas 'completa'", cur.fetchone()[0] == len(prods))

    cur.execute("SELECT count(*) FROM DetallePedido WHERE id_pedido=%s AND cantidad_entregada < cantidad", (pid,))
    check("no quedan líneas con cantidad pendiente", cur.fetchone()[0] == 0)
finally:
    conn.rollback()   # nada de esto se persiste
    cur.close()
    conn.close()
print("   (rollback hecho: la BD real quedó intacta)")

# ── 2. force_refresh() emite las dos señales ────────────────────────────────
print("=== 2. DatabaseSyncManager.force_refresh() recarga los paneles ===")
from src.Views.Pedidos.programarPedido import DatabaseSyncManager

mgr = DatabaseSyncManager()
mgr.timer.stop()  # no queremos el poll de 8s corriendo durante el test

contador = {"pend": 0, "entr": 0}
mgr.pedidos_pendientes_changed.connect(lambda: contador.__setitem__("pend", contador["pend"] + 1))
mgr.pedidos_entregados_changed.connect(lambda: contador.__setitem__("entr", contador["entr"] + 1))

mgr.force_refresh()
app.processEvents()

check("force_refresh emitió pedidos_pendientes_changed", contador["pend"] >= 1, str(contador))
check("force_refresh emitió pedidos_entregados_changed", contador["entr"] >= 1, str(contador))
check("baseline quedó sincronizado (hash no vacío)",
      mgr.last_pendientes_hash != "" and mgr.last_entregados_hash != "")
check("cambios_locales se reseteó a False tras el check", mgr.cambios_locales is False)
mgr.local_changes_timer.stop()

# ── 3. flujo completo en la ventana real (crea/borra un pedido de prueba) ───
print("=== 3. VentanaProgramarPedido: el pedido entregado sale de Pendientes ===")
from src.Views.Pedidos.programarPedido import VentanaProgramarPedido

mgr2 = DatabaseSyncManager()
mgr2.timer.stop()
ventana = VentanaProgramarPedido(sync_manager=mgr2)
app.processEvents()

conn = conectar()
conn.autocommit = True
cur = conn.cursor()
pid = None
try:
    cur.execute("SELECT id_cliente FROM Cliente LIMIT 1")
    id_cliente = cur.fetchone()[0]
    cur.execute("SELECT id_producto FROM Producto LIMIT 1")
    id_prod = cur.fetchone()[0]
    cur.execute("""INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido)
                   VALUES (%s, CURRENT_DATE, 'pendiente') RETURNING id_pedido""", (id_cliente,))
    pid = cur.fetchone()[0]
    cur.execute("""INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, cantidad_entregada, precio_unitario)
                   VALUES (%s, %s, 3, 0, 0)""", (pid, id_prod))

    ventana.cargar_pedidos_pendientes()
    ventana.cargar_pedidos_entregados()
    app.processEvents()

    def ids_en(tabla):
        return {int(tabla.item(r, 0).text()) for r in range(tabla.rowCount())}

    check("el pedido de prueba aparece en Pendientes", pid in ids_en(ventana.tabla_pendientes))
    check("el pedido de prueba NO está en Entregados todavía", pid not in ids_en(ventana.tabla_entregados))

    # entrega completa (SQL del código) + el force_refresh arreglado
    cur.execute("UPDATE DetallePedido SET cantidad_entregada = cantidad WHERE id_pedido = %s", (pid,))
    cur.execute("UPDATE Pedido SET estado_pedido='entregado', fecha_entrega=CURRENT_DATE WHERE id_pedido=%s", (pid,))
    mgr2.force_refresh()
    app.processEvents()

    check("tras entregar: el pedido SALIÓ de Pendientes", pid not in ids_en(ventana.tabla_pendientes))
    check("tras entregar: el pedido ESTÁ en Entregados", pid in ids_en(ventana.tabla_entregados))
finally:
    if pid is not None:
        cur.execute("DELETE FROM DetallePedido WHERE id_pedido = %s", (pid,))
        cur.execute("DELETE FROM Pedido WHERE id_pedido = %s", (pid,))
    cur.close()
    conn.close()
    mgr2.local_changes_timer.stop()
print("   (pedido de prueba borrado)")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
