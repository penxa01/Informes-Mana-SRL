"""Suscripciones a avisos contra la base real (movil/api/db.py: `id_usuario`, `guardar_suscripcion` y
`borrar_suscripcion`), ejecutadas como `movil_api` (con sus permisos reales) y dentro de una transacción
que siempre se revierte. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_push_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# La conexión real se abre ANTES de fijar las variables de prueba (mismos nombres PEDIDOS_DB_* que la
# app de escritorio; ver guideline/Movil.md).
print("=== suscripciones a avisos (transacción que se revierte) ===")
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

PREFIJO = "https://fcm.googleapis.com/fcm/send/prueba-"

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    try:
        migraciones.aplicar(con)
        migraciones.asegurar_permisos(con)   # no depende de cómo haya quedado el servidor

        cur.execute("SELECT id, username FROM usuario WHERE activo ORDER BY id LIMIT 2")
        (id_a, user_a), (id_b, user_b) = cur.fetchall()

        def filas(endpoint):
            cur.execute("SELECT usuario_id, p256dh, auth FROM push_suscripcion WHERE endpoint = %s", (PREFIJO + endpoint,))
            return cur.fetchall()

        def cantidad(usuario_id):
            cur.execute("SELECT count(*) FROM push_suscripcion WHERE usuario_id = %s AND endpoint LIKE %s", (usuario_id, PREFIJO + "%"))
            return cur.fetchone()[0]

        cur.execute("SET LOCAL ROLE movil_api")
        try:
            check("id_usuario devuelve el id del usuario activo", db.id_usuario(con, user_a) == id_a)
            check("id_usuario de alguien que no existe -> None", db.id_usuario(con, "no-existe-nadie") is None)

            db.guardar_suscripcion(con, id_a, PREFIJO + "uno", "clave1", "auth1", 10)
            check("guarda la suscripción del usuario", filas("uno") == [(id_a, "clave1", "auth1")], filas("uno"))

            db.guardar_suscripcion(con, id_a, PREFIJO + "uno", "clave2", "auth2", 10)
            check("mandarla de nuevo no la duplica y actualiza las claves", filas("uno") == [(id_a, "clave2", "auth2")], filas("uno"))

            db.guardar_suscripcion(con, id_b, PREFIJO + "uno", "clave3", "auth3", 10)
            check("si el mismo celular entra con otro usuario, la suscripción pasa a ese usuario",
                  filas("uno") == [(id_b, "clave3", "auth3")], filas("uno"))

            check("un usuario no puede dar de baja la suscripción de otro", db.borrar_suscripcion(con, id_a, PREFIJO + "uno") is False
                  and len(filas("uno")) == 1)
            check("dar de baja la propia -> True y la borra", db.borrar_suscripcion(con, id_b, PREFIJO + "uno") is True and filas("uno") == [])
            check("dar de baja algo que ya no está -> False (sin error)", db.borrar_suscripcion(con, id_b, PREFIJO + "uno") is False)

            for n in range(5):
                db.guardar_suscripcion(con, id_a, PREFIJO + f"d{n}", "k", "a", 3)
            check("cada usuario conserva como mucho el máximo de dispositivos", cantidad(id_a) == 3, cantidad(id_a))
            check("y se descartan los más viejos (quedan los 3 últimos)",
                  [bool(filas(f"d{n}")) for n in range(5)] == [False, False, True, True, True])
            check("el límite de un usuario no toca los de otro", cantidad(id_b) == 0)
        finally:
            cur.execute("RESET ROLE")
    finally:
        con.rollback()
        cur = con.cursor()
        # Mientras la migración 004 no se aplique en el servidor, la tabla ni existe tras el rollback.
        cur.execute("SELECT to_regclass('push_suscripcion') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM push_suscripcion WHERE endpoint LIKE %s", (PREFIJO + "%",))
            quedaron = cur.fetchone()[0]
        else:
            quedaron = 0
        check("rollback: ninguna suscripción de prueba quedó en la base real", quedaron == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
