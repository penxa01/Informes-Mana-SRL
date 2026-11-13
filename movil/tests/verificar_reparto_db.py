"""Ubicación de los clientes con el GPS del reparto contra la base real (movil/api/db.py:
`guardar_ubicacion_cliente`), conectado como `movil_api` (con sus permisos reales) y dentro de una transacción
que siempre se revierte. Si la base no responde, se omite y se avisa.

(La lista de pedidos por entregar, en camino y las entregas se prueban en verificar_gestion_db.py.)

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
print("=== ubicación de clientes con el GPS (transacción que se revierte) ===")
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

        # Clientes SIN pedidos sin entregar ni recientes (el negocio sigue operando: un cliente que hoy recibió un
        # pedido haría que "entregado hace 10 días" cuente como reciente y el test fallara solo).
        cur.execute("SELECT c.id_cliente FROM cliente c WHERE NOT EXISTS (SELECT 1 FROM pedido p WHERE p.id_cliente = c.id_cliente "
                    "AND (p.estado_pedido <> 'entregado' OR p.fecha_entrega >= CURRENT_DATE - 7)) "
                    "ORDER BY c.id_cliente LIMIT 6")
        c1, c2, c3, c4, c5, c6 = (r[0] for r in cur.fetchall())
        cur.execute("UPDATE cliente SET ubicacion_maps = NULL, ubicacion_lat = NULL, ubicacion_lng = NULL "
                    "WHERE id_cliente = ANY(%s)", ([c1, c2, c3, c4, c5, c6],))
        # c1: pendiente; c2: programado; c3: en camino; c4: entregado hace 10 días (ya no cuenta); c5: entregado hoy
        # (cuenta); c6: sin pedidos de ningún tipo.
        for cliente, estado, entrega in ((c1, "pendiente", None), (c2, "programado", hoy), (c3, "en camino", None),
                                         (c4, "entregado", hoy - dt.timedelta(days=10)), (c5, "entregado", hoy)):
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega) "
                        "VALUES (%s, %s, %s, %s) RETURNING id_pedido", (cliente, hoy - dt.timedelta(days=12), estado, entrega))
            creados.append(cur.fetchone()[0])

        def ubicacion_de(cliente):
            cur.execute("SELECT ubicacion_maps, ubicacion_lat, ubicacion_lng FROM cliente WHERE id_cliente = %s", (cliente,))
            return cur.fetchone()

        lat, lng = -32.922612345, -68.857198765
        # Todo lo que sigue corre con los permisos reales del rol de la API.
        cur.execute("SET LOCAL ROLE movil_api")
        check("cliente con un pedido PENDIENTE y sin ubicación: se guarda (el reparto ve todos los pedidos)",
              db.guardar_ubicacion_cliente(con, c1, lat, lng) == "guardada")
        check("cliente con un pedido programado: se guarda", db.guardar_ubicacion_cliente(con, c2, lat, lng) == "guardada")
        cur.execute("RESET ROLE")
        enlace, glat, glng = ubicacion_de(c2)
        check("guarda las coordenadas redondeadas a 6 decimales", (glat, glng) == (round(lat, 6), round(lng, 6)), (glat, glng))
        check("y el enlace de Maps de ese punto", enlace == db.enlace_maps(lat, lng) and enlace.startswith("https://www.google.com/maps/"), enlace)
        from src.controllers import ubicacion_maps as um   # el lector de la PC entiende ese enlace
        check("la PC saca las mismas coordenadas del enlace", um.extraer_coordenadas(enlace) == (glat, glng))
        check("pasa el CHECK de la base (solo http/https)", um.es_enlace_valido(enlace))

        cur.execute("SET LOCAL ROLE movil_api")
        check("si ya tiene ubicación, NO se pisa", db.guardar_ubicacion_cliente(con, c2, -34.0, -58.0) == "ya_tiene")
        check("cliente con un pedido en camino: se guarda", db.guardar_ubicacion_cliente(con, c3, lat, lng) == "guardada")
        check("cliente cuyo último pedido se entregó hace 10 días: se rechaza",
              db.guardar_ubicacion_cliente(con, c4, lat, lng) == "sin_entregas")
        check("cliente entregado HOY (la ubicación llegó después de la entrega, sin señal): se guarda",
              db.guardar_ubicacion_cliente(con, c5, lat, lng) == "guardada")
        check("cliente sin pedidos: se rechaza", db.guardar_ubicacion_cliente(con, c6, lat, lng) == "sin_entregas")
        check("cliente inexistente: se rechaza", db.guardar_ubicacion_cliente(con, -999999, lat, lng) == "sin_entregas")
        cur.execute("RESET ROLE")
        check("lo rechazado no escribió nada", ubicacion_de(c2) == (enlace, glat, glng)
              and ubicacion_de(c4) == (None, None, None) and ubicacion_de(c6) == (None, None, None))
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM pedido WHERE id_pedido = ANY(%s)", (creados,))
        check("rollback: ningún pedido de prueba quedó en la base real", cur.fetchone()[0] == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
