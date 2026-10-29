"""Ciclo del notificador (movil/avisos/worker.py + almacen.py) contra la base real, como `movil_api` (con sus
permisos reales) y dentro de una transacción que siempre se revierte. El envío es SIMULADO: no hay red ni se
le manda nada a nadie. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_avisos_db.py
"""
import logging
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
print("=== avisos: ciclo contra la base (transacción que se revierte, con el rol movil_api) ===")
try:
    from src.Views.Pedidos.programarPedido import _conexion
    real = _conexion()
except Exception as e:
    real = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")

from movil import migraciones
from movil.avisos import almacen, worker

PREFIJO = "https://fcm.googleapis.com/fcm/send/aviso-test-"


class _ConSavepoint:
    """commit() y rollback() de `ciclo` actúan sobre un savepoint: nunca sobre la transacción entera."""

    def __init__(self, conexion):
        self._real = conexion
        self._cur = conexion.cursor()
        self._cur.execute("SAVEPOINT sp_aviso")

    def cursor(self):
        return self._real.cursor()

    def commit(self):
        self._cur.execute("RELEASE SAVEPOINT sp_aviso")
        self._cur.execute("SAVEPOINT sp_aviso")

    def rollback(self):
        self._cur.execute("ROLLBACK TO SAVEPOINT sp_aviso")


if real is not None:
    real.autocommit = False
    cur = real.cursor()
    logging.disable(logging.CRITICAL)   # los errores simulados son a propósito: que no ensucien la salida
    try:
        migraciones.aplicar(real)
        migraciones.asegurar_permisos(real)   # no depende de cómo haya quedado el servidor

        def usuario(rol, n=1):
            cur.execute("SELECT id, username FROM usuario WHERE activo AND rol = %s ORDER BY id LIMIT %s", (rol, n))
            return cur.fetchall()

        (id_admin, u_admin), = usuario("admin")[:1]
        (id_super, u_super), = usuario("superadmin")[:1]
        (id_reparto, u_reparto), = usuario("reparto")[:1]
        (id_v1, u_v1), (id_v2, u_v2) = usuario("vendedor", 2)[:2]
        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente LIMIT 1")
        id_cliente = cur.fetchone()[0]

        def suscribir(id_usuario, nombre):
            cur.execute("INSERT INTO push_suscripcion (usuario_id, endpoint, p256dh, auth) VALUES (%s, %s, 'k', 'a')",
                        (id_usuario, PREFIJO + nombre))

        for uid, nombre in ((id_admin, "admin"), (id_super, "super"), (id_reparto, "reparto"), (id_v1, "vend1"), (id_v2, "vend2")):
            suscribir(uid, nombre)

        def pedido(origen, estado, creado_por, fecha_entrega=None):
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, fecha_entrega, origen, creado_por) "
                        "VALUES (%s, CURRENT_DATE, %s, %s, %s, %s) RETURNING id_pedido",
                        (id_cliente, estado, fecha_entrega, origen, creado_por))
            return cur.fetchone()[0]

        def estado(id_pedido, nuevo):
            cur.execute("UPDATE pedido SET estado_pedido = %s, fecha_entrega = COALESCE(fecha_entrega, CURRENT_DATE) WHERE id_pedido = %s",
                        (nuevo, id_pedido))

        enviados = []
        respuestas = {}   # sufijo del endpoint -> resultado simulado (por defecto "ok")

        def enviar(destino, payload):
            enviados.append((destino["endpoint"][len(PREFIJO):], payload["evento"], payload["id_pedido"]))
            return respuestas.get(destino["endpoint"][len(PREFIJO):], "ok")

        def quienes(evento, id_pedido):
            return sorted(q for q, e, i in enviados if e == evento and i == id_pedido)

        def como_api():
            cur.execute("SET LOCAL ROLE movil_api")

        def como_dueno():
            cur.execute("RESET ROLE")

        como_api()
        con = _ConSavepoint(real)
        intentos = {}

        def correr():
            return worker.ciclo(con, enviar, intentos)

        print("--- siembra inicial")
        check("la tabla de avisos arranca vacía", almacen.hay_registros(con) is False)
        anotados = almacen.sembrar(con)
        check("siembra lo que ya existe (así no llega un aviso por cada pedido viejo)", anotados > 0 and almacen.hay_registros(con), anotados)
        check("sembrar dos veces no duplica nada", almacen.sembrar(con) == 0)
        r = correr()
        check("después de sembrar, el primer ciclo no avisa nada", r == {"enviados": 0, "silenciados": 0, "bajas": 0, "fallidos": 0} and enviados == [], r)

        print("--- un pedido nuevo de un vendedor")
        como_dueno()
        p1 = pedido("movil", "pendiente", u_v1)
        como_api()
        r = correr()
        check("avisa a admin y superadmin, y no al vendedor que lo cargó ni al reparto ni a otro vendedor",
              quienes("nuevo", p1) == ["admin", "super"], quienes("nuevo", p1))
        check("el ciclo lo cuenta", r["enviados"] == 2, r)
        n = len(enviados)
        correr()
        check("otro ciclo no repite el aviso", len(enviados) == n)

        print("--- el pedido se programa")
        como_dueno()
        estado(p1, "programado")
        como_api()
        correr()
        check("avisa solo al reparto", quienes("programado", p1) == ["reparto"], quienes("programado", p1))

        print("--- el pedido se entrega")
        como_dueno()
        estado(p1, "entregado")
        como_api()
        correr()
        check("avisa a admin, superadmin y al vendedor que lo cargó (no al reparto ni a otro vendedor)",
              quienes("entregado", p1) == ["admin", "super", "vend1"], quienes("entregado", p1))
        n = len(enviados)
        correr()
        check("y no se repite", len(enviados) == n)
        check("un pedido ya entregado y avisado deja de revisarse", p1 not in [p["id_pedido"] for p in almacen.pedidos_a_revisar(con)])

        print("--- un pedido cargado desde la PC")
        como_dueno()
        p2 = pedido("pc", "pendiente", None)
        como_api()
        correr()
        check("pendiente: no se avisa (la PC no avisa de lo que carga)", [e for e in enviados if e[2] == p2] == [])
        como_dueno()
        estado(p2, "programado")
        como_api()
        correr()
        check("programado: avisa al reparto", quienes("programado", p2) == ["reparto"])
        como_dueno()
        estado(p2, "entregado")
        como_api()
        correr()
        check("entregado: solo admin y superadmin (no hay vendedor que lo cargó)", quienes("entregado", p2) == ["admin", "super"], quienes("entregado", p2))

        print("--- un pedido que se saltea pasos")
        como_dueno()
        p3 = pedido("movil", "entregado", u_v2)
        como_api()
        r = correr()
        check("pasó directo a entregado: avisa solo la entrega y no lo viejo",
              quienes("entregado", p3) == ["admin", "super", "vend2"] and quienes("nuevo", p3) == [] and quienes("programado", p3) == [], r)
        check("lo que se salteó queda silenciado", r["silenciados"] == 2, r)

        print("--- suscripción muerta")
        como_dueno()
        p4 = pedido("movil", "pendiente", u_v1)
        como_api()
        respuestas["admin"] = "muerta"
        r = correr()
        como_dueno()
        cur.execute("SELECT count(*) FROM push_suscripcion WHERE endpoint = %s", (PREFIJO + "admin",))
        check("si el servicio de push dice que la suscripción murió, se borra", cur.fetchone()[0] == 0 and r["bajas"] == 1, r)
        como_api()
        check("y el aviso queda resuelto (le llegó al otro destinatario)", quienes("nuevo", p4) == ["admin", "super"] and r["enviados"] == 1, r)
        respuestas.clear()
        como_dueno()
        suscribir(id_admin, "admin")
        como_api()

        print("--- fallas pasajeras (sin internet, servicio caído)")
        como_dueno()
        p5 = pedido("movil", "pendiente", u_v1)
        como_api()
        respuestas.update({"admin": "error", "super": "error"})
        r = correr()
        check("si todos fallan el aviso NO se da por resuelto", r["fallidos"] == 1 and r["enviados"] == 0, r)
        antes = len(enviados)
        correr()
        check("el ciclo siguiente lo reintenta", len(enviados) == antes + 2)
        respuestas.clear()
        r = correr()
        check("cuando se arregla, llega y queda resuelto", r["enviados"] == 2, r)
        n = len(enviados)
        correr()
        check("sin repetirse", len(enviados) == n)

        como_dueno()
        p6 = pedido("movil", "pendiente", u_v1)
        como_api()
        respuestas.update({"admin": "error", "super": "error"})
        intentos.clear()
        for _ in range(worker.MAX_INTENTOS):
            correr()
        n = len(enviados)
        correr()
        check("si falla siempre, se rinde después de %s intentos (no insiste para siempre)" % worker.MAX_INTENTOS, len(enviados) == n)
        respuestas.clear()

        como_dueno()
        p7 = pedido("movil", "pendiente", u_v1)
        como_api()
        respuestas["admin"] = "error"
        r = correr()
        check("si a uno le llega y a otro falla, queda resuelto (no se le repite al que ya le llegó)",
              r["enviados"] == 1 and r["fallidos"] == 0 and quienes("nuevo", p7) == ["admin", "super"], r)
        respuestas.clear()

        print("--- usuarios dados de baja y sin suscriptores")
        como_dueno()
        cur.execute("UPDATE usuario SET activo = false WHERE id = %s", (id_super,))
        p8 = pedido("movil", "pendiente", u_v1)
        como_api()
        correr()
        check("un usuario dado de baja no recibe avisos", quienes("nuevo", p8) == ["admin"], quienes("nuevo", p8))

        como_dueno()
        cur.execute("DELETE FROM push_suscripcion WHERE endpoint LIKE %s", (PREFIJO + "%",))
        p9 = pedido("movil", "pendiente", u_v1)
        como_api()
        r = correr()
        check("sin nadie suscripto no se manda nada, pero el aviso se da por resuelto", quienes("nuevo", p9) == [] and r["enviados"] == 0, r)
        como_dueno()
        suscribir(id_admin, "admin")
        como_api()
        n = len(enviados)
        correr()
        check("quien se suscribe después no recibe de golpe lo que pasó antes", len(enviados) == n)
    finally:
        real.rollback()
        cur = real.cursor()
        cur.execute("SELECT to_regclass('push_suscripcion') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM push_suscripcion WHERE endpoint LIKE %s", (PREFIJO + "%",))
            quedaron = cur.fetchone()[0]
        else:
            quedaron = 0   # la migración 004 todavía no está aplicada en el servidor: la tabla ni existe
        check("rollback: no quedó ninguna suscripción de prueba en la base real", quedaron == 0)
        real.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
