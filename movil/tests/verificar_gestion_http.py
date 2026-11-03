"""Gestión de pedidos del admin (movil/api/routers/gestion.py): cableado HTTP, permisos por rol, validación de lo
que manda el celular y códigos de respuesta. La lógica de base se prueba en verificar_gestion_db.py.

No toca la base real: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_gestion_http.py
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
    "id_pedido": 7, "estado": "programado", "origen": "movil", "fecha_pedido": dt.date(2026, 10, 30),
    "fecha_entrega": dt.date(2026, 11, 2), "cliente": "DREAM SRL", "cargado_por": "Jose Banco",
    "lineas": [{"id_detalle": 11, "id_producto": "01VA133", "nombre": "VINO MALBEC", "cantidad": 3, "entregada": 1}],
}
ENTREGADO = {**PEDIDO, "id_pedido": 8, "estado": "entregado", "fecha_entrega": dt.date(2026, 10, 30), "cliente": "OTRO SA",
             "cargado_por": None, "origen": "pc", "lineas": []}
db.pedidos_para_gestion = lambda con: {"pendientes": [PEDIDO], "entregados": [ENTREGADO]}
llamadas = []   # lo que llegó a la base, para ver que NADA se aplica cuando se rechaza


def registrar(nombre, resultado):
    def _f(con, *args):
        llamadas.append((nombre, args))
        return resultado
    return _f


client = TestClient(app)
cab = {"Authorization": f"Bearer {auth.crear_token('miguel')}"}
HOY = (dt.date.today() + dt.timedelta(days=3)).isoformat()

RUTAS = (
    ("GET", "/pedidos/gestion", None),
    ("POST", "/pedidos/7/entregar", None),
    ("POST", "/pedidos/7/entrega-parcial", {"lineas": [{"id_detalle": 11, "entregada": 2}]}),
    ("POST", "/pedidos/7/programar", {"fecha": HOY}),
    ("DELETE", "/pedidos/7", None),
)

print("=== quién puede: solo admin y superadmin ===")
db.entregar_pedido_total = registrar("entregar", "entregado")
db.entrega_parcial = registrar("parcial", ("parcial", None))
db.programar_pedido = registrar("programar", "programado")
db.borrar_pedido = registrar("borrar", "borrado")
for rol, esperado in (("admin", 200), ("superadmin", 200), ("vendedor", 403), ("reparto", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    llamadas.clear()
    codigos = [client.request(m, ruta, json=cuerpo, headers=cab).status_code for m, ruta, cuerpo in RUTAS]
    check(f"{etiqueta}: las 5 rutas -> {esperado}", codigos == [esperado] * 5, codigos)
    if esperado != 200:
        check(f"{etiqueta}: nada llegó a la base", llamadas == [], llamadas)
sin_token = [client.request(m, ruta, json=cuerpo).status_code for m, ruta, cuerpo in RUTAS]
check("sin token -> 401 en las 5", sin_token == [401] * 5, sin_token)

db.rol_activo = lambda con, username: "admin"

print("=== GET /pedidos/gestion ===")
r = client.get("/pedidos/gestion", headers=cab)
cuerpo = r.json()
check("devuelve pendientes y entregados", r.status_code == 200 and len(cuerpo["pendientes"]) == 1 and len(cuerpo["entregados"]) == 1, r.text[:200])
p = cuerpo["pendientes"][0]
check("con cliente, estado, fecha de entrega y quién lo cargó",
      (p["id_pedido"], p["cliente"], p["estado"], p["fecha_entrega"], p["cargado_por"]) == (7, "DREAM SRL", "programado", "2026-11-02", "Jose Banco"), p)
check("y las líneas con su id_detalle, cantidad y entregada",
      p["lineas"] == [{"id_detalle": 11, "id_producto": "01VA133", "nombre": "VINO MALBEC", "cantidad": 3, "entregada": 1}], p["lineas"])
check("NO trae dirección ni teléfono del cliente (eso es del reparto)", "direccion" not in p and "telefono" not in p and isinstance(p["cliente"], str))
db.pedidos_para_gestion = lambda con: {"pendientes": [], "entregados": []}
check("sin pedidos -> dos listas vacías (no error)", client.get("/pedidos/gestion", headers=cab).json() == {"pendientes": [], "entregados": []})

print("=== POST /pedidos/{id}/entregar ===")
for resultado, codigo, ya in (("entregado", 200, False), ("ya_estaba", 200, True), ("no_existe", 404, None)):
    db.entregar_pedido_total = registrar("entregar", resultado)
    r = client.post("/pedidos/7/entregar", headers=cab)
    check(f"'{resultado}' -> {codigo}", r.status_code == codigo, r.text)
    if codigo == 200:
        check(f"'{resultado}': ya_estaba={ya} y devuelve el id", r.json() == {"id_pedido": 7, "ya_estaba": ya}, r.json())
conexion.commits = conexion.rollbacks = 0
db.entregar_pedido_total = registrar("entregar", "entregado")
client.post("/pedidos/7/entregar", headers=cab)
check("al entregar se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))

print("=== POST /pedidos/{id}/entrega-parcial ===")
db.entrega_parcial = registrar("parcial", ("parcial", None))
llamadas.clear()
r = client.post("/pedidos/7/entrega-parcial", json={"lineas": [{"id_detalle": 11, "entregada": 2}]}, headers=cab)
check("se aplica y devuelve 'parcial'", r.status_code == 200 and r.json() == {"id_pedido": 7, "estado": "parcial", "completo": False, "sin_cambios": False}, r.text)
check("a la base le llega el TOTAL que debe quedar por línea: {id_detalle: entregada}", llamadas == [("parcial", (7, {11: 2}))], llamadas)
for resultado, esperado in ((("completo", None), {"estado": "entregado", "completo": True, "sin_cambios": False}),
                            (("sin_cambios", None), {"estado": "parcial", "completo": False, "sin_cambios": True}),
                            (("ya_entregado", None), {"estado": "entregado", "completo": True, "sin_cambios": True})):
    db.entrega_parcial = registrar("parcial", resultado)
    r = client.post("/pedidos/7/entrega-parcial", json={"lineas": [{"id_detalle": 11, "entregada": 3}]}, headers=cab)
    check(f"'{resultado[0]}' -> 200 con {esperado}", r.status_code == 200 and {k: r.json()[k] for k in esperado} == esperado, r.text)
for resultado, codigo, texto in ((("no_existe", None), 404, "no existe"), (("linea_ajena", 99), 422, "no es de este pedido"),
                                 (("excede", 11), 422, "más de lo que se pidió"), (("cambio", 11), 409, "Actualizá")):
    db.entrega_parcial = registrar("parcial", resultado)
    r = client.post("/pedidos/7/entrega-parcial", json={"lineas": [{"id_detalle": 11, "entregada": 9}]}, headers=cab)
    check(f"'{resultado[0]}' -> {codigo} y explica el motivo", r.status_code == codigo and texto in r.json()["detail"], r.text)
llamadas.clear()
for nombre, cuerpo in (("sin líneas", {"lineas": []}), ("sin el campo lineas", {}),
                       ("una línea repetida", {"lineas": [{"id_detalle": 11, "entregada": 1}, {"id_detalle": 11, "entregada": 2}]}),
                       ("cantidad negativa", {"lineas": [{"id_detalle": 11, "entregada": -1}]}),
                       ("cantidad absurda", {"lineas": [{"id_detalle": 11, "entregada": 10 ** 9}]}),
                       ("cantidad que no es un número", {"lineas": [{"id_detalle": 11, "entregada": "mucho"}]}),
                       ("id_detalle que no es un número", {"lineas": [{"id_detalle": "x", "entregada": 1}]})):
    r = client.post("/pedidos/7/entrega-parcial", json=cuerpo, headers=cab)
    check(f"rechaza {nombre} -> 422", r.status_code == 422, r.text[:100])
check("y nada de eso llegó a la base", llamadas == [], llamadas)

print("=== POST /pedidos/{id}/programar ===")
db.programar_pedido = registrar("programar", "programado")
llamadas.clear()
r = client.post("/pedidos/7/programar", json={"fecha": HOY}, headers=cab)
check("programa y devuelve la fecha", r.status_code == 200 and r.json() == {"id_pedido": 7, "fecha_entrega": HOY}, r.text)
check("a la base le llega la fecha como fecha", llamadas == [("programar", (7, dt.date.fromisoformat(HOY)))], llamadas)
for resultado, codigo, texto in (("no_existe", 404, "no existe"), ("ya_entregado", 409, "ya entregado"), ("fecha_pasada", 422, "anterior a hoy")):
    db.programar_pedido = registrar("programar", resultado)
    r = client.post("/pedidos/7/programar", json={"fecha": HOY}, headers=cab)
    check(f"'{resultado}' -> {codigo} y explica el motivo", r.status_code == codigo and texto in r.json()["detail"], r.text)
llamadas.clear()
for nombre, cuerpo in (("sin fecha", {}), ("una fecha que no es fecha", {"fecha": "mañana"}), ("una fecha imposible", {"fecha": "2026-02-31"})):
    r = client.post("/pedidos/7/programar", json=cuerpo, headers=cab)
    check(f"rechaza {nombre} -> 422", r.status_code == 422, r.text[:100])
check("y nada de eso llegó a la base", llamadas == [], llamadas)

print("=== DELETE /pedidos/{id} ===")
for resultado, codigo, ya in (("borrado", 200, False), ("ya_no_estaba", 200, True), ("entregado", 409, None)):
    db.borrar_pedido = registrar("borrar", resultado)
    r = client.delete("/pedidos/7", headers=cab)
    check(f"'{resultado}' -> {codigo}", r.status_code == codigo, r.text)
    if codigo == 200:
        check(f"'{resultado}': ya_no_estaba={ya} y devuelve el id (borrar dos veces no da error)", r.json() == {"id_pedido": 7, "ya_no_estaba": ya}, r.json())
    else:
        check("un pedido entregado no se borra desde el celular y explica por qué", "ya entregado" in r.json()["detail"] and "PC" in r.json()["detail"], r.json())
check("un id que no es número -> 422 (no llega a la base)", client.delete("/pedidos/abc", headers=cab).status_code == 422)

print("=== si la base falla, no queda nada a medias ===")


def _falla(*args):
    raise RuntimeError("simulado")


sin_errores = TestClient(app, raise_server_exceptions=False)
for nombre, metodo, ruta, cuerpo, funcion in (
        ("entregar", "POST", "/pedidos/7/entregar", None, "entregar_pedido_total"),
        ("entrega parcial", "POST", "/pedidos/7/entrega-parcial", {"lineas": [{"id_detalle": 11, "entregada": 2}]}, "entrega_parcial"),
        ("programar", "POST", "/pedidos/7/programar", {"fecha": HOY}, "programar_pedido"),
        ("borrar", "DELETE", "/pedidos/7", None, "borrar_pedido")):
    original = getattr(db, funcion)
    setattr(db, funcion, _falla)
    conexion.commits = conexion.rollbacks = 0
    r = sin_errores.request(metodo, ruta, json=cuerpo, headers=cab)
    setattr(db, funcion, original)
    check(f"{nombre}: 500 y rollback, sin commit", r.status_code == 500 and (conexion.commits, conexion.rollbacks) == (0, 1), (r.status_code, conexion.commits, conexion.rollbacks))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
