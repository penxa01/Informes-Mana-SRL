"""Migración de `movil/sql/001_movil.sql` y rol `movil_api` (movil/migraciones.py).

La prueba de base corre **dentro de una transacción que siempre se revierte**
(Postgres tiene DDL transaccional, roles incluidos): no deja columnas, índices
ni el rol `movil_api` en la base real de Pedidos. Si la base no responde, se
omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_migracion.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from movil import migraciones as mig

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def columna_existe(cur, tabla, columna):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (tabla, columna),
    )
    return cur.fetchone() is not None


def rol_existe(cur):
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'movil_api'")
    return cur.fetchone() is not None


print("=== migración + rol movil_api (transacción que se revierte) ===")
con = None
try:
    from src.Views.Pedidos.programarPedido import _conexion
    con = _conexion()
except Exception as e:  # base caída / sin red: se omite la prueba
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    try:
        existia_origen = columna_existe(cur, "pedido", "origen")
        existia_uuid = columna_existe(cur, "pedido", "uuid_cliente")
        existia_ubicacion = columna_existe(cur, "cliente", "ubicacion_maps")
        existia_rol = rol_existe(cur)

        mig.aplicar(con)
        mig.aplicar(con)
        check("aplicar la migración dos veces no rompe", True)
        check("columna origen creada", columna_existe(cur, "pedido", "origen"))
        check("columna uuid_cliente creada", columna_existe(cur, "pedido", "uuid_cliente"))
        check("columna cliente.ubicacion_maps creada", columna_existe(cur, "cliente", "ubicacion_maps"))

        def acepta_ubicacion(valor):
            cur.execute("SAVEPOINT s_ubi")
            try:
                cur.execute("UPDATE cliente SET ubicacion_maps = %s WHERE id_cliente = "
                            "(SELECT min(id_cliente) FROM cliente)", (valor,))
                ok = True
            except Exception:
                ok = False
            cur.execute("ROLLBACK TO SAVEPOINT s_ubi")
            return ok

        check("ubicacion_maps acepta un enlace de Google Maps",
              acepta_ubicacion("https://maps.app.goo.gl/abc123"))
        check("ubicacion_maps acepta NULL (todavía sin cargar)", acepta_ubicacion(None))
        check("ubicacion_maps rechaza javascript: (el celular la abre como enlace)",
              not acepta_ubicacion("javascript:alert(1)"))
        check("ubicacion_maps rechaza texto que no es un enlace", not acepta_ubicacion("Av. Siempreviva 742"))

        cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido) "
                    "VALUES (1, CURRENT_DATE, 'pendiente') RETURNING id_pedido, origen")
        id_pc, origen_pc = cur.fetchone()
        check("un INSERT al estilo de la PC (sin columnas nuevas) sigue andando y queda origen='pc'",
              origen_pc == "pc", origen_pc)

        cur.execute("SAVEPOINT s_check")
        try:
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen) "
                        "VALUES (1, CURRENT_DATE, 'pendiente', 'invalido')")
            rechaza_origen = False
        except Exception:
            rechaza_origen = True
        cur.execute("ROLLBACK TO SAVEPOINT s_check")
        check("el CHECK rechaza un origen inventado", rechaza_origen)

        import uuid
        u = str(uuid.uuid4())
        cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen, uuid_cliente) "
                    "VALUES (1, CURRENT_DATE, 'pendiente', 'movil', %s) RETURNING id_pedido", (u,))
        id1 = cur.fetchone()[0]
        cur.execute("SAVEPOINT s_dup")
        try:
            cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen, uuid_cliente) "
                        "VALUES (2, CURRENT_DATE, 'pendiente', 'movil', %s)", (u,))
            rechaza_duplicado = False
        except Exception:
            rechaza_duplicado = True
        cur.execute("ROLLBACK TO SAVEPOINT s_dup")
        check("uuid_cliente único (anti-duplicados de la cola offline)", rechaza_duplicado)

        cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido) "
                    "VALUES (3, CURRENT_DATE, 'pendiente') RETURNING id_pedido")
        id2 = cur.fetchone()[0]
        check("dos pedidos con uuid_cliente NULL no chocan entre sí (índice parcial)", id2 != id1)

        mig.asegurar_rol(con, "clave_de_prueba_123")
        mig.asegurar_rol(con, "clave_de_prueba_123")
        check("asegurar_rol dos veces no rompe", True)
        check("el rol movil_api existe", rol_existe(cur))

        # Los GRANT hechos antes en esta misma transacción ya son visibles para
        # lo que siga en ella (sin necesidad de commit): se puede probar el rol
        # y de todas formas revertir todo al final.
        try:
            cur.execute("SET LOCAL ROLE movil_api")

            cur.execute("SAVEPOINT s_login")
            try:
                cur.execute("SELECT password_hash FROM usuario LIMIT 1")
                puede_leer_hash = True
            except Exception:
                puede_leer_hash = False
            cur.execute("ROLLBACK TO SAVEPOINT s_login")
            check("movil_api puede leer password_hash (lo necesita para el login)", puede_leer_hash)

            def permitido(sql):
                """Corre `sql` como movil_api y devuelve si el permiso lo dejó pasar."""
                cur.execute("SAVEPOINT s_permiso")
                try:
                    cur.execute(sql)
                    ok = True
                except Exception:
                    ok = False
                cur.execute("ROLLBACK TO SAVEPOINT s_permiso")
                return ok

            check("movil_api puede leer la columna rol de usuario (decide qué ve cada perfil)",
                  permitido("SELECT rol FROM usuario LIMIT 1"))
            check("movil_api NO puede leer vendedor_id de usuario",
                  not permitido("SELECT vendedor_id FROM usuario LIMIT 1"))

            # Reparto: solo puede tocar lo que cambia una entrega.
            check("movil_api puede marcar estado/fecha de entrega en pedido",
                  permitido(f"UPDATE pedido SET estado_pedido = estado_pedido, fecha_entrega = fecha_entrega "
                            f"WHERE id_pedido = {id1}"))
            check("movil_api puede actualizar cantidad_entregada",
                  permitido("UPDATE detallepedido SET cantidad_entregada = cantidad_entregada WHERE false"))
            check("movil_api NO puede cambiar el cliente de un pedido",
                  not permitido(f"UPDATE pedido SET id_cliente = id_cliente WHERE id_pedido = {id1}"))
            check("movil_api NO puede cambiar la cantidad pedida",
                  not permitido("UPDATE detallepedido SET cantidad = cantidad WHERE false"))
            check("movil_api puede guardar la ubicación de un cliente",
                  permitido("UPDATE cliente SET ubicacion_maps = ubicacion_maps, ubicacion_lat = ubicacion_lat, "
                            "ubicacion_lng = ubicacion_lng WHERE false"))
            check("movil_api NO puede cambiar el nombre/dirección/teléfono de un cliente",
                  not permitido("UPDATE cliente SET nombre = nombre WHERE false")
                  and not permitido("UPDATE cliente SET direccion = direccion WHERE false")
                  and not permitido("UPDATE cliente SET telefono = telefono WHERE false"))
            check("movil_api NO puede borrar pedidos",
                  not permitido(f"DELETE FROM pedido WHERE id_pedido = {id1}"))
            check("movil_api NO puede tocar la tabla usuario",
                  not permitido("UPDATE usuario SET activo = activo WHERE false"))

            cur.execute("SAVEPOINT s_write_cliente")
            try:
                cur.execute("UPDATE cliente SET nombre = nombre WHERE false")
                puede_escribir_cliente = True
            except Exception:
                puede_escribir_cliente = False
            cur.execute("ROLLBACK TO SAVEPOINT s_write_cliente")
            check("movil_api NO puede escribir en cliente", not puede_escribir_cliente)

            cur.execute("SAVEPOINT s_insert_pedido")
            try:
                cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido) "
                            "VALUES (1, CURRENT_DATE, 'pendiente')")
                puede_crear_pedido = True
            except Exception:
                puede_crear_pedido = False
            cur.execute("ROLLBACK TO SAVEPOINT s_insert_pedido")
            check("movil_api puede crear pedidos (para eso existe)", puede_crear_pedido)
        finally:
            cur.execute("RESET ROLE")
    finally:
        con.rollback()
        cur = con.cursor()
        check("rollback: columna origen no quedó" if not existia_origen else "columna origen seguía existiendo (ya estaba)",
              columna_existe(cur, "pedido", "origen") == existia_origen)
        check("rollback: columna uuid_cliente no quedó" if not existia_uuid else "columna uuid_cliente seguía existiendo (ya estaba)",
              columna_existe(cur, "pedido", "uuid_cliente") == existia_uuid)
        check("rollback: columna ubicacion_maps no quedó" if not existia_ubicacion else "columna ubicacion_maps seguía existiendo (ya estaba)",
              columna_existe(cur, "cliente", "ubicacion_maps") == existia_ubicacion)
        check("rollback: el rol movil_api no quedó" if not existia_rol else "el rol movil_api ya existía antes",
              rol_existe(cur) == existia_rol)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
