"""Rutas de los avisos (movil/api/routers/push.py): permisos por rol, validación de la suscripción
(sobre todo que el destino sea un servicio de push conocido) y códigos de respuesta. No toca la base
real: `db.*` queda reemplazado. La lógica de base se prueba en verificar_push_db.py.

Correr desde la raíz:  python movil/tests/verificar_push_http.py
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from fastapi.testclient import TestClient

from movil import vapid
from movil.api import auth, config, db, push
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
guardadas = []
bajas = []
db.id_usuario = lambda con, username: {"jose": 4, "reparto": 10}.get(username)
db.guardar_suscripcion = lambda con, uid, endpoint, p256dh, auth_, maximo: guardadas.append((uid, endpoint, p256dh, auth_, maximo))
db.borrar_suscripcion = lambda con, uid, endpoint: bajas.append((uid, endpoint)) or True

P256DH = vapid.generar()[0]                                   # un punto P-256 sin comprimir, como el de un celular
AUTH = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123:APA91b"


def cuerpo(endpoint=ENDPOINT, p256dh=P256DH, auth_=AUTH):
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth_}}


client = TestClient(app)


def cab(usuario="jose"):
    return {"Authorization": f"Bearer {auth.crear_token(usuario)}"}


print("=== destinos permitidos (que el servidor no le pegue a cualquier dirección) ===")
buenos = [
    "https://fcm.googleapis.com/fcm/send/xyz",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://web.push.apple.com/QGx",
    "https://wns2-par02p.notify.windows.com/w/?token=abc",
]
malos = [
    "http://fcm.googleapis.com/fcm/send/xyz",              # sin https
    "https://127.0.0.1/algo", "https://localhost/algo", "https://192.168.0.10/algo",
    "https://desktop-r8e4v7s.tail5a20aa.ts.net/panel",     # la propia red
    "https://fcm.googleapis.com.evil.com/fcm/send/x",      # el dominio como prefijo de otro
    "https://evilfcm.googleapis.com.evil.com/x",
    "https://fcm.googleapis.com@evil.com/fcm/send/x",      # el truco del usuario@
    "https://usuario:clave@fcm.googleapis.com/x",
    "https://fcm.googleapis.com:8443/x",                   # puerto raro
    "https://notgoogleapis.com/x", "ftp://fcm.googleapis.com/x", "javascript:alert(1)", "", "fcm.googleapis.com/x",
    "https://fcm.googleapis.com/" + "a" * 1100,            # demasiado largo
]
check("acepta los servicios de push de Chrome, Firefox, Safari y Edge", all(push.endpoint_permitido(u) for u in buenos))
check("rechaza todo lo demás", not any(push.endpoint_permitido(u) for u in malos), [u for u in malos if push.endpoint_permitido(u)])
check("un valor que no es texto no rompe", not push.endpoint_permitido(None) and not push.endpoint_permitido(123))

print("=== claves de la suscripción ===")
check("p256dh: 65 bytes que empiezan con 0x04", push.clave_p256dh_valida(P256DH))
check("p256dh rechaza lo corto, lo que no es base64url y lo que no empieza con 0x04",
      not push.clave_p256dh_valida("abc") and not push.clave_p256dh_valida("a b c") and not push.clave_p256dh_valida(None)
      and not push.clave_p256dh_valida(base64.urlsafe_b64encode(b"\x05" + bytes(64)).decode()))
check("auth: 16 bytes", push.secreto_auth_valido(AUTH) and not push.secreto_auth_valido("abc") and not push.secreto_auth_valido(None))

print("=== GET /push/clave ===")
config.VAPID_PUBLICA = ""
db.rol_activo = lambda con, username: "vendedor"
check("sin claves configuradas -> 503 (la app no ofrece avisos)", client.get("/push/clave", headers=cab()).status_code == 503)
config.VAPID_PUBLICA = "BClavePublicaDePrueba"
r = client.get("/push/clave", headers=cab())
check("con claves devuelve la pública", r.status_code == 200 and r.json() == {"clave": "BClavePublicaDePrueba"}, r.text)
check("sin token -> 401", client.get("/push/clave").status_code == 401)

print("=== quién puede (todos los perfiles; el dado de baja no) ===")
for rol, esperado in (("vendedor", 200), ("reparto", 200), ("admin", 200), ("superadmin", 200), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    check(f"{etiqueta}: GET /push/clave -> {esperado}", client.get("/push/clave", headers=cab()).status_code == esperado)
    check(f"{etiqueta}: POST /push/suscribir -> {esperado}", client.post("/push/suscribir", json=cuerpo(), headers=cab()).status_code == esperado)
    check(f"{etiqueta}: POST /push/baja -> {esperado}", client.post("/push/baja", json={"endpoint": ENDPOINT}, headers=cab()).status_code == esperado)

print("=== POST /push/suscribir ===")
db.rol_activo = lambda con, username: "reparto"
guardadas.clear()
conexion.commits = 0
r = client.post("/push/suscribir", json=cuerpo(), headers=cab("reparto"))
check("guarda la suscripción del usuario que la manda (no de otro)", r.status_code == 200 and r.json() == {"ok": True}
      and guardadas == [(10, ENDPOINT, P256DH, AUTH, push.MAX_SUSCRIPCIONES_POR_USUARIO)], guardadas)
check("hace commit", conexion.commits == 1)
guardadas.clear()
r = client.post("/push/suscribir", json={**cuerpo(), "expirationTime": None}, headers=cab("reparto"))
check("acepta la suscripción tal cual la entrega el navegador (con expirationTime)", r.status_code == 200 and len(guardadas) == 1, r.text)
check("mandarla de nuevo (la app lo hace al abrir) no da error", client.post("/push/suscribir", json=cuerpo(), headers=cab("reparto")).status_code == 200)

guardadas.clear()
for nombre, datos, codigo in (
    ("destino que no es un servicio de push", cuerpo(endpoint="https://127.0.0.1/x"), 422),
    ("destino con http", cuerpo(endpoint="http://fcm.googleapis.com/x"), 422),
    ("clave p256dh inválida", cuerpo(p256dh="abc"), 422),
    ("secreto auth inválido", cuerpo(auth_="abc"), 422),
    ("sin las claves", {"endpoint": ENDPOINT}, 422),
    ("sin destino", {"keys": {"p256dh": P256DH, "auth": AUTH}}, 422),
    ("destino larguísimo", cuerpo(endpoint="https://fcm.googleapis.com/" + "a" * 5000), 422),
    ("clave larguísima", cuerpo(p256dh="A" * 5000), 422),
):
    r = client.post("/push/suscribir", json=datos, headers=cab("reparto"))
    check(f"rechaza: {nombre} -> {codigo}", r.status_code == codigo, r.text[:120])
check("y nada de eso llegó a la base", guardadas == [])

print("=== POST /push/baja ===")
bajas.clear()
r = client.post("/push/baja", json={"endpoint": ENDPOINT}, headers=cab("reparto"))
check("da de baja la suscripción de este usuario", r.status_code == 200 and bajas == [(10, ENDPOINT)], bajas)
db.borrar_suscripcion = lambda con, uid, endpoint: False
check("dar de baja algo que ya no está también es OK (idempotente)",
      client.post("/push/baja", json={"endpoint": ENDPOINT}, headers=cab("reparto")).status_code == 200)
check("sin destino -> 422", client.post("/push/baja", json={}, headers=cab("reparto")).status_code == 422)

db.guardar_suscripcion = lambda *a: (_ for _ in ()).throw(RuntimeError("base caída"))
conexion.rollbacks = 0
try:
    cliente_sin_errores = TestClient(app, raise_server_exceptions=False)
    r = cliente_sin_errores.post("/push/suscribir", json=cuerpo(), headers=cab("reparto"))
    check("si la base falla al guardar: 500 y rollback (no queda a medias)", r.status_code == 500 and conexion.rollbacks == 1, r.status_code)
except Exception as e:
    check("si la base falla al guardar: 500 y rollback", False, repr(e))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
