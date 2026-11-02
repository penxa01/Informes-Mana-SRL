"""Gestión de pedidos del admin contra la base real (movil/api/db.py: `pedidos_para_gestion`, `entregar_pedido_total`,
`entrega_parcial`, `programar_pedido` y `borrar_pedido`), ejecutada como `movil_api` (con sus permisos reales, incluido
el de borrar) y dentro de una transacción que siempre se revierte. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_gestion_db.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# La conexión real se abre ANTES de fijar las variables de prueba (mismos nombres PEDIDOS_DB_* que la app de
# escritorio; ver guideline/Movil.md).
print("=== gestión de pedidos del admin (transacción que se revierte, con el rol movil_api) ===")
try:
    from src.Views.Pedidos.programarPedido import _conexion
    con = _conexion()
except Exception as e:
    con = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from movil import migraciones
from movil.api import db

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    creados = []
    try:
        migraciones.aplicar(con)
        migraciones.asegurar_permisos(con)   # no depende de cómo haya quedado el servidor

        hoy = dt.date.today()
        dia = lambda n: hoy + dt.timedelta(days=n)
        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente LIMIT 1")
        id_cliente = cur.fetchone()[0]
        cur.execute("SELECT nombre FROM cliente WHERE id_cliente = %s", (id_cliente,))
        nombre_cliente = cur.fetchone()[0]
        cur.execute("SELECT id_producto FROM producto ORDER BY id_producto LIMIT 3")
        prod1, prod2, prod3 = (r[0] for r in cur.fetchall())
        cur.execute("SELECT username, nombre FROM usuario WHERE username = 'jose'")
        fila_jose = cur.fetchone()

        def pedido(estado, fecha_entrega=None, creado_por=None, origen="pc", lineas=((5, 0), (2, 0), (4, 0))):
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega, creado_por, origen) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_pedido",
                        (id_cliente, dia(-3), estado, fecha_entrega, creado_por, origen))
            pid = cur.fetchone()[0]
            creados.append(pid)
            for prod, (cant, ent) in zip((prod1, prod2, prod3), lineas):
                cur.execute("INSERT INTO detallepedido (id_pedido, id_producto, cantidad, cantidad_entregada, precio_unitario) "
                            "VALUES (%s, %s, %s, %s, 0)", (pid, prod, cant, ent))
            return pid

        def lineas_de(pid):
            cur.execute("SELECT id_detalle, cantidad, cantidad_entregada FROM detallepedido WHERE id_pedido = %s ORDER BY id_detalle", (pid,))
            return cur.fetchall()

        def estado_de(pid):
            cur.execute("SELECT estado_pedido, fecha_entrega FROM pedido WHERE id_pedido = %s", (pid,))
            return cur.fetchone()

        p_pend = pedido("pendiente", None, creado_por="jose" if fila_jose else None, origen="movil" if fila_jose else "pc")
        p_prog = pedido("programado", dia(1))
        p_camino = pedido("en camino", dia(0), lineas=((5, 2), (2, 0), (4, 0)))
        p_ent_reciente = pedido("entregado", dia(-6), lineas=((5, 5), (2, 2), (4, 4)))
        p_ent_viejo = pedido("entregado", dia(-8), lineas=((5, 5), (2, 2), (4, 4)))

        # Todo lo que sigue corre con los permisos reales del rol de la API.
        cur.execute("SET LOCAL ROLE movil_api")

        print("  -- lista --")
        g = db.pedidos_para_gestion(con)
        ids_p = [p["id_pedido"] for p in g["pendientes"]]
        ids_e = [p["id_pedido"] for p in g["entregados"]]
        check("pendientes incluye pendiente, programado y en camino", all(i in ids_p for i in (p_pend, p_prog, p_camino)))
        check("pendientes NO incluye entregados", p_ent_reciente not in ids_p and p_ent_viejo not in ids_p)
        check("entregados incluye el de hace 6 días y NO el de hace 8 (última semana, como la PC)", p_ent_reciente in ids_e and p_ent_viejo not in ids_e)
        check("entregados NO incluye ningún pendiente", not any(i in ids_e for i in (p_pend, p_prog, p_camino)))
        check("pendientes por fecha de entrega (el de hoy antes que el de mañana) y sin fecha al final",
              ids_p.index(p_camino) < ids_p.index(p_prog) < ids_p.index(p_pend))
        ficha = next(p for p in g["pendientes"] if p["id_pedido"] == p_camino)
        check("trae estado, fecha de entrega y el nombre del cliente", (ficha["estado"], ficha["fecha_entrega"], ficha["cliente"]) == ("en camino", dia(0), nombre_cliente), ficha)
        check("trae las 3 líneas con id_detalle, producto, nombre, cantidad y entregada",
              [(l["id_producto"], l["cantidad"], l["entregada"]) for l in ficha["lineas"]] == [(prod1, 5, 2), (prod2, 2, 0), (prod3, 4, 0)]
              and all(l["id_detalle"] and l["nombre"] for l in ficha["lineas"]), ficha["lineas"])
        check("NO trae dirección ni teléfono", "direccion" not in ficha and "telefono" not in ficha and isinstance(ficha["cliente"], str))
        if fila_jose:
            check("un pedido cargado desde el celular trae el nombre de quien lo cargó",
                  next(p for p in g["pendientes"] if p["id_pedido"] == p_pend)["cargado_por"] == fila_jose[1])
        check("uno cargado desde la PC no tiene quién lo cargó", ficha["cargado_por"] is None and ficha["origen"] == "pc")

        print("  -- entrega total --")
        check("un pedido PENDIENTE (sin programar) se puede entregar completo (el reparto no puede, el admin sí)",
              db.entregar_pedido_total(con, p_pend) == "entregado")
        check("queda 'entregado' con la fecha de HOY", estado_de(p_pend) == ("entregado", hoy), estado_de(p_pend))
        check("todas las líneas completas", all(e == c for _, c, e in lineas_de(p_pend)))
        check("reintentar -> 'ya_estaba' y no cambia nada", db.entregar_pedido_total(con, p_pend) == "ya_estaba" and estado_de(p_pend) == ("entregado", hoy))
        check("pedido inexistente -> 'no_existe'", db.entregar_pedido_total(con, -999999) == "no_existe")

        print("  -- entrega parcial --")
        (d1, c1, e1), (d2, c2, e2), (d3, c3, e3) = lineas_de(p_prog)
        r = db.entrega_parcial(con, p_prog, {d1: 2})
        check("entregar 2 de 5 de una línea -> 'parcial'", r == ("parcial", None), r)
        check("esa línea queda en 2 y las demás no cambian", [e for _, _, e in lineas_de(p_prog)] == [2, 0, 0])
        check("el pedido sigue programado (como en la PC: no pasa a entregado hasta completar)", estado_de(p_prog) == ("programado", dia(1)), estado_de(p_prog))
        check("reintentar la MISMA orden no entrega dos veces -> 'sin_cambios'", db.entrega_parcial(con, p_prog, {d1: 2}) == ("sin_cambios", None)
              and [e for _, _, e in lineas_de(p_prog)] == [2, 0, 0])
        check("entregar más de una línea a la vez", db.entrega_parcial(con, p_prog, {d1: 4, d2: 1}) == ("parcial", None)
              and [e for _, _, e in lineas_de(p_prog)] == [4, 1, 0])
        check("más de lo pedido -> 'excede' y no cambia nada", db.entrega_parcial(con, p_prog, {d1: 6}) == ("excede", d1)
              and [e for _, _, e in lineas_de(p_prog)] == [4, 1, 0])
        check("menos de lo ya entregado (alguien lo cambió) -> 'cambio' y no cambia nada", db.entrega_parcial(con, p_prog, {d1: 1}) == ("cambio", d1)
              and [e for _, _, e in lineas_de(p_prog)] == [4, 1, 0])
        otra = lineas_de(p_camino)[0][0]
        check("una línea de OTRO pedido -> 'linea_ajena' y no toca nada", db.entrega_parcial(con, p_prog, {otra: 1}) == ("linea_ajena", otra)
              and lineas_de(p_camino)[0][2] == 2)
        check("un error en una línea no deja aplicada la otra (todo o nada)", db.entrega_parcial(con, p_prog, {d2: 2, d1: 99}) == ("excede", d1)
              and [e for _, _, e in lineas_de(p_prog)] == [4, 1, 0])
        r = db.entrega_parcial(con, p_prog, {d1: c1, d2: c2, d3: c3})
        check("al completar todo -> 'completo'", r == ("completo", None), r)
        check("el pedido pasa a 'entregado' con la fecha de HOY (no la programada)", estado_de(p_prog) == ("entregado", hoy), estado_de(p_prog))
        check("un pedido ya entregado -> 'ya_entregado'", db.entrega_parcial(con, p_prog, {d1: c1}) == ("ya_entregado", None))
        check("pedido inexistente -> 'no_existe'", db.entrega_parcial(con, -999999, {1: 1}) == ("no_existe", None))

        print("  -- programar / reprogramar --")
        check("un pedido 'en camino' se reprograma (estado 'programado' y la nueva fecha)", db.programar_pedido(con, p_camino, dia(5)) == "programado"
              and estado_de(p_camino) == ("programado", dia(5)), estado_de(p_camino))
        check("programar hoy se puede", db.programar_pedido(con, p_camino, hoy) == "programado" and estado_de(p_camino) == ("programado", hoy))
        check("la misma orden otra vez no rompe (idempotente)", db.programar_pedido(con, p_camino, hoy) == "programado")
        check("una fecha anterior a hoy -> 'fecha_pasada' y no cambia nada", db.programar_pedido(con, p_camino, dia(-1)) == "fecha_pasada"
              and estado_de(p_camino) == ("programado", hoy))
        check("un pedido ya entregado no se programa", db.programar_pedido(con, p_ent_reciente, dia(2)) == "ya_entregado"
              and estado_de(p_ent_reciente) == ("entregado", dia(-6)))
        check("pedido inexistente -> 'no_existe'", db.programar_pedido(con, -999999, dia(2)) == "no_existe")

        print("  -- borrar --")
        p_a_borrar = pedido("pendiente")
        cur.execute("SELECT count(*) FROM detallepedido WHERE id_pedido = %s", (p_a_borrar,))
        check("el pedido de prueba tiene sus 3 líneas", cur.fetchone()[0] == 3)
        check("un pedido pendiente se borra (con el permiso real de movil_api)", db.borrar_pedido(con, p_a_borrar) == "borrado")
        cur.execute("SELECT count(*) FROM pedido WHERE id_pedido = %s", (p_a_borrar,))
        borrado = cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM detallepedido WHERE id_pedido = %s", (p_a_borrar,))
        check("y se van el pedido y sus líneas (por la clave foránea)", borrado and cur.fetchone()[0] == 0)
        check("borrar otra vez -> 'ya_no_estaba' (no da error)", db.borrar_pedido(con, p_a_borrar) == "ya_no_estaba")
        check("un pedido ENTREGADO no se borra desde el celular", db.borrar_pedido(con, p_ent_reciente) == "entregado"
              and estado_de(p_ent_reciente) is not None)

        print("  -- el permiso de borrar es solo sobre pedido --")

        def permitido(sql):
            cur.execute("SAVEPOINT s_permiso")
            try:
                cur.execute(sql)
                ok = True
            except Exception:
                ok = False
            cur.execute("ROLLBACK TO SAVEPOINT s_permiso")
            return ok

        check("movil_api NO puede borrar líneas directamente", not permitido(f"DELETE FROM detallepedido WHERE id_pedido = {p_ent_reciente}"))
        check("movil_api NO puede borrar clientes ni productos", not permitido("DELETE FROM cliente WHERE false") and not permitido("DELETE FROM producto WHERE false"))
        check("movil_api NO puede cambiar el cliente de un pedido ni las cantidades pedidas",
              not permitido(f"UPDATE pedido SET id_cliente = id_cliente WHERE id_pedido = {p_ent_reciente}")
              and not permitido("UPDATE detallepedido SET cantidad = cantidad WHERE false"))
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM pedido WHERE id_pedido = ANY(%s)", (creados,))
        check("rollback: ningún pedido de prueba quedó en la base real", cur.fetchone()[0] == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
