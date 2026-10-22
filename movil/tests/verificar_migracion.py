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
        existia_rol = rol_existe(cur)

        mig.aplicar(con)
        mig.aplicar(con)
        check("aplicar la migración dos veces no rompe", True)
        check("columna origen creada", columna_existe(cur, "pedido", "origen"))
        check("columna uuid_cliente creada", columna_existe(cur, "pedido", "uuid_cliente"))

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

            cur.execute("SAVEPOINT s_rol_col")
            try:
                cur.execute("SELECT rol FROM usuario LIMIT 1")
                puede_leer_rol = True
            except Exception:
                puede_leer_rol = False
            cur.execute("ROLLBACK TO SAVEPOINT s_rol_col")
            check("movil_api NO puede leer la columna rol de usuario", not puede_leer_rol)

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
        check("rollback: el rol movil_api no quedó" if not existia_rol else "el rol movil_api ya existía antes",
              rol_existe(cur) == existia_rol)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
