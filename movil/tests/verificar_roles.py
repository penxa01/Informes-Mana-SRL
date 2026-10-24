"""Perfiles de la API (vendedor / reparto / admin): quién puede qué.

Parte 1 (sin base): cableado HTTP con `db.rol_activo` reemplazado. Un vendedor y el
admin cargan pedidos y bajan el catálogo; el reparto NO; un usuario dado de baja no entra.
Parte 2 (base real): `db.rol_activo` / `db.buscar_usuario` conectados como `movil_api`
(con sus permisos reales), dentro de una transacción que siempre se revierte.

Correr desde la raíz:  python movil/tests/verificar_roles.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# La conexión real se abre ANTES de fijar las variables de prueba: la API móvil y la app de
# escritorio leen los mismos nombres PEDIDOS_DB_* y las de prueba apuntan a una base falsa.
_con_real = None
_error_base = None
try:
    from src.Views.Pedidos.programarPedido import _conexion
    _con_real = _conexion()
except Exception as e:  # base caída / sin red: la parte 3 se omite
    _error_base = f"{type(e).__name__}: {str(e)[:80]}"

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

import bcrypt
from fastapi.testclient import TestClient

from movil.api import auth, db
from movil.api.app import app

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


class _ConexionFalsa:
    def close(self):
        pass

    def commit(self):
        pass


print("=== 1. quién puede qué (HTTP, sin base) ===")
creados = []
db.conexion = lambda: _ConexionFalsa()
db.catalogo = lambda con: ([], [], "v1")
db.cliente_existe = lambda con, id_cliente: True
db.productos_inexistentes = lambda con, ids: []
db.crear_pedido = lambda con, uuid_cliente, id_cliente, fecha_pedido, lineas, creado_por: (
    creados.append(creado_por) or (42, False))

PEDIDO = {
    "uuid": "11111111-1111-1111-1111-111111111111",
    "id_cliente": 1,
    "fecha_pedido": "2026-10-23",
    "lineas": [{"id_producto": "01VA133", "cantidad": 3}],
}
client = TestClient(app)
cabecera = {"Authorization": f"Bearer {auth.crear_token('alguien')}"}

for rol, esperado in (("vendedor", 200), ("admin", 200), ("superadmin", 200), ("reparto", 403), ("capitan", 403), ("", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'" if rol else "rol vacío"
    check(f"{etiqueta}: GET /catalogo -> {esperado}", client.get("/catalogo", headers=cabecera).status_code == esperado)
    antes = len(creados)
    r = client.post("/pedidos", json=PEDIDO, headers=cabecera)
    check(f"{etiqueta}: POST /pedidos -> {esperado}", r.status_code == esperado, r.status_code)
    check(f"{etiqueta}: " + ("el pedido se crea" if esperado == 200 else "no se crea ningún pedido"),
          (len(creados) == antes + 1) == (esperado == 200))

db.rol_activo = lambda con, username: "reparto"
r = client.post("/pedidos", json=PEDIDO, headers=cabecera)
check("el 403 explica el motivo", "permiso" in r.json().get("detail", ""), r.json())

# El mismo token: si le cambian el rol en la base, cambia lo que puede hacer, sin volver a entrar.
db.rol_activo = lambda con, username: "vendedor"
check("mismo token, rol vendedor -> 200", client.get("/catalogo", headers=cabecera).status_code == 200)
db.rol_activo = lambda con, username: "reparto"
check("mismo token, ahora con rol reparto -> 403 al instante", client.get("/catalogo", headers=cabecera).status_code == 403)

llamado = []
db.rol_activo = lambda con, username: llamado.append(username) or "vendedor"
check("sin token -> 401", client.get("/catalogo").status_code == 401)
check("sin token válido ni se consulta la base", llamado == [])

print("=== 2. el login informa el rol ===")
_HASH = bcrypt.hashpw(b"clave-de-prueba", bcrypt.gensalt()).decode("utf-8")
db.buscar_usuario = lambda con, username: (
    {"password_hash": _HASH, "nombre": "Personal de reparto", "activo": True, "rol": "reparto"}
    if username == "reparto" else None)
r = client.post("/auth/login", json={"username": "reparto", "clave": "clave-de-prueba"})
check("login de reparto -> 200", r.status_code == 200, r.text)
check("con rol 'reparto'", r.json().get("rol") == "reparto", r.json())
check("y el token es del usuario", auth.verificar_token(r.json()["token"]) == "reparto")

print("=== 3. contra la base real, con los permisos de movil_api ===")
con = _con_real
if con is None:
    print(f"  OMITIDO  no hay conexión a la base ({_error_base})")
else:
    import importlib
    from movil import migraciones as mig

    # `db` quedó con funciones reemplazadas arriba: se recarga para probar las reales.
    db = importlib.reload(db)
    con.autocommit = False
    cur = con.cursor()
    try:
        mig.asegurar_permisos(con)     # idempotente; así la prueba no depende de cómo quedó el servidor
        cur.execute("SELECT 1 FROM usuario WHERE username = 'reparto'")
        hay_reparto = cur.fetchone() is not None
        if not hay_reparto:
            from movil import usuarios
            usuarios.crear_usuario(con, "reparto", "clave-de-prueba", "Personal de reparto", "reparto")
        cur.execute("UPDATE usuario SET activo = true WHERE username = 'reparto'")
        cur.execute("INSERT INTO usuario (username, password_hash, nombre, rol, activo) "
                    "VALUES ('baja_prueba_tmp', 'x', 'Baja', 'vendedor', false)")

        cur.execute("SET LOCAL ROLE movil_api")
        check("reparto -> 'reparto'", db.rol_activo(con, "reparto") == "reparto")
        check("un vendedor real -> 'vendedor'", db.rol_activo(con, "jose") == "vendedor")
        check("admin -> 'admin'", db.rol_activo(con, "admin") == "admin")
        check("usuario inexistente -> None", db.rol_activo(con, "no_existe_zzz") is None)
        check("usuario dado de baja -> None", db.rol_activo(con, "baja_prueba_tmp") is None)
        check("usuario_activo sigue andando (activo / baja)",
              db.usuario_activo(con, "reparto") is True and db.usuario_activo(con, "baja_prueba_tmp") is False)
        fila = db.buscar_usuario(con, "reparto")
        check("buscar_usuario trae el rol para el login", fila is not None and fila["rol"] == "reparto")   # sin imprimir la fila: trae el hash
        cur.execute("RESET ROLE")
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM usuario WHERE username = 'baja_prueba_tmp'")
        check("rollback: el usuario de prueba no quedó", cur.fetchone()[0] == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
