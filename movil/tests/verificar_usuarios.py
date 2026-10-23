"""Alta de usuarios de la app móvil (`movil/usuarios.py`), en una transacción que
siempre se revierte: no deja usuarios en la base real. Si la base no responde, se
omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_usuarios.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import bcrypt

from movil import usuarios

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=== crear_usuario (transacción que se revierte) ===")

try:
    usuarios.crear_usuario(None, "x", "y", "X", "capitan")
    check("un rol desconocido se rechaza", False)
except ValueError:
    check("un rol desconocido se rechaza", True)

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
        u = "reparto_prueba_tmp"
        creado = usuarios.crear_usuario(con, u, "clave-de-prueba", "Prueba de reparto", "reparto")
        check("crea el usuario nuevo", creado is True)

        cur.execute("SELECT password_hash, rol, activo, vendedor_id FROM usuario WHERE username = %s", (u,))
        hash_clave, rol, activo, vendedor_id = cur.fetchone()
        check("la clave queda en bcrypt y verifica", bcrypt.checkpw(b"clave-de-prueba", hash_clave.encode("ascii")))
        check("una clave distinta no verifica", not bcrypt.checkpw(b"otra", hash_clave.encode("ascii")))
        check("rol 'reparto', activo y sin vendedor asociado", (rol, activo, vendedor_id) == ("reparto", True, None))

        de_nuevo = usuarios.crear_usuario(con, u, "OTRA_CLAVE", "Otro nombre", "vendedor")
        check("si ya existe no lo crea otra vez", de_nuevo is False)
        cur.execute("SELECT password_hash, rol FROM usuario WHERE username = %s", (u,))
        hash2, rol2 = cur.fetchone()
        check("y no le pisa la clave ni el rol", hash2 == hash_clave and rol2 == "reparto")
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT 1 FROM usuario WHERE username = 'reparto_prueba_tmp'")
        check("rollback: el usuario de prueba no quedó", cur.fetchone() is None)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
