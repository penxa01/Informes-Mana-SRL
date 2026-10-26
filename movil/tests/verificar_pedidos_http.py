"""POST /pedidos (movil/api/routers/pedidos.py): cableado HTTP — token,
validación de entrada, cliente/producto inexistente y respuesta de éxito.
La lógica real de líneas y de idempotencia ya se prueba en
verificar_pedidos_logica.py y verificar_pedidos_api.py.

No toca la base real: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_pedidos_http.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from fastapi.testclient import TestClient

from movil.api import db, deps
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


PEDIDO_OK = {
    "uuid": "11111111-1111-1111-1111-111111111111",
    "id_cliente": 1,
    "fecha_pedido": "2026-10-22",
    "lineas": [{"id_producto": "01VA133", "cantidad": 3}],
}

db.conexion = lambda: _ConexionFalsa()
db.cliente_existe = lambda con, id_cliente: id_cliente == 1
db.productos_inexistentes = lambda con, ids: [i for i in ids if i != "01VA133"]
db.crear_pedido = lambda con, uuid_cliente, id_cliente, fecha_pedido, lineas, creado_por: (42, False)

app.dependency_overrides[deps.vendedor_actual] = lambda: "miguel"
client = TestClient(app)

print("=== POST /pedidos ===")
r = client.post("/pedidos", json=PEDIDO_OK)
check("pedido válido -> 200", r.status_code == 200, r.text)
check("devuelve id_pedido y ya_existia", r.json() == {"id_pedido": 42, "ya_existia": False}, r.json())

r2 = client.post("/pedidos", json={**PEDIDO_OK, "lineas": [{"id_producto": "01VA133", "cantidad": 0}]})
check("cantidad inválida -> 422", r2.status_code == 422, r2.status_code)

r3 = client.post("/pedidos", json={**PEDIDO_OK, "id_cliente": 999})
check("cliente inexistente -> 422", r3.status_code == 422, r3.status_code)

r4 = client.post("/pedidos", json={**PEDIDO_OK, "lineas": [{"id_producto": "NO-EXISTE", "cantidad": 1}]})
check("producto inexistente -> 422", r4.status_code == 422, r4.status_code)

r5 = client.post("/pedidos", json={**PEDIDO_OK, "uuid": "no-es-un-uuid"})
check("uuid con formato inválido -> 422 (lo valida Pydantic)", r5.status_code == 422, r5.status_code)

app.dependency_overrides.pop(deps.vendedor_actual, None)
r6 = client.post("/pedidos", json=PEDIDO_OK)
check("sin token -> 401", r6.status_code == 401, r6.status_code)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
