"""Esqueleto de la API móvil (movil/api/app.py): arranca, expone /health y no
se cae si la base no responde.

No toca la base real: usa credenciales falsas a propósito.

Correr desde la raíz:  python movil/tests/verificar_api.py
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

from movil.api.app import app

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


client = TestClient(app)

print("=== esqueleto de la API ===")
r = client.get("/health")
check("/health responde 200 aunque la base esté mal configurada", r.status_code == 200, r.status_code)
body = r.json()
check("api: ok", body.get("api") == "ok", body)
check("db: reporta el error sin tirar abajo la API", str(body.get("db", "")).startswith("error"), body)

r2 = client.get("/no-existe")
check("una ruta inexistente da 404 (la API arrancó normal)", r2.status_code == 404, r2.status_code)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
