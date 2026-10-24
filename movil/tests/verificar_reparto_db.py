"""Reparto contra la base real (movil/api/db.py: `pedidos_para_reparto` y `marcar_entregado`),
conectado como `movil_api` (con sus permisos reales) y dentro de una transacción que siempre
se revierte. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_reparto_db.py
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


# La conexión real se abre ANTES de fijar las variables de prueba (mismos nombres PEDIDOS_DB_*
# que la app de escritorio; ver guideline/Movil.md).
print("=== reparto: lista y entrega (transacción que se revierte) ===")
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
        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente LIMIT 1")
        id_cliente = cur.fetchone()[0]
        cur.execute("UPDATE cliente SET direccion = 'Calle Prueba 123, MENDOZA', telefono = '261-0000', "
                    "ubicacion_maps = 'https://maps.app.goo.gl/prueba', ubicacion_lat = -32.9, ubicacion_lng = -68.8 "
                    "WHERE id_cliente = %s", (id_cliente,))
        cur.execute("SELECT id_producto FROM producto ORDER BY id_producto LIMIT 2")
        prod1, prod2 = (r[0] for r in cur.fetchall())

        def pedido(estado, fecha_entrega, entregadas=(0, 0)):
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega) "
                        "VALUES (%s, %s, %s, %s) RETURNING id_pedido",
                        (id_cliente, hoy - dt.timedelta(days=3), estado, fecha_entrega))
            pid = cur.fetchone()[0]
            creados.append(pid)
            for prod, cant, ent in ((prod1, 5, entregadas[0]), (prod2, 2, entregadas[1])):
                cur.execute("INSERT INTO detallepedido (id_pedido, id_producto, cantidad, cantidad_entregada, "
                            "precio_unitario) VALUES (%s, %s, %s, %s, 0)", (pid, prod, cant, ent))
            return pid

        p_prog = pedido("programado", hoy)
        p_camino = pedido("en camino", hoy + dt.timedelta(days=1), entregadas=(2, 0))
        p_sin_fecha = pedido("programado", None)
        p_pend = pedido("pendiente", None)
        p_entregado = pedido("entregado", hoy, entregadas=(5, 2))

        # Todo lo que sigue corre con los permisos reales del rol de la API.
        cur.execute("SET LOCAL ROLE movil_api")

        print("  -- lista para el reparto --")
        lista = db.pedidos_para_reparto(con)
        ids = [p["id_pedido"] for p in lista]
        check("incluye programado, en camino y programado sin fecha",
              all(i in ids for i in (p_prog, p_camino, p_sin_fecha)))
        check("NO incluye pendiente ni entregado", p_pend not in ids and p_entregado not in ids)
        check("ordenados por fecha de entrega, sin fecha al final",
              ids.index(p_prog) < ids.index(p_camino) < ids.index(p_sin_fecha))
        ficha = next(p for p in lista if p["id_pedido"] == p_camino)
        check("estado y fecha de entrega", ficha["estado"] == "en camino" and ficha["fecha_entrega"] == hoy + dt.timedelta(days=1))
        check("cliente con dirección, teléfono y ubicación",
              (ficha["cliente"]["direccion"], ficha["cliente"]["telefono"], ficha["cliente"]["ubicacion_maps"],
               ficha["cliente"]["ubicacion_lat"], ficha["cliente"]["ubicacion_lng"])
              == ("Calle Prueba 123, MENDOZA", "261-0000", "https://maps.app.goo.gl/prueba", -32.9, -68.8), ficha["cliente"])
        check("dos líneas con nombre, cantidad y entregada",
              [(l["id_producto"], l["cantidad"], l["entregada"]) for l in ficha["lineas"]] == [(prod1, 5, 2), (prod2, 2, 0)]
              and all(l["nombre"] for l in ficha["lineas"]), ficha["lineas"])

        print("  -- entregar --")
        check("un pedido programado se entrega", db.marcar_entregado(con, p_prog) == "entregado")
        cur.execute("SELECT estado_pedido, fecha_entrega FROM pedido WHERE id_pedido = %s", (p_prog,))
        check("queda 'entregado' con la fecha de HOY", cur.fetchone() == ("entregado", hoy))
        cur.execute("SELECT cantidad_entregada = cantidad, estado_entrega FROM detallepedido WHERE id_pedido = %s", (p_prog,))
        filas = cur.fetchall()
        check("todas las líneas entregadas por completo", all(f == (True, "completa") for f in filas), filas)
        check("ya no está en la lista del reparto", p_prog not in [p["id_pedido"] for p in db.pedidos_para_reparto(con)])

        check("reintentar no rompe: 'ya_estaba'", db.marcar_entregado(con, p_prog) == "ya_estaba")
        cur.execute("SELECT fecha_entrega FROM pedido WHERE id_pedido = %s", (p_prog,))
        check("y no cambia nada", cur.fetchone()[0] == hoy)

        check("'en camino' con entrega parcial previa se completa", db.marcar_entregado(con, p_camino) == "entregado")
        cur.execute("SELECT cantidad_entregada, cantidad FROM detallepedido WHERE id_pedido = %s ORDER BY id_detalle", (p_camino,))
        check("las líneas parciales quedan completas", all(e == c for e, c in cur.fetchall()))
        cur.execute("SELECT fecha_entrega FROM pedido WHERE id_pedido = %s", (p_camino,))
        check("la fecha pasa a hoy (no la programada)", cur.fetchone()[0] == hoy)

        check("un pedido 'pendiente' no se puede entregar", db.marcar_entregado(con, p_pend) == "sin_programar")
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s", (p_pend,))
        check("y sigue pendiente", cur.fetchone()[0] == "pendiente")
        check("un pedido inexistente", db.marcar_entregado(con, -999999) == "no_existe")

        cur.execute("RESET ROLE")
        # La PC lo ve entregado con la misma consulta de su panel "Entregados (última semana)".
        cur.execute("SELECT p.id_pedido FROM Pedido p JOIN Cliente c ON p.id_cliente = c.id_cliente "
                    "WHERE p.estado_pedido = 'entregado' AND p.fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'")
        visto_por_la_pc = {f[0] for f in cur.fetchall()}
        check("la PC lo ve en 'Entregados (última semana)'", {p_prog, p_camino} <= visto_por_la_pc)

        print("  -- ubicación del cliente con el GPS del reparto --")
        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente OFFSET 1 LIMIT 3")
        c2, c3, c4 = (r[0] for r in cur.fetchall())
        cur.execute("UPDATE cliente SET ubicacion_maps = NULL, ubicacion_lat = NULL, ubicacion_lng = NULL "
                    "WHERE id_cliente = ANY(%s)", ([c2, c3, c4],))
        # c2: programado; c3: entregado hace 10 días (ya no cuenta); c4: entregado hoy (cuenta)
        for cliente, estado, entrega in ((c2, "programado", hoy), (c3, "entregado", hoy - dt.timedelta(days=10)),
                                         (c4, "entregado", hoy)):
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega) "
                        "VALUES (%s, %s, %s, %s) RETURNING id_pedido", (cliente, hoy - dt.timedelta(days=12), estado, entrega))
            creados.append(cur.fetchone()[0])

        def ubicacion_de(cliente):
            cur.execute("SELECT ubicacion_maps, ubicacion_lat, ubicacion_lng FROM cliente WHERE id_cliente = %s", (cliente,))
            return cur.fetchone()

        lat, lng = -32.922612345, -68.857198765
        cur.execute("SET LOCAL ROLE movil_api")
        check("cliente con entrega pendiente y sin ubicación: se guarda",
              db.guardar_ubicacion_cliente(con, c2, lat, lng) == "guardada")
        cur.execute("RESET ROLE")
        enlace, glat, glng = ubicacion_de(c2)
        check("guarda las coordenadas redondeadas a 6 decimales", (glat, glng) == (round(lat, 6), round(lng, 6)), (glat, glng))
        check("y el enlace de Maps de ese punto", enlace == db.enlace_maps(lat, lng) and enlace.startswith("https://www.google.com/maps/"), enlace)
        from src.controllers import ubicacion_maps as um   # el lector de la PC entiende ese enlace
        check("la PC saca las mismas coordenadas del enlace", um.extraer_coordenadas(enlace) == (glat, glng))
        check("pasa el CHECK de la base (solo http/https)", um.es_enlace_valido(enlace))

        cur.execute("SET LOCAL ROLE movil_api")
        check("si ya tiene ubicación, NO se pisa", db.guardar_ubicacion_cliente(con, c2, -34.0, -58.0) == "ya_tiene")
        check("cliente cuya última entrega fue hace 10 días: se rechaza",
              db.guardar_ubicacion_cliente(con, c3, lat, lng) == "sin_entregas")
        check("cliente entregado HOY (la ubicación llegó después de la entrega, sin señal): se guarda",
              db.guardar_ubicacion_cliente(con, c4, lat, lng) == "guardada")
        check("cliente inexistente: se rechaza", db.guardar_ubicacion_cliente(con, -999999, lat, lng) == "sin_entregas")
        cur.execute("RESET ROLE")
        check("lo rechazado no escribió nada", ubicacion_de(c2) == (enlace, glat, glng) and ubicacion_de(c3) == (None, None, None))
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM pedido WHERE id_pedido = ANY(%s)", (creados,))
        check("rollback: ningún pedido de prueba quedó en la base real", cur.fetchone()[0] == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
