"""`db.catalogo` (movil/api/db.py) y `GET /catalogo` (movil/api/routers/catalogo.py).

La parte de base solo hace SELECT (no hace falta transacción revertida: no
escribe nada). Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_catalogo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# OJO: movil/api/config.py lee las mismas PEDIDOS_DB_* que programarPedido.py
# (a propósito, ver guideline/Movil.md). Por eso la conexión real se abre
# ACÁ, antes de pisar esas variables con valores falsos para la parte de
# abajo (si no, programarPedido._conexion() también usaría los valores falsos).
print("=== db.catalogo contra la base real (solo lectura) ===")
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

from fastapi.testclient import TestClient

from movil.api import db, deps
from movil.api.app import app

if con is not None:
    try:
        clientes, productos, version = db.catalogo(con)
        check("2.104 clientes", len(clientes) == 2104, len(clientes))
        check("1.425 productos", len(productos) == 1425, len(productos))
        claves_cliente = set(clientes[0].keys())
        check("cliente: solo id/nombre/cuit/localidad (sin teléfono ni dirección)",
              claves_cliente == {"id", "nombre", "cuit", "localidad"}, claves_cliente)
        claves_producto = set(productos[0].keys())
        check("producto: solo id/nombre (sin stock)", claves_producto == {"id", "nombre"}, claves_producto)
        check("version es un hash estable (mismo contenido, mismo hash)",
              version == db.catalogo(con)[2])
        check("version no está vacía", len(version) == 64, version)  # sha256 hex
    finally:
        con.close()

print("=== GET /catalogo (wiring HTTP, con datos falsos) ===")


class _ConexionFalsa:
    def close(self):
        pass


db.conexion = lambda: _ConexionFalsa()
db.catalogo = lambda con: (
    [{"id": 1, "nombre": "DREAM SRL", "cuit": "20-1-1", "localidad": "MENDOZA"}],
    [{"id": "01VA133", "nombre": "VINO MALBEC"}],
    "hash-de-prueba",
)

client = TestClient(app)

r = client.get("/catalogo")
check("sin token -> 401", r.status_code == 401, r.status_code)

app.dependency_overrides[deps.usuario_actual] = lambda: "miguel"
try:
    r2 = client.get("/catalogo")
    check("con token -> 200", r2.status_code == 200, r2.status_code)
    body = r2.json()
    check("trae clientes, productos y version", set(body.keys()) == {"version", "clientes", "productos"}, body.keys())
    check("un cliente de ejemplo, sin teléfono/dirección", body["clientes"] == [
        {"id": 1, "nombre": "DREAM SRL", "cuit": "20-1-1", "localidad": "MENDOZA"}
    ], body["clientes"])
    check("un producto de ejemplo, sin stock", body["productos"] == [{"id": "01VA133", "nombre": "VINO MALBEC"}],
          body["productos"])
finally:
    app.dependency_overrides.pop(deps.usuario_actual, None)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
