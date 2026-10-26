"""POST /auth/login (movil/api/routers/auth.py): que la ruta esté bien
enchufada a auth.py y db.py. La lógica de bcrypt/token/bloqueo ya se prueba
a fondo en verificar_auth.py; acá solo se prueba el cableado HTTP.

No toca la base real: `db.conexion`/`db.buscar_usuario` quedan reemplazados.

Correr desde la raíz:  python movil/tests/verificar_login_api.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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


_HASH = bcrypt.hashpw(b"laClaveCorrecta123", bcrypt.gensalt()).decode("utf-8")
_USUARIOS = {"miguel": {"password_hash": _HASH, "nombre": "MIGUEL ORTUÑO", "activo": True, "rol": "vendedor"}}

db.conexion = lambda: _ConexionFalsa()
db.buscar_usuario = lambda con, username: _USUARIOS.get(username)

client = TestClient(app)

print("=== POST /auth/login ===")
r = client.post("/auth/login", json={"username": "miguel", "clave": "laClaveCorrecta123"})
check("login correcto -> 200 con token y nombre", r.status_code == 200, r.text)
body = r.json()
check("devuelve el nombre del usuario", body.get("nombre") == "MIGUEL ORTUÑO", body)
check("devuelve el rol (decide la pantalla de la app)", body.get("rol") == "vendedor", body)
check("el token es válido", "token" in body and auth.verificar_token(body["token"]) == "miguel")

r2 = client.post("/auth/login", json={"username": "miguel", "clave": "mala"})
check("clave mala -> 401", r2.status_code == 401, r2.status_code)

r3 = client.post("/auth/login", json={"username": "fantasma", "clave": "x"})
check("usuario inexistente -> 401 (mismo trato que clave mala)", r3.status_code == 401, r3.status_code)

r4 = client.post("/auth/login", json={"username": "miguel"})
check("falta la clave -> 422 (validación de Pydantic)", r4.status_code == 422, r4.status_code)


def _rota():
    raise ConnectionError("simulado: la base no responde")


db.conexion = _rota
r5 = client.post("/auth/login", json={"username": "miguel", "clave": "laClaveCorrecta123"})
check("base caída -> 503 prolijo, no un 500 crudo", r5.status_code == 503, r5.status_code)
db.conexion = lambda: _ConexionFalsa()

print("=== usuario dado de baja: el token deja de servir al instante ===")
db.catalogo = lambda con: ([], [], "v1")
token = auth.crear_token("miguel")
cabecera = {"Authorization": f"Bearer {token}"}

db.rol_activo = lambda con, username: "vendedor"
check("token válido + usuario activo -> 200", client.get("/catalogo", headers=cabecera).status_code == 200)

db.rol_activo = lambda con, username: None
r6 = client.get("/catalogo", headers=cabecera)
check("el MISMO token, con el usuario dado de baja -> 401", r6.status_code == 401, r6.status_code)
check("y el motivo es claro", "baja" in r6.json().get("detail", ""), r6.json())

llamado = []
db.rol_activo = lambda con, username: llamado.append(username) or "vendedor"
check("sin token -> 401", client.get("/catalogo").status_code == 401)
check("con un token inválido -> 401", client.get("/catalogo", headers={"Authorization": "Bearer xxx"}).status_code == 401)
check("sin token válido ni se consulta la base de usuarios", llamado == [], llamado)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
