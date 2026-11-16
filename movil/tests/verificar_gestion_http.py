"""Pedidos por entregar (movil/api/routers/gestion.py): cableado HTTP, permisos por rol (el reparto ve y entrega pero
NO programa, no quita artículos ni borra; el admin hace todo), validación de lo que manda el celular y códigos de
respuesta. La lógica de base se prueba en verificar_gestion_db.py.

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

PEDIDO = {
    "id_pedido": 7, "estado": "programado", "origen": "movil", "fecha_pedido": dt.date(2026, 10, 30),
    "fecha_entrega": dt.date(2026, 11, 2), "cliente": "DREAM SRL", "cargado_por": "Jose Banco",
    "id_cliente": 1, "direccion": "Calle 1, MENDOZA", "ubicacion_maps": "https://maps.app.goo.gl/x",
    "ubicacion_lat": -32.9, "ubicacion_lng": -68.8,
    "lineas": [{"id_detalle": 11, "id_producto": "01VA133", "nombre": "VINO MALBEC", "cantidad": 3, "entregada": 1}],
}
db.pedidos_para_gestion = lambda con: [PEDIDO]
llamadas = []   # lo que llegó a la base, para ver que NADA se aplica cuando se rechaza


def registrar(nombre, resultado):
    def _f(con, *args):
        llamadas.append((nombre, args))
        return resultado
    return _f


client = TestClient(app)
cab = {"Authorization": f"Bearer {auth.crear_token('miguel')}"}
HOY = (dt.date.today() + dt.timedelta(days=3)).isoformat()

# Lo que puede hacer el reparto además del admin (ver, marcar en camino y entregar) y lo que es solo del admin.
RUTAS_REPARTO = (
    ("GET", "/pedidos/gestion", None),
    ("POST", "/pedidos/7/en-camino", None),
    ("POST", "/pedidos/7/entregar", None),
    ("POST", "/pedidos/7/entrega-parcial", {"lineas": [{"id_detalle": 11, "entregada": 2}]}),
)
RUTAS_ADMIN = (
    ("POST", "/pedidos/7/programar", {"fecha": HOY}),
    ("DELETE", "/pedidos/7/lineas/11", None),
    ("DELETE", "/pedidos/7", None),
)

print("=== quién puede: el reparto ve y entrega; programar, quitar artículos y borrar son del admin ===")
db.marcar_en_camino = registrar("en_camino", "en_camino")
db.entregar_pedido_total = registrar("entregar", "entregado")
db.entrega_parcial = registrar("parcial", ("parcial", None))
db.programar_pedido = registrar("programar", "programado")
db.borrar_pedido = registrar("borrar", "borrado")
db.quitar_linea = registrar("quitar", "quitada")
# (rol, lo que dan las rutas del reparto, lo que dan las del admin)
for rol, de_reparto, de_admin in (("admin", 200, 200), ("superadmin", 200, 200), ("reparto", 200, 403),
                                  ("vendedor", 403, 403), (None, 401, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    llamadas.clear()
    codigos = [client.request(m, ruta, json=cuerpo, headers=cab).status_code for m, ruta, cuerpo in RUTAS_REPARTO]
    check(f"{etiqueta}: ver, en camino, entregar y entrega parcial -> {de_reparto}", codigos == [de_reparto] * 4, codigos)
    llamadas.clear()
    codigos = [client.request(m, ruta, json=cuerpo, headers=cab).status_code for m, ruta, cuerpo in RUTAS_ADMIN]
    check(f"{etiqueta}: programar, quitar un artículo y borrar -> {de_admin}", codigos == [de_admin] * 3, codigos)
    if de_admin != 200:
        check(f"{etiqueta}: nada de lo del admin llegó a la base", llamadas == [], llamadas)
sin_token = [client.request(m, ruta, json=cuerpo).status_code for m, ruta, cuerpo in RUTAS_REPARTO + RUTAS_ADMIN]
check("sin token -> 401 en todas", sin_token == [401] * 7, sin_token)
for rol in ("reparto", "vendedor"):
    db.rol_activo = lambda con, username, rol=rol: rol
    llamadas.clear()
    client.delete("/pedidos/7", headers=cab)
    check(f"rol '{rol}': NO puede borrar un pedido y no llega nada a la base", client.delete("/pedidos/7", headers=cab).status_code == 403 and llamadas == [], llamadas)

db.rol_activo = lambda con, username: "reparto"

print("=== GET /pedidos/gestion ===")
r = client.get("/pedidos/gestion", headers=cab)
cuerpo = r.json()
check("devuelve la lista de pedidos por entregar (una lista, sin 'entregados')", r.status_code == 200 and isinstance(cuerpo, list) and len(cuerpo) == 1, r.text[:200])
p = cuerpo[0]
check("con cliente, estado, fecha de entrega y quién lo cargó",
      (p["id_pedido"], p["cliente"], p["estado"], p["fecha_entrega"], p["cargado_por"]) == (7, "DREAM SRL", "programado", "2026-11-02", "Jose Banco"), p)
check("y las líneas con su id_detalle, cantidad y entregada",
      p["lineas"] == [{"id_detalle": 11, "id_producto": "01VA133", "nombre": "VINO MALBEC", "cantidad": 3, "entregada": 1}], p["lineas"])
check("con el id del cliente, su dirección y su ubicación (para llegar o cargarla)",
      (p["id_cliente"], p["direccion"], p["ubicacion_maps"], p["ubicacion_lat"], p["ubicacion_lng"])
      == (1, "Calle 1, MENDOZA", "https://maps.app.goo.gl/x", -32.9, -68.8), p)
check("NO trae el teléfono (nadie llama desde la app)", "telefono" not in p and isinstance(p["cliente"], str))
check("un pedido sin observaciones trae None (no falta la clave)", "observaciones" in p and p["observaciones"] is None, p)
db.pedidos_para_gestion = lambda con: [{**PEDIDO, "observaciones": "Dejar en la portería"}]
check("recibe las observaciones", client.get("/pedidos/gestion", headers=cab).json()[0]["observaciones"] == "Dejar en la portería")
db.pedidos_para_gestion = lambda con: [{**PEDIDO, "ubicacion_maps": None, "ubicacion_lat": None, "ubicacion_lng": None, "direccion": None}]
sin_ubicacion = client.get("/pedidos/gestion", headers=cab).json()[0]
check("un cliente sin ubicación ni dirección trae None (no falla)", (sin_ubicacion["ubicacion_maps"], sin_ubicacion["ubicacion_lat"], sin_ubicacion["direccion"]) == (None, None, None))
db.pedidos_para_gestion = lambda con: []
check("sin pedidos -> lista vacía (no error)", client.get("/pedidos/gestion", headers=cab).json() == [])

print("=== POST /pedidos/{id}/en-camino ===")
for resultado, codigo, ya in (("en_camino", 200, False), ("ya_estaba", 200, True), ("no_existe", 404, None), ("ya_entregado", 409, None)):
    db.marcar_en_camino = registrar("en_camino", resultado)
    llamadas.clear()
    r = client.post("/pedidos/7/en-camino", headers=cab)
    check(f"'{resultado}' -> {codigo}", r.status_code == codigo, r.text)
    if codigo == 200:
        check(f"'{resultado}': ya_estaba={ya} y devuelve el id (reintentar no da error)", r.json() == {"id_pedido": 7, "ya_estaba": ya}, r.json())
        check(f"'{resultado}': a la base le llega solo el pedido", llamadas == [("en_camino", (7,))], llamadas)
    else:
        check(f"'{resultado}': el mensaje explica el motivo", r.json().get("detail"), r.json())
conexion.commits = conexion.rollbacks = 0
db.marcar_en_camino = registrar("en_camino", "en_camino")
client.post("/pedidos/7/en-camino", headers=cab)
check("al marcar en camino se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))
check("un id que no es número -> 422", client.post("/pedidos/abc/en-camino", headers=cab).status_code == 422)

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
check("se aplica y el pedido VUELVE A 'pendiente' (queda lo que falta)",
      r.status_code == 200 and r.json() == {"id_pedido": 7, "estado": "pendiente", "completo": False, "sin_cambios": False}, r.text)
check("a la base le llega el TOTAL que debe quedar por línea: {id_detalle: entregada}",
      llamadas == [("parcial", (7, {11: 2}))], llamadas)
for resultado, esperado in ((("completo", None), {"estado": "entregado", "completo": True, "sin_cambios": False}),
                            (("sin_cambios", None), {"estado": "pendiente", "completo": False, "sin_cambios": True}),
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

db.rol_activo = lambda con, username: "admin"   # lo que sigue es solo del admin

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

print("=== DELETE /pedidos/{id}/lineas/{id_detalle} (quitar un artículo) ===")
for resultado, codigo, esperado in (("quitada", 200, {"ya_no_estaba": False, "completo": False}),
                                    ("completo", 200, {"ya_no_estaba": False, "completo": True}),
                                    ("ya_no_estaba", 200, {"ya_no_estaba": True, "completo": False})):
    db.quitar_linea = registrar("quitar", resultado)
    llamadas.clear()
    r = client.delete("/pedidos/7/lineas/11", headers=cab)
    check(f"'{resultado}' -> {codigo} con {esperado} (quitar dos veces no da error)",
          r.status_code == codigo and r.json() == {"id_pedido": 7, "id_detalle": 11, **esperado}, r.text)
    check(f"'{resultado}': a la base le llega el pedido y la línea", llamadas == [("quitar", (7, 11))], llamadas)
for resultado, codigo, texto in (("no_existe", 404, "no existe"), ("ya_entregado", 409, "ya entregado"),
                                 ("entregada_en_parte", 409, "ya se entregó una parte"), ("es_la_unica", 409, "único artículo")):
    db.quitar_linea = registrar("quitar", resultado)
    r = client.delete("/pedidos/7/lineas/11", headers=cab)
    check(f"'{resultado}' -> {codigo} y explica el motivo", r.status_code == codigo and texto in r.json()["detail"], r.text)
conexion.commits = conexion.rollbacks = 0
db.quitar_linea = registrar("quitar", "quitada")
client.delete("/pedidos/7/lineas/11", headers=cab)
check("al quitar se confirma la transacción", (conexion.commits, conexion.rollbacks) == (1, 0))
llamadas.clear()
check("ids que no son números -> 422 (no llegan a la base)",
      client.delete("/pedidos/abc/lineas/11", headers=cab).status_code == 422
      and client.delete("/pedidos/7/lineas/x", headers=cab).status_code == 422 and llamadas == [])

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
        ("en camino", "POST", "/pedidos/7/en-camino", None, "marcar_en_camino"),
        ("entregar", "POST", "/pedidos/7/entregar", None, "entregar_pedido_total"),
        ("entrega parcial", "POST", "/pedidos/7/entrega-parcial", {"lineas": [{"id_detalle": 11, "entregada": 2}]}, "entrega_parcial"),
        ("programar", "POST", "/pedidos/7/programar", {"fecha": HOY}, "programar_pedido"),
        ("quitar artículo", "DELETE", "/pedidos/7/lineas/11", None, "quitar_linea"),
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
