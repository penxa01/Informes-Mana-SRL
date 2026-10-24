"""Rutas de reparto (movil/api/routers/reparto.py): cableado HTTP, permisos por rol y
códigos de respuesta. La lógica de base se prueba en verificar_reparto_db.py.

No toca la base real: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_reparto_http.py
"""
import datetime as dt
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

PEDIDO = {
    "id_pedido": 7, "estado": "programado", "fecha_pedido": dt.date(2026, 10, 20), "fecha_entrega": dt.date(2026, 10, 23),
    "cliente": {"id": 1, "nombre": "DREAM SRL", "direccion": "Calle 1, MENDOZA", "telefono": "261-555",
                "localidad": "MENDOZA", "ubicacion_maps": "https://maps.app.goo.gl/x",
                "ubicacion_lat": -32.9, "ubicacion_lng": -68.8},
    "lineas": [{"id_producto": "01VA133", "nombre": "VINO MALBEC", "cantidad": 3, "entregada": 1}],
}
db.pedidos_para_reparto = lambda con: [PEDIDO]
db.marcar_entregado = lambda con, id_pedido: "entregado"

client = TestClient(app)
cab = {"Authorization": f"Bearer {auth.crear_token('reparto')}"}

print("=== quién puede ===")
for rol, esperado in (("reparto", 200), ("admin", 200), ("superadmin", 200), ("vendedor", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    check(f"{etiqueta}: GET /reparto/pedidos -> {esperado}", client.get("/reparto/pedidos", headers=cab).status_code == esperado)
    check(f"{etiqueta}: POST /reparto/pedidos/7/entregar -> {esperado}",
          client.post("/reparto/pedidos/7/entregar", headers=cab).status_code == esperado)
check("sin token -> 401", client.get("/reparto/pedidos").status_code == 401)

db.rol_activo = lambda con, username: "reparto"
print("=== GET /reparto/pedidos ===")
r = client.get("/reparto/pedidos", headers=cab)
cuerpo = r.json()
check("devuelve la lista", r.status_code == 200 and len(cuerpo) == 1, r.text)
p = cuerpo[0]
check("con estado, fechas y líneas", (p["id_pedido"], p["estado"], p["fecha_entrega"]) == (7, "programado", "2026-10-23")
      and p["lineas"][0]["cantidad"] == 3 and p["lineas"][0]["entregada"] == 1, p)
check("con dirección, teléfono y ubicación del cliente",
      (p["cliente"]["direccion"], p["cliente"]["telefono"], p["cliente"]["ubicacion_maps"], p["cliente"]["ubicacion_lat"])
      == ("Calle 1, MENDOZA", "261-555", "https://maps.app.goo.gl/x", -32.9), p["cliente"])

db.pedidos_para_reparto = lambda con: []
check("sin pedidos -> lista vacía (no error)", client.get("/reparto/pedidos", headers=cab).json() == [])

print("=== POST /reparto/pedidos/{id}/entregar ===")
for resultado, codigo, ya in (("entregado", 200, False), ("ya_estaba", 200, True),
                              ("no_existe", 404, None), ("sin_programar", 409, None)):
    db.marcar_entregado = lambda con, id_pedido, resultado=resultado: resultado
    r = client.post("/reparto/pedidos/7/entregar", headers=cab)
    check(f"'{resultado}' -> {codigo}", r.status_code == codigo, r.text)
    if codigo == 200:
        check(f"'{resultado}': ya_estaba={ya} y devuelve el id", r.json() == {"id_pedido": 7, "ya_estaba": ya}, r.json())
    else:
        check(f"'{resultado}': el mensaje explica el motivo", "pedido 7" in r.json()["detail"], r.json())

conexion.commits = conexion.rollbacks = 0
db.marcar_entregado = lambda con, id_pedido: "entregado"
client.post("/reparto/pedidos/7/entregar", headers=cab)
check("al entregar se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))


def _falla(con, id_pedido):
    raise RuntimeError("simulado")


db.marcar_entregado = _falla
conexion.commits = conexion.rollbacks = 0
try:
    cliente_sin_errores = TestClient(app, raise_server_exceptions=False)
    r = cliente_sin_errores.post("/reparto/pedidos/7/entregar", headers=cab)
    check("si falla algo -> 500 y se deshace (no queda a medias)",
          r.status_code == 500 and (conexion.commits, conexion.rollbacks) == (0, 1), (r.status_code, conexion.rollbacks))
except Exception as e:
    check("si falla algo se deshace", False, str(e))

r = client.post("/reparto/pedidos/abc/entregar", headers=cab)
check("id que no es número -> 422", r.status_code == 422, r.status_code)

print("=== POST /reparto/clientes/{id}/ubicacion ===")
guardados = []
db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng: guardados.append((id_cliente, lat, lng)) or "guardada"
GPS = {"lat": -32.9226, "lng": -68.8572}
r = client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
check("ubicación válida -> 200", r.status_code == 200, r.text)
check("devuelve el enlace de Maps de ese punto",
      r.json() == {"id_cliente": 5, "ubicacion_maps": "https://www.google.com/maps/search/?api=1&query=-32.922600,-68.857200"}, r.json())
check("y se guardó lo que mandó el teléfono", guardados == [(5, -32.9226, -68.8572)], guardados)
for resultado, codigo in (("sin_entregas", 404), ("ya_tiene", 409)):
    db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng, resultado=resultado: resultado
    r = client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab)
    check(f"'{resultado}' -> {codigo} con el motivo", r.status_code == codigo and r.json().get("detail"), r.text)
guardados.clear()
db.guardar_ubicacion_cliente = lambda con, id_cliente, lat, lng: guardados.append(id_cliente) or "guardada"
for etiqueta, cuerpo in (("latitud fuera de rango", {"lat": 91, "lng": 0.5}), ("longitud fuera de rango", {"lat": 0.5, "lng": -181}),
                         ("punto 0,0 (GPS sin dato)", {"lat": 0, "lng": 0}), ("sin longitud", {"lat": 1}),
                         ("texto en vez de número", {"lat": "x", "lng": 1})):
    r = client.post("/reparto/clientes/5/ubicacion", json=cuerpo, headers=cab)
    check(f"{etiqueta} -> 422 y no se guarda", r.status_code == 422 and not guardados, r.status_code)
for rol, esperado in (("vendedor", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    check(f"rol {rol}: no puede guardar ubicaciones -> {esperado}",
          client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab).status_code == esperado and not guardados)
db.rol_activo = lambda con, username: "admin"
check("rol admin: sí puede (ve todas las pantallas)",
      client.post("/reparto/clientes/5/ubicacion", json=GPS, headers=cab).status_code == 200 and guardados == [5])
db.rol_activo = lambda con, username: "reparto"

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
