"""Quitar un artículo del detalle de un pedido en la PC (src/Views/Pedidos/programarPedido.py): la regla
(`_motivo_no_quitable` y `_quitar_linea_pedido`, la misma que usa el celular) y la X de la tabla del detalle.

Corre dentro de UNA transacción que se revierte: commit() y close() de las conexiones que usa la app quedan
anulados, así que no queda nada en la base real.

    QT_QPA_PLATFORM=offscreen python tests/verificar_pedido_quitar_articulo.py
"""
import os
import sys
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton

from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond, extra=""):
    print(("OK   " if cond else "FALLA"), nombre, extra)
    if not cond:
        fallas.append(nombre)


avisos = []   # los cuadros no bloquean la prueba, pero se anotan
preguntas = []
respuesta = {"valor": QMessageBox.Yes}
QMessageBox.information = staticmethod(lambda *a, **k: avisos.append(("info", " ".join(str(x) for x in a[1:]))))
QMessageBox.critical = staticmethod(lambda *a, **k: avisos.append(("error", " ".join(str(x) for x in a[1:]))))
QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(("aviso", " ".join(str(x) for x in a[1:]))))
QMessageBox.question = staticmethod(lambda *a, **k: preguntas.append(" ".join(str(x) for x in a[1:3])) or respuesta["valor"])

# ── 1. la regla pura ──────────────────────────────────────────────────────────
print("=== motivo por el que no se puede quitar ===")
check("con otros artículos y sin entregas: se puede", pp._motivo_no_quitable(3, 0) is None)
check("el único artículo no se quita (para eso está eliminar el pedido)", "único artículo" in (pp._motivo_no_quitable(1, 0) or ""))
check("uno del que ya se entregó algo no se quita", "ya se entregó" in (pp._motivo_no_quitable(3, 2) or ""))
check("si pasan las dos cosas, se explica la de lo entregado (la más grave)", "ya se entregó" in (pp._motivo_no_quitable(1, 2) or ""))

# ── 2. con base (transacción revertida) ───────────────────────────────────────
try:
    real = pp._conexion()
except Exception as e:  # sin base disponible no se puede seguir
    print("SIN BASE:", e)
    sys.exit(1 if fallas else 0)


class _Proxy:
    """commit(), rollback() y close() no hacen nada: todo se revierte al final, con la conexión real (un rollback
    de la app, por un error simulado, tiraría también los pedidos de prueba)."""
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


def pedido(estado, lineas, fecha_entrega=None):
    cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega) "
                "SELECT id_cliente, CURRENT_DATE, %s, %s FROM cliente ORDER BY id_cliente LIMIT 1 RETURNING id_pedido",
                (estado, fecha_entrega))
    pid = cur.fetchone()[0]
    for prod, (cant, ent) in zip(productos, lineas):
        cur.execute("INSERT INTO detallepedido (id_pedido, id_producto, cantidad, cantidad_entregada, precio_unitario) "
                    "VALUES (%s, %s, %s, %s, 0)", (pid, prod, cant, ent))
    return pid


def lineas_de(pid):
    cur.execute("SELECT id_detalle, cantidad, cantidad_entregada FROM detallepedido WHERE id_pedido = %s ORDER BY id_detalle", (pid,))
    return cur.fetchall()


def estado_de(pid):
    cur.execute("SELECT estado_pedido, fecha_entrega FROM pedido WHERE id_pedido = %s", (pid,))
    return cur.fetchone()


try:
    cur.execute("SELECT id_producto FROM producto ORDER BY id_producto LIMIT 3")
    productos = [r[0] for r in cur.fetchall()]

    print("=== _quitar_linea_pedido (la regla, contra la base) ===")
    p = pedido("pendiente", ((5, 0), (2, 0), (4, 0)))
    (d1, _, _), (d2, _, _), (d3, _, _) = lineas_de(p)
    check("quita un artículo de un pedido sin entregar -> 'quitada'", pp._quitar_linea_pedido(cur, p, d2) == "quitada"
          and [d for d, _, _ in lineas_de(p)] == [d1, d3] and estado_de(p)[0] == "pendiente")
    check("quitar la misma línea otra vez -> 'ya_no_estaba' (no da error)", pp._quitar_linea_pedido(cur, p, d2) == "ya_no_estaba")
    check("pedido inexistente -> 'no_existe'", pp._quitar_linea_pedido(cur, -999999, 1) == "no_existe")
    check("una línea de OTRO pedido no se toca", pp._quitar_linea_pedido(cur, p, 987654321) == "ya_no_estaba" and len(lineas_de(p)) == 2)
    check("quita otro y queda uno solo", pp._quitar_linea_pedido(cur, p, d3) == "quitada" and [d for d, _, _ in lineas_de(p)] == [d1])
    check("el ÚLTIMO artículo no se quita -> 'es_la_unica'", pp._quitar_linea_pedido(cur, p, d1) == "es_la_unica" and len(lineas_de(p)) == 1)

    p_ent = pedido("entregado", ((5, 5), (2, 2), (4, 4)), hoy)
    check("un pedido ENTREGADO no se modifica -> 'ya_entregado'", pp._quitar_linea_pedido(cur, p_ent, lineas_de(p_ent)[0][0]) == "ya_entregado"
          and len(lineas_de(p_ent)) == 3)

    p_par = pedido("programado", ((5, 2), (2, 0), (4, 0)), hoy)
    check("un artículo del que ya se entregó algo no se quita -> 'entregada_en_parte'",
          pp._quitar_linea_pedido(cur, p_par, lineas_de(p_par)[0][0]) == "entregada_en_parte" and len(lineas_de(p_par)) == 3)

    p_c = pedido("programado", ((5, 5), (2, 0), (4, 0)), hoy)
    (c_a, _, _), (c_b, _, _), (c_c, _, _) = lineas_de(p_c)
    check("si queda otro pendiente, el pedido sigue programado", pp._quitar_linea_pedido(cur, p_c, c_b) == "quitada" and estado_de(p_c)[0] == "programado")
    check("quitar el último pendiente deja todo entregado -> 'completo' y el pedido pasa a 'entregado' hoy",
          pp._quitar_linea_pedido(cur, p_c, c_c) == "completo" and estado_de(p_c) == ("entregado", hoy) and [d for d, _, _ in lineas_de(p_c)] == [c_a])

    print("=== la X del detalle del pedido ===")

    def botones(ventana):
        """Los botones X de la tabla, por fila (None si la fila no tiene)."""
        salida = []
        for i in range(ventana.tabla_productos.rowCount()):
            celda = ventana.tabla_productos.cellWidget(i, 7)
            salida.append(celda.findChild(QPushButton) if celda is not None else None)
        return salida

    p_ui = pedido("programado", ((5, 0), (2, 0), (4, 3)), hoy)
    v = pp.VentanaDetallePedido(p_ui, None, None)
    check("la tabla de productos tiene la columna de la X", v.tabla_productos.columnCount() == 8)
    bs = botones(v)
    check("una X por artículo", len(bs) == 3 and all(b is not None for b in bs))
    check("los dos sin entregas se pueden quitar", bs[0].isEnabled() and bs[1].isEnabled())
    check("el que ya tiene entregas queda apagado y explica por qué", not bs[2].isEnabled() and "ya se entregó" in bs[2].toolTip(), bs[2].toolTip())

    # Quitar uno: pregunta, borra, y la tabla se recarga sola.
    cambios = []
    v.pedido_updated.connect(cambios.append)
    preguntas.clear()
    avisos.clear()
    bs[1].click()
    check("antes de borrar pregunta, con el artículo y el número de pedido", len(preguntas) == 1 and str(p_ui) in preguntas[0], preguntas)
    check("el artículo se quitó de la base", len(lineas_de(p_ui)) == 2)
    check("la tabla se recargó con un artículo menos", v.tabla_productos.rowCount() == 2 and v._badge_prod.text() == "2 artículos")
    check("avisa al resto de la PC que el pedido cambió", cambios == [p_ui], cambios)
    check("no hubo avisos de error", [a for a in avisos if a[0] in ("error", "aviso")] == [], avisos)

    # Si dice que no, no se toca nada.
    respuesta["valor"] = QMessageBox.No
    antes = lineas_de(p_ui)
    botones(v)[0].click()
    check("si se responde que no, no se borra nada", lineas_de(p_ui) == antes and v.tabla_productos.rowCount() == 2)
    respuesta["valor"] = QMessageBox.Yes

    # Quedan dos: uno sin entregas y uno con entregas (apagado). Quitar el primero deja todo lo pendiente fuera.
    bs = botones(v)
    check("con un artículo sin entregas y otro con entregas, el primero se puede quitar", bs[0].isEnabled() and not bs[1].isEnabled())
    avisos.clear()
    bs[0].click()
    check("al quitarlo, el que queda tiene entregado 3 de 4 (falta 1): el pedido sigue programado",
          estado_de(p_ui)[0] == "programado" and len(lineas_de(p_ui)) == 1)
    check("el que queda (con entregas, y además el único) sigue apagado", not botones(v)[0].isEnabled() and "ya se entregó" in botones(v)[0].toolTip())
    v_uno = pp.VentanaDetallePedido(pedido("pendiente", ((5, 0),)), None, None)
    check("un pedido con UN solo artículo (sin entregas) lo muestra apagado y dice que hay que eliminar el pedido",
          not botones(v_uno)[0].isEnabled() and "único artículo" in botones(v_uno)[0].toolTip())

    # Un pedido entregado no muestra ninguna X.
    v_ent = pp.VentanaDetallePedido(p_ent, None, None)
    check("un pedido entregado no tiene X", all(b is None for b in botones(v_ent)))

    # Alguien lo cambió mientras la ventana estaba abierta: el aviso es claro y la tabla se actualiza.
    p_carrera = pedido("pendiente", ((5, 0), (2, 0), (4, 0)))
    v_c = pp.VentanaDetallePedido(p_carrera, None, None)
    b_viejo = botones(v_c)[0]
    id_viejo = lineas_de(p_carrera)[0][0]
    cur.execute("DELETE FROM detallepedido WHERE id_detalle = %s", (id_viejo,))   # lo quitó otra PC
    avisos.clear()
    b_viejo.click()
    check("si la línea ya no estaba, no falla (se recarga y listo)", [a for a in avisos if a[0] == "error"] == [] and v_c.tabla_productos.rowCount() == 2)

    # Si la base se cae a mitad de camino, avisa y no deja la tabla a medias.
    p_error = pedido("pendiente", ((5, 0), (2, 0), (4, 0)))
    v_e = pp.VentanaDetallePedido(p_error, None, None)
    original = pp._quitar_linea_pedido
    pp._quitar_linea_pedido = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulado"))
    avisos.clear()
    botones(v_e)[0].click()
    pp._quitar_linea_pedido = original
    check("ante un error de base avisa y no borra nada", any(a[0] == "error" and "No se pudo quitar" in a[1] for a in avisos) and len(lineas_de(p_error)) == 3, avisos)
finally:
    real.rollback()
    real.close()

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S): {fallas}")
sys.exit(1 if fallas else 0)
