"""`POST /pedidos` (movil/api/db.py + routers/pedidos.py): nuevo, repetido
(idempotencia), producto inexistente y que la PC lo vea con la misma consulta
de `check_for_changes` (programarPedido.py).

Escribe en la base real: corre **dentro de una transacción que se revierte**.
Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_pedidos_api.py
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# movil/api/config.py lee las mismas PEDIDOS_DB_* que programarPedido.py (a
# propósito, ver guideline/Movil.md): la conexión real se abre ACÁ, antes de
# importar movil.api.db (que exige esas variables, aunque sea con valores
# falsos para no tocar la base real desde este archivo de test).
print("=== POST /pedidos: db.crear_pedido (transacción que se revierte) ===")
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

from movil.api import db
from movil import migraciones

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    try:
        # La migración de la Tarea 1 todavía no se aplicó de verdad al servidor
        # (su propio test la revierte a propósito): se aplica acá, dentro de
        # esta misma transacción que también se revierte al final, para poder
        # probar `origen`/`uuid_cliente` sin tocar la base real.
        migraciones.aplicar(con)

        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente LIMIT 1")
        id_cliente = cur.fetchone()[0]
        cur.execute("SELECT id_producto FROM producto ORDER BY id_producto LIMIT 2")
        id_producto_1, id_producto_2 = (r[0] for r in cur.fetchall())

        check("cliente existente", db.cliente_existe(con, id_cliente))
        check("cliente inexistente", not db.cliente_existe(con, -999999))
        check("sin productos inexistentes", db.productos_inexistentes(con, [id_producto_1]) == [])
        check("detecta producto inexistente",
              db.productos_inexistentes(con, [id_producto_1, "NO-EXISTE-XYZ"]) == ["NO-EXISTE-XYZ"])

        u = str(uuid.uuid4())
        lineas = [(id_producto_1, 3), (id_producto_2, 1)]
        id_pedido, ya_existia = db.crear_pedido(con, u, id_cliente, dt.date.today(), lineas, "miguel")
        check("pedido nuevo: no existía", not ya_existia)
        check("pedido nuevo: devuelve un id", isinstance(id_pedido, int) and id_pedido > 0, id_pedido)

        cur.execute("SELECT estado_pedido, origen, uuid_cliente, creado_por FROM pedido WHERE id_pedido = %s",
                    (id_pedido,))
        estado, origen, uuid_guardado, creado_por = cur.fetchone()
        check("estado inicial 'pendiente'", estado == "pendiente", estado)
        check("origen 'movil'", origen == "movil", origen)
        check("uuid guardado coincide", str(uuid_guardado) == u)
        check("creado_por = username", creado_por == "miguel", creado_por)

        cur.execute("SELECT id_producto, cantidad FROM detallepedido WHERE id_pedido = %s ORDER BY id_producto",
                    (id_pedido,))
        detalle = cur.fetchall()
        check("dos líneas de detalle", len(detalle) == 2, detalle)

        print("  -- reenviar el mismo pedido (reconexión / doble tap) --")
        id_pedido_2, ya_existia_2 = db.crear_pedido(con, u, id_cliente, dt.date.today(), lineas, "miguel")
        check("mismo uuid -> mismo id_pedido", id_pedido_2 == id_pedido)
        check("mismo uuid -> ya_existia=True", ya_existia_2)
        cur.execute("SELECT count(*) FROM pedido WHERE uuid_cliente = %s", (u,))
        check("no se duplicó el pedido", cur.fetchone()[0] == 1)
        cur.execute("SELECT count(*) FROM detallepedido WHERE id_pedido = %s", (id_pedido,))
        check("no se duplicó el detalle", cur.fetchone()[0] == 2)

        print("  -- la PC lo ve con la consulta real de check_for_changes --")
        cur.execute("""
            SELECT p.id_pedido, p.estado_pedido, p.fecha_entrega, c.nombre, p.fecha_pedido
            FROM Pedido p
            JOIN Cliente c ON p.id_cliente = c.id_cliente
            WHERE p.estado_pedido IN ('pendiente', 'programado', 'en camino')
            ORDER BY p.id_pedido
        """)
        vistos = {fila[0] for fila in cur.fetchall()}
        check("el pedido movil aparece en el poll de la PC", id_pedido in vistos)
    finally:
        con.rollback()
        con.close()
    print("  rollback: nada de esto queda en la base real")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
