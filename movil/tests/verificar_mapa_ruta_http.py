"""POST /mapa/ruta (movil/api/routers/mapa.py): quién puede pedirla, qué pedidos entran (solo los EN CAMINO, un cliente
= una parada), de dónde sale (la última posición del reparto), los clientes sin ubicación, la memoria corta y el
límite de paradas. El cálculo en sí se prueba en verificar_ruteo.py: acá `ruteo.armar_ruta` queda reemplazado
(salvo en los casos que no llegan a calcular nada).

No toca la base real ni la red: `db.*` queda reemplazado.

Correr desde la raíz:  python movil/tests/verificar_mapa_ruta_http.py
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from fastapi.testclient import TestClient

from movil.api import auth, config, db, ruteo
from movil.api.app import app
from movil.api.routers import mapa as router_mapa

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


class _Conexion:
    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


db.conexion = lambda: _Conexion()
db.sesion_vigente = lambda con, username, sid: True
client = TestClient(app)
cab = {"Authorization": f"Bearer {auth.crear_token('alguien')}"}


def pedido(id_pedido, estado, id_cliente, cliente, lat, lng, direccion="Calle 1"):
    return {"id_pedido": id_pedido, "estado": estado, "origen": "pc", "fecha_pedido": None, "fecha_entrega": None,
            "cliente": cliente, "id_cliente": id_cliente, "direccion": direccion, "ubicacion_maps": None,
            "ubicacion_lat": lat, "ubicacion_lng": lng, "cargado_por": None, "observaciones": None, "lineas": []}


PEDIDOS = [
    pedido(1, "en camino", 10, "DREAM SRL", Decimal("-31.5410"), Decimal("-68.5290")),       # la base devuelve Decimal
    pedido(2, "pendiente", 11, "NO VA (pendiente)", -31.55, -68.55),
    pedido(3, "en camino", 12, "MARTINEZ", -31.5470, -68.5440, "Calle 3"),
    pedido(4, "en camino", 10, "DREAM SRL", Decimal("-31.5410"), Decimal("-68.5290")),       # otro pedido del mismo cliente
    pedido(5, "programado", 13, "NO VA (programado)", -31.56, -68.56),
    pedido(6, "en camino", 14, "SIN UBICACION SA", None, None, "Calle 9"),
]
db.pedidos_para_gestion = lambda con: PEDIDOS
POSICIONES = [{"usuario": "reparto", "nombre": "Personal de reparto", "lat": -31.5300, "lng": -68.5400, "precision_m": 10, "hace_seg": 5}]
db.posiciones_reparto = lambda con: POSICIONES

llamadas = []
CALCULADO = {"orden": [1, 0], "tramos": [{"metros": 900, "segundos": 120}, {"metros": 1500, "segundos": 200}],
             "trazado": [[-31.53, -68.54], [-31.547, -68.544], [-31.541, -68.529]], "metros": 2400, "segundos": 320,
             "aproximada": False, "trazado_por_calles": True}


def armar_falso(paradas, origen, **kwargs):
    llamadas.append({"paradas": paradas, "origen": origen, **kwargs})
    return dict(CALCULADO)


armar_real = ruteo.armar_ruta
ruteo.armar_ruta = armar_falso


def pedir(cabecera=cab):
    return client.post("/mapa/ruta", headers=cabecera)


print("=== quién puede pedir la ruta ===")
for rol, esperado in (("reparto", 200), ("admin", 200), ("superadmin", 200), ("vendedor", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    router_mapa._cache.clear()
    etiqueta = "dado de baja" if rol is None else f"rol '{rol}'"
    check(f"{etiqueta} -> {esperado}", pedir().status_code == esperado)
check("sin token -> 401", client.post("/mapa/ruta").status_code == 401)
check("la ruta se pide con POST: un GET no calcula nada (404/405)", client.get("/mapa/ruta", headers=cab).status_code in (404, 405))
db.rol_activo = lambda con, username: "reparto"

print("=== qué paradas entran ===")
router_mapa._cache.clear()
llamadas.clear()
r = pedir()
check("200", r.status_code == 200, r.text)
d = r.json()
check("al cálculo le llegan solo los clientes con pedido EN CAMINO y ubicación: 2 (no los pendientes, programados ni el que no tiene ubicación)",
      len(llamadas) == 1 and llamadas[0]["paradas"] == [(-31.541, -68.529), (-31.547, -68.544)], llamadas)
check("las coordenadas llegan como números comunes (la base devuelve Decimal)", all(type(x) is float for p in llamadas[0]["paradas"] for x in p))
check("un cliente con dos pedidos en camino es UNA parada, con sus dos pedidos",
      [(p["id_cliente"], p["pedidos"]) for p in d["paradas"]] == [(12, [3]), (10, [1, 4])], d["paradas"])
check("las paradas salen en el orden que calculó el motor (1 y después 0), numeradas desde 1",
      [(p["orden"], p["cliente"]) for p in d["paradas"]] == [(1, "MARTINEZ"), (2, "DREAM SRL")])
check("con su dirección, ubicación y el tramo desde la anterior",
      d["paradas"][0] == {"orden": 1, "id_cliente": 12, "cliente": "MARTINEZ", "direccion": "Calle 3", "lat": -31.547, "lng": -68.544,
                          "pedidos": [3], "metros": 900, "segundos": 120}, d["paradas"][0])
check("el trazado, el total y las banderas pasan tal cual", (d["trazado"], d["metros"], d["segundos"], d["aproximada"], d["trazado_por_calles"]) ==
      (CALCULADO["trazado"], 2400, 320, False, True))
check("el cliente en camino sin ubicación no entra en la ruta, pero se avisa",
      d["sin_ubicacion"] == [{"id_cliente": 14, "cliente": "SIN UBICACION SA", "pedidos": [6]}], d["sin_ubicacion"])
check("el servidor de rutas y la pausa salen de la configuración", llamadas[0]["url_base"] == config.OSRM_URL and llamadas[0]["pausa_s"] == config.OSRM_PAUSA_S)

print("=== de dónde sale ===")
check("sale de la posición del reparto, con hace cuánto llegó", d["origen"] == {"lat": -31.53, "lng": -68.54, "hace_seg": 5}, d["origen"])
check("y esa posición se la pasa al motor", llamadas[0]["origen"] == (-31.53, -68.54))
POSICIONES.append({"usuario": "otro", "nombre": "Otro", "lat": -31.60, "lng": -68.60, "precision_m": 10, "hace_seg": 2})
router_mapa._cache.clear()
llamadas.clear()
d = pedir().json()
check("si hubiera dos posiciones, vale la más reciente", d["origen"]["hace_seg"] == 2 and llamadas[0]["origen"] == (-31.60, -68.60), d["origen"])
POSICIONES.clear()
router_mapa._cache.clear()
llamadas.clear()
d = pedir().json()
check("sin posición reciente del reparto: origen null y el motor arma la ruta sin salida fija", d["origen"] is None and llamadas[0]["origen"] is None, d["origen"])
POSICIONES.append({"usuario": "reparto", "nombre": "Personal de reparto", "lat": -31.5300, "lng": -68.5400, "precision_m": 10, "hace_seg": 5})

print("=== memoria corta: no se consulta dos veces lo mismo ===")
router_mapa._cache.clear()
llamadas.clear()
pedir()
pedir()
check("dos pedidos seguidos de lo mismo -> el motor calcula una sola vez", len(llamadas) == 1, len(llamadas))
d = pedir().json()
check("pero la respuesta sigue leyendo la posición y la antigüedad de la base (no queda congelada)", d["origen"]["hace_seg"] == 5)
POSICIONES[0] = dict(POSICIONES[0], lat=-31.5301, lng=-68.5401)   # el reparto se movió unos 15 m
pedir()
check("si el reparto se movió unos metros, sigue siendo lo mismo (la salida se redondea a ~100 m)", len(llamadas) == 1, len(llamadas))
POSICIONES[0] = dict(POSICIONES[0], lat=-31.5400, lng=-68.5400)   # se movió 1 km
pedir()
check("si se movió de verdad (1 km), se recalcula", len(llamadas) == 2, len(llamadas))
PEDIDOS.append(pedido(7, "en camino", 15, "NUEVO SA", -31.5200, -68.5100))
pedir()
check("si entra otro cliente en camino, se recalcula", len(llamadas) == 3, len(llamadas))
PEDIDOS.pop()
n = len(llamadas)
CALCULADO["aproximada"], CALCULADO["trazado_por_calles"] = True, False
router_mapa._cache.clear()
pedir()
pedir()
check("una ruta de emergencia (en línea recta) NO se guarda: al pedirla de nuevo se reintenta con las calles", len(llamadas) == n + 2, len(llamadas) - n)
CALCULADO["aproximada"], CALCULADO["trazado_por_calles"] = False, True

print("=== sin pedidos en camino / demasiados ===")
ruteo.armar_ruta = armar_real   # estos casos los resuelve el motor de verdad (no llegan a consultar a nadie)
backup = list(PEDIDOS)
PEDIDOS[:] = [pedido(2, "pendiente", 11, "X", -31.55, -68.55)]
router_mapa._cache.clear()
r = pedir()
check("sin pedidos en camino -> 200 con la ruta vacía (no es un error)", r.status_code == 200 and r.json()["paradas"] == [] and r.json()["trazado"] == [] and r.json()["metros"] == 0, r.text)
PEDIDOS[:] = [pedido(100 + i, "en camino", 100 + i, f"CLIENTE {i}", -31.5 - i / 1000, -68.5) for i in range(13)]
router_mapa._cache.clear()
r = pedir()
check("13 clientes en camino -> 422 con un mensaje que dice cuántos y cuál es el máximo",
      r.status_code == 422 and "13" in r.json()["detail"] and "12" in r.json()["detail"], r.text)
PEDIDOS[:] = [pedido(100 + i, "en camino", 100 + i, f"CLIENTE {i}", None, None) for i in range(13)]
router_mapa._cache.clear()
r = pedir()
check("pero 13 en camino SIN ubicación no cuentan (no entran en la ruta): 200 y los 13 en 'sin_ubicacion'",
      r.status_code == 200 and len(r.json()["sin_ubicacion"]) == 13 and r.json()["paradas"] == [], r.text[:200])
PEDIDOS[:] = backup

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
