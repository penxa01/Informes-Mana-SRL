"""Mapa de clientes, ubicación del reparto (movil/api/routers/mapa.py) y sesión única de la cuenta de reparto
(login + movil/api/deps.py): cableado HTTP, permisos por rol y códigos de respuesta. La lógica de base se prueba en
verificar_mapa_db.py.

No toca la base real: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_mapa_http.py
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

from movil.api import auth, db, deps
from movil.api.app import app

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


class _Conexion:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def close(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


conexion = _Conexion()
db.conexion = lambda: conexion
client = TestClient(app)

# ── el mapa ──────────────────────────────────────────────────────────────────
CLIENTES = [{"id": 1, "nombre": "DREAM SRL", "direccion": "Calle 1", "localidad": "SAN JUAN", "lat": -31.5375, "lng": -68.5364}]
POSICIONES = [{"usuario": "reparto", "nombre": "Personal de reparto", "lat": -31.52, "lng": -68.53, "precision_m": 12.5, "hace_seg": 7}]
db.clientes_con_ubicacion = lambda con: CLIENTES
db.posiciones_reparto = lambda con: POSICIONES
recibidas = []
db.guardar_posicion_reparto = lambda con, username, lat, lng, precision_m: recibidas.append((username, lat, lng, precision_m))
db.sesion_vigente = lambda con, username, sid: True   # la sesión única se prueba más abajo

cab = {"Authorization": f"Bearer {auth.crear_token('alguien')}"}
GPS = {"lat": -31.52, "lng": -68.53, "precision_m": 12.5}

print("=== quién puede: ver el mapa (reparto y admin) y mandar la posición (solo el reparto) ===")
for rol, ver, mandar in (("reparto", 200, 200), ("admin", 200, 403), ("superadmin", 200, 403), ("vendedor", 403, 403), (None, 401, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    recibidas.clear()
    codigos = [client.get("/mapa/clientes", headers=cab).status_code, client.get("/mapa/reparto", headers=cab).status_code]
    check(f"{etiqueta}: ver clientes y la posición del reparto -> {ver}", codigos == [ver, ver], codigos)
    check(f"{etiqueta}: mandar su posición -> {mandar}", client.post("/mapa/mi-ubicacion", json=GPS, headers=cab).status_code == mandar)
    if mandar != 200:
        check(f"{etiqueta}: nada llegó a la base", recibidas == [], recibidas)
check("sin token -> 401 en las tres", [client.get("/mapa/clientes").status_code, client.get("/mapa/reparto").status_code,
                                       client.post("/mapa/mi-ubicacion", json=GPS).status_code] == [401, 401, 401])

db.rol_activo = lambda con, username: "reparto"
print("=== GET /mapa/clientes y /mapa/reparto ===")
r = client.get("/mapa/clientes", headers=cab)
check("devuelve los clientes con su ubicación", r.status_code == 200 and r.json() == CLIENTES, r.text)
r = client.get("/mapa/reparto", headers=cab)
check("devuelve dónde está el reparto, con el nombre y hace cuánto", r.status_code == 200 and r.json() == [
    {"nombre": "Personal de reparto", "lat": -31.52, "lng": -68.53, "precision_m": 12.5, "hace_seg": 7}], r.text)
check("sin mostrar el nombre de usuario (solo el nombre de la persona)", "usuario" not in r.json()[0])
db.clientes_con_ubicacion = lambda con: []
db.posiciones_reparto = lambda con: []
check("sin clientes ni posición -> listas vacías (no error)", client.get("/mapa/clientes", headers=cab).json() == [] and client.get("/mapa/reparto", headers=cab).json() == [])

print("=== POST /mapa/mi-ubicacion ===")
recibidas.clear()
conexion.commits = conexion.rollbacks = 0
r = client.post("/mapa/mi-ubicacion", json=GPS, headers=cab)
check("se guarda -> 200", r.status_code == 200 and r.json() == {"ok": True}, r.text)
check("a la base le llega el usuario del token (no uno que mande el celular) y la posición", recibidas == [("alguien", -31.52, -68.53, 12.5)], recibidas)
check("y se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))
recibidas.clear()
check("la precisión es opcional", client.post("/mapa/mi-ubicacion", json={"lat": -31.5, "lng": -68.5}, headers=cab).status_code == 200 and recibidas[0][3] is None)
recibidas.clear()
for nombre, cuerpo in (("latitud fuera de rango", {"lat": 91, "lng": 0.5}), ("longitud fuera de rango", {"lat": 0.5, "lng": -181}),
                       ("punto 0,0 (GPS sin dato)", {"lat": 0, "lng": 0}), ("sin longitud", {"lat": 1}),
                       ("texto en vez de número", {"lat": "x", "lng": 1}), ("precisión negativa", {"lat": 1, "lng": 1, "precision_m": -5}),
                       ("un usuario que manda el celular (se ignora, no se acepta)", {"lat": 0, "lng": 0, "usuario": "otro"})):
    r = client.post("/mapa/mi-ubicacion", json=cuerpo, headers=cab)
    check(f"rechaza {nombre} -> 422", r.status_code == 422, r.status_code)
check("y nada de eso llegó a la base", recibidas == [], recibidas)


def _falla(*args):
    raise RuntimeError("simulado")


original = db.guardar_posicion_reparto
db.guardar_posicion_reparto = _falla
conexion.commits = conexion.rollbacks = 0
r = TestClient(app, raise_server_exceptions=False).post("/mapa/mi-ubicacion", json=GPS, headers=cab)
db.guardar_posicion_reparto = original
check("si falla algo -> 500 y se deshace", r.status_code == 500 and (conexion.commits, conexion.rollbacks) == (0, 1))

# ── una sola sesión para la cuenta de reparto ────────────────────────────────
print("=== una sola sesión para la cuenta de reparto (login y token) ===")
_HASH = bcrypt.hashpw(b"clave-de-prueba", bcrypt.gensalt()).decode("utf-8")
USUARIOS = {
    "reparto": {"password_hash": _HASH, "nombre": "Personal de reparto", "activo": True, "rol": "reparto"},
    "admin1": {"password_hash": _HASH, "nombre": "Admin", "activo": True, "rol": "admin"},
    "jose": {"password_hash": _HASH, "nombre": "Jose", "activo": True, "rol": "vendedor"},
}
SESION = {}   # lo que habría en usuario.sesion_id
db.buscar_usuario = lambda con, username: USUARIOS.get(username)
db.rol_activo = lambda con, username: USUARIOS[username]["rol"] if username in USUARIOS else None
db.fijar_sesion = lambda con, username, sid: SESION.__setitem__(username, sid)
db.sesion_vigente = lambda con, username, sid: SESION.get(username) == sid
db.pedidos_para_gestion = lambda con: []
auth._intentos.clear()


def entrar(usuario):
    r = client.post("/auth/login", json={"username": usuario, "clave": "clave-de-prueba"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def lista(cabecera):
    return client.get("/pedidos/gestion", headers=cabecera)


celular1 = entrar("reparto")
check("el primer celular entra y trabaja", lista(celular1).status_code == 200)
celular2 = entrar("reparto")
check("al iniciar sesión en un SEGUNDO celular, el segundo trabaja", lista(celular2).status_code == 200)
r = lista(celular1)
check("y el PRIMERO queda afuera: 401 con el motivo", r.status_code == 401 and r.json()["detail"] == deps.MENSAJE_OTRA_SESION, r.text)
check("en todas las rutas (no solo en la lista): también al mandar la posición o ver el mapa",
      client.post("/mapa/mi-ubicacion", json=GPS, headers=celular1).status_code == 401
      and client.get("/mapa/clientes", headers=celular1).status_code == 401)
celular3 = entrar("reparto")
check("un tercer celular desplaza al segundo", lista(celular3).status_code == 200 and lista(celular2).status_code == 401)
check("el primero, que volvió a entrar, ahora es el único que vale (entra de nuevo y desplaza)",
      lista(entrar("reparto")).status_code == 200 and lista(celular3).status_code == 401)

SESION.clear()
viejo = {"Authorization": f"Bearer {auth.crear_token('reparto')}"}   # un token de antes de que existiera el identificador
check("un token sin identificador vale mientras no haya sesión anotada (hasta que el reparto vuelva a entrar)", lista(viejo).status_code == 200)
entrar("reparto")
check("pero deja de valer apenas el reparto inicia sesión", lista(viejo).status_code == 401)

print("=== los demás perfiles NO tienen esa restricción ===")
SESION.clear()
a1, a2 = entrar("admin1"), entrar("admin1")
check("un admin puede tener la sesión abierta en dos celulares a la vez", lista(a1).status_code == 200 and lista(a2).status_code == 200)
j1, j2 = entrar("jose"), entrar("jose")
db.catalogo = lambda con: ([], [], "v1")
check("un vendedor también", client.get("/catalogo", headers=j1).status_code == 200 and client.get("/catalogo", headers=j2).status_code == 200)
check("iniciar sesión un admin no anota ninguna sesión (la columna es solo del reparto)", SESION == {}, SESION)
check("el token de un admin no lleva identificador de sesión", auth.leer_token(a1["Authorization"].split()[1])["sid"] is None)
check("el del reparto sí", auth.leer_token(celular1["Authorization"].split()[1])["sid"] is not None)

print("=== un login fallido no desplaza a nadie ===")
SESION.clear()
buena = entrar("reparto")
sesion_antes = dict(SESION)
r = client.post("/auth/login", json={"username": "reparto", "clave": "clave-mala"})
check("clave mala -> 401", r.status_code == 401)
check("y la sesión que estaba sigue valiendo (no se anotó nada)", SESION == sesion_antes and lista(buena).status_code == 200)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
