"""Ubicación de clientes desde el celular (movil/api/routers/reparto.py): cableado HTTP, permisos por rol y
códigos de respuesta. La lógica de base se prueba en verificar_reparto_db.py. (Los pedidos por entregar, en camino y
las entregas, en verificar_gestion_http.py: el reparto ya no tiene rutas propias para eso.)

No toca la base real: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_reparto_http.py
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

from movil.api import auth, db
from movil.api.app import app

# La cuenta de reparto tiene una sola sesión (usuario.sesion_id): estas pruebas no tocan la base, así que se da por
# vigente. La regla real se prueba en verificar_sesion_unica.py.
db.sesion_vigente = lambda con, username, sid: True

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
cab = {"Authorization": f"Bearer {auth.crear_token('reparto')}"}
db.rol_activo = lambda con, username: "reparto"

print("=== las rutas viejas del reparto ya no existen ===")
for metodo, ruta in (("GET", "/reparto/pedidos"), ("POST", "/reparto/pedidos/7/entregar"), ("POST", "/reparto/pedidos/7/entrega-parcial")):
    check(f"{metodo} {ruta} -> 404 (ahora es /pedidos/gestion y /pedidos/{{id}}/...)",
          client.request(metodo, ruta, json={"lineas": [{"id_detalle": 1, "entregada": 1}]} if metodo == "POST" else None, headers=cab).status_code in (404, 405))

print("=== POST /reparto/clientes/{id}/ubicacion ===")
guardados = []
db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng: guardados.append((id_cliente, lat, lng)) or "guardada"
GPS = {"lat": -32.9226, "lng": -68.8572}
r = client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
check("ubicación válida -> 200", r.status_code == 200, r.text)
check("devuelve el enlace de Maps de ese punto",
      r.json() == {"id_cliente": 5, "ubicacion_maps": "https://www.google.com/maps/search/?api=1&query=-32.922600,-68.857200"}, r.json())
check("y se guardó lo que mandó el teléfono", guardados == [(5, -32.9226, -68.8572)], guardados)
conexion.commits = conexion.rollbacks = 0
client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
check("al guardar se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))
for resultado, codigo in (("sin_entregas", 404), ("ya_tiene", 409)):
    db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng, resultado=resultado: resultado
    r = client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
    check(f"'{resultado}' -> {codigo} con el motivo", r.status_code == codigo and r.json().get("detail"), r.text)


def _falla(con, id_cliente, lat, lng):
    raise RuntimeError("simulado")


db.guardar_ubicacion_cliente = _falla
conexion.commits = conexion.rollbacks = 0
r = TestClient(app, raise_server_exceptions=False).post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
check("si falla algo -> 500 y se deshace (no queda a medias)", r.status_code == 500 and (conexion.commits, conexion.rollbacks) == (0, 1))

guardados.clear()
db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng: guardados.append(id_cliente) or "guardada"
for etiqueta, cuerpo in (("latitud fuera de rango", {"lat": 91, "lng": 0.5}), ("longitud fuera de rango", {"lat": 0.5, "lng": -181}),
                         ("punto 0,0 (GPS sin dato)", {"lat": 0, "lng": 0}), ("sin longitud", {"lat": 1}),
                         ("texto en vez de número", {"lat": "x", "lng": 1})):
    r = client.post("/reparto/clientes/5/ubicacion", json=cuerpo, headers=cab)
    check(f"{etiqueta} -> 422 y no se guarda", r.status_code == 422 and not guardados, r.status_code)
check("un id de cliente que no es número -> 422", client.post("/reparto/clientes/abc/ubicacion", json=GPS, headers=cab).status_code == 422)
for rol, esperado in (("vendedor", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    check(f"rol {rol}: no puede guardar ubicaciones -> {esperado}",
          client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab).status_code == esperado and not guardados)
check("sin token -> 401", client.post("/reparto/clientes/5/ubicacion", json=GPS).status_code == 401)
for rol in ("reparto", "admin", "superadmin"):
    guardados.clear()
    db.rol_activo = lambda con, username, rol=rol: rol
    check(f"rol {rol}: sí puede",
          client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab).status_code == 200 and guardados == [5])

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
