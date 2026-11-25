"""El motor de la ruta de reparto (movil/api/ruteo.py): el orden exacto de las paradas (contra fuerza bruta), que
respete los sentidos de las calles (costos distintos de ida y de vuelta), el trato con OSRM (con un OSRM falso: no hay
red) y la ruta de emergencia en línea recta cuando OSRM no responde.

No toca la base ni la red.

Correr desde la raíz:  python movil/tests/verificar_ruteo.py
"""
import itertools
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx

from movil.api import ruteo

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def costo_total(orden, costo, desde_origen):
    inicio = desde_origen[orden[0]] if desde_origen is not None else 0.0
    return inicio + sum(costo[a][b] for a, b in zip(orden, orden[1:]))


print("=== el orden es el mejor posible (contra probar todas las combinaciones) ===")
azar = random.Random(7)
malos = []
for n in range(1, 8):
    for _ in range(25):
        costo = [[0 if i == j else azar.uniform(1, 100) for j in range(n)] for i in range(n)]   # asimétrica
        for salida in (None, [azar.uniform(1, 100) for _ in range(n)]):
            orden = ruteo.mejor_orden(costo, salida)
            mejor = min(costo_total(list(p), costo, salida) for p in itertools.permutations(range(n)))
            if sorted(orden) != list(range(n)) or abs(costo_total(orden, costo, salida) - mejor) > 1e-9:
                malos.append((n, salida is not None))
check("de 1 a 7 paradas, con y sin salida fija, con costos de ida y vuelta distintos: siempre el óptimo", malos == [], malos[:3])
check("sin paradas -> lista vacía", ruteo.mejor_orden([]) == [])
check("con una parada -> esa", ruteo.mejor_orden([[0]], [5]) == [0])

print("=== los sentidos de las calles cuentan (ir de A a B no es lo mismo que de B a A) ===")
costo = [[0, 5], [100, 0]]   # de 0 a 1 son 5; de 1 a 0 son 100 (contramano: hay que dar toda la vuelta)
check("saliendo de un punto equidistante, conviene ir en el sentido barato", ruteo.mejor_orden(costo, [10, 10]) == [0, 1])
check("y al revés si la calle va para el otro lado", ruteo.mejor_orden([[0, 100], [5, 0]], [10, 10]) == [1, 0])
check("la salida pesa: si queda más cerca de la otra parada, arranca por esa",
      ruteo.mejor_orden([[0, 5], [6, 0]], [50, 1]) == [1, 0])

print("=== el límite de paradas ===")
try:
    ruteo.mejor_orden([[0] * 13 for _ in range(13)])
    check("13 paradas -> se rechaza", False)
except ruteo.DemasiadasParadas as e:
    check("13 paradas -> DemasiadasParadas (el mensaje dice cuántas)", e.cantidad == 13 and "13" in str(e), str(e))
t0 = time.monotonic()
grande = [[0 if i == j else azar.uniform(1, 100) for j in range(12)] for i in range(12)]
ruteo.mejor_orden(grande, [azar.uniform(1, 100) for _ in range(12)])
check("12 paradas se resuelven rápido (menos de 5 s)", time.monotonic() - t0 < 5, f"{time.monotonic() - t0:.2f} s")

print("=== en línea recta (cuando no hay calles) ===")
check("un grado de latitud son ~111,2 km", abs(ruteo.distancia_recta_m((-31.0, -68.0), (-32.0, -68.0)) - 111195) < 300)
check("un punto a sí mismo: 0", ruteo.distancia_recta_m((-31.5, -68.5), (-31.5, -68.5)) == 0)
dur, dist = ruteo.matriz_recta([(-31.5, -68.5), (-31.5, -68.49)])
check("la matriz es simétrica, con 0 en la diagonal y la distancia más larga que la recta (las calles dan vueltas)",
      dur[0][1] == dur[1][0] and dur[0][0] == 0 and dist[0][1] > ruteo.distancia_recta_m((-31.5, -68.5), (-31.5, -68.49)))


# ── un OSRM de mentira ───────────────────────────────────────────────────────
def osrm_falso(duraciones, distancias=None, tramos=None, geometria=None, codigo="Ok", falla=None, ruta_falla=False):
    """Responde /table con las matrices dadas y /route con una geometría y tramos. Anota cada pedido."""
    pedidos = []

    def manejar(request):
        pedidos.append(request)
        if falla:
            raise falla
        camino = request.url.path
        if camino.startswith("/table/"):
            return httpx.Response(200, json={"code": codigo, "durations": duraciones,
                                             "distances": distancias if distancias is not None else duraciones})
        if ruta_falla:
            return httpx.Response(500, text="boom")
        n = len(camino.split("/")[-1].split(";"))
        return httpx.Response(200, json={"code": codigo, "routes": [{
            "distance": 1234.0, "duration": 321.0,
            "geometry": {"type": "LineString", "coordinates": geometria or [[-68.5, -31.5], [-68.4, -31.4]]},
            "legs": tramos if tramos is not None else [{"distance": 100.0 * (i + 1), "duration": 10.0 * (i + 1)} for i in range(n - 1)]}]})

    return httpx.Client(transport=httpx.MockTransport(manejar)), pedidos


O, A, B, C = (-31.50, -68.50), (-31.50, -68.49), (-31.50, -68.48), (-31.50, -68.47)   # A, B y C hacia el este, en recta
print("=== el orden sale de las CALLES, no de la línea recta ===")
# En recta lo natural es A, B, C. Pero por las calles (un solo sentido) llegar a C es lo barato y de ahí se va volviendo.
INF = 9999
durs = [[0, 1000, 500, 100],      # desde la salida
        [INF, 0, INF, INF],       # desde A
        [INF, 50, 0, INF],        # desde B: A queda al lado
        [INF, INF, 50, 0]]        # desde C: B queda al lado
http, pedidos = osrm_falso(durs)
r = ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("el orden respeta los sentidos: C, B, A (no A, B, C)", r["orden"] == [2, 1, 0], r["orden"])
check("sale por calles (no aproximada) y el trazado también", r["aproximada"] is False and r["trazado_por_calles"] is True)
check("se hicieron dos consultas: la matriz y el recorrido", [p.url.path.split("/")[1] for p in pedidos] == ["table", "route"])
tabla = pedidos[0].url
check("las coordenadas van como longitud,latitud (al revés de lat,lng)", tabla.path.split("/")[-1].startswith("-68.500000,-31.500000;-68.490000,-31.500000"), tabla.path)
check("la matriz pide tiempo y distancia", tabla.params["annotations"] == "duration,distance")
ruta = pedidos[1].url
check("el recorrido se pide con las paradas YA en el orden elegido (salida, C, B, A)",
      ruta.path.split("/")[-1] == "-68.500000,-31.500000;-68.470000,-31.500000;-68.480000,-31.500000;-68.490000,-31.500000", ruta.path)
check("con el trazado completo, en geojson", ruta.params["overview"] == "full" and ruta.params["geometries"] == "geojson")
check("el trazado vuelve como [lat, lng] (OSRM lo manda al revés)", r["trazado"] == [[-31.5, -68.5], [-31.4, -68.4]], r["trazado"])
check("un tramo por parada, con metros y segundos de cada uno (los del recorrido)",
      r["tramos"] == [{"metros": 100, "segundos": 10}, {"metros": 200, "segundos": 20}, {"metros": 300, "segundos": 30}], r["tramos"])
check("el total es la suma de los tramos", (r["metros"], r["segundos"]) == (600, 60), (r["metros"], r["segundos"]))
check("el trazado se redondea (no manda 15 decimales por el celular)",
      ruteo.pedir_trazado("http://osrm.test", [O, A], osrm_falso(durs, geometria=[[-68.123456789, -31.987654321], [-68.2, -31.3]])[0])["coordenadas"][0] == [-31.98765, -68.12346])

print("=== sin posición del reparto: arranca donde más convenga ===")
costos = [[0, 10, 10], [10, 0, 1], [10, 1, 0]]   # 3 paradas: la 1 y la 2 están pegadas; la 0 está lejos de todas
http, pedidos = osrm_falso(costos)
r = ruteo.armar_ruta([A, B, C], None, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("empieza por un extremo (0, y después las pegadas) o por las pegadas y termina en 0: nunca la 0 en el medio",
      r["orden"] in ([0, 1, 2], [0, 2, 1], [1, 2, 0], [2, 1, 0]), r["orden"])
check("la matriz se pidió solo con las paradas (3 puntos, sin salida)", len(pedidos[0].url.path.split("/")[-1].split(";")) == 3)
check("sin salida, la primera parada no tiene tramo de llegada (0) y las otras sí", r["tramos"][0] == {"metros": 0, "segundos": 0} and r["tramos"][1]["metros"] > 0, r["tramos"])
check("y hay un tramo por parada", len(r["tramos"]) == 3)

print("=== casos chicos ===")
http, pedidos = osrm_falso([[0]])
r = ruteo.armar_ruta([A], None, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("una parada y sin salida: no hay nada que calcular, no se consulta a nadie", r["orden"] == [0] and pedidos == [] and r["metros"] == 0 and r["aproximada"] is False, r)
http, pedidos = osrm_falso([[0, 80], [80, 0]])
r = ruteo.armar_ruta([A], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("una parada y la salida: se arma el tramo hasta ella", r["orden"] == [0] and len(r["tramos"]) == 1 and r["tramos"][0]["metros"] == 100, r)
http, pedidos = osrm_falso([])
r = ruteo.armar_ruta([], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("sin paradas: ruta vacía, sin consultar", r["orden"] == [] and r["trazado"] == [] and pedidos == [])
try:
    ruteo.armar_ruta([A] * 13, O, url_base="http://osrm.test", pausa_s=0, cliente_http=osrm_falso([])[0])
    check("más de 12 paradas -> se rechaza", False)
except ruteo.DemasiadasParadas:
    check("más de 12 paradas -> DemasiadasParadas", True)

print("=== si OSRM falla, la ruta sale igual (aproximada, en línea recta) ===")
for nombre, kwargs in (("no hay red", {"falla": httpx.ConnectError("sin internet")}),
                       ("tarda demasiado", {"falla": httpx.ReadTimeout("lento")}),
                       ("responde un código que no es Ok", {"duraciones": durs, "codigo": "NoRoute"}),
                       ("no hay camino a un punto (null en la matriz)", {"duraciones": [[0, None, 500, 100]] + durs[1:]})):
    http, pedidos = osrm_falso(kwargs.pop("duraciones", durs), **kwargs)
    r = ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
    check(f"{nombre}: devuelve una ruta marcada como aproximada", r["aproximada"] is True and r["trazado_por_calles"] is False and sorted(r["orden"]) == [0, 1, 2], r)
    check(f"{nombre}: con la poligonal recta salida-paradas (4 puntos) y una sola consulta fallida", len(r["trazado"]) == 4 and len(pedidos) == 1)
http, _ = osrm_falso(durs, falla=httpx.ConnectError("x"))
r = ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("en línea recta el orden natural es A, B, C", r["orden"] == [0, 1, 2], r["orden"])
check("y hay distancias y tiempos estimados (no ceros)", r["metros"] > 2000 and r["segundos"] > 0, (r["metros"], r["segundos"]))

http, pedidos = osrm_falso(durs, ruta_falla=True)
r = ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test", pausa_s=0, cliente_http=http)
check("si solo falla el dibujo: el ORDEN sigue siendo por calles (C, B, A) y no es 'aproximada'", r["orden"] == [2, 1, 0] and r["aproximada"] is False, r)
check("pero el trazado es la poligonal recta y se avisa (trazado_por_calles False)", r["trazado_por_calles"] is False and len(r["trazado"]) == 4)
check("los tiempos de cada tramo salen de la matriz por calles", [t["segundos"] for t in r["tramos"]] == [100, 50, 50], r["tramos"])

print("=== trato con el servidor ===")
check("una dirección con barra al final no rompe la URL", ruteo.armar_ruta([A], O, url_base="http://osrm.test/", pausa_s=0, cliente_http=osrm_falso([[0, 80], [80, 0]])[0])["orden"] == [0])
http, pedidos = osrm_falso(durs)
ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test/", pausa_s=0, cliente_http=http)
check("...y no queda 'test//table'", "//table" not in str(pedidos[0].url))
t0 = time.monotonic()
ruteo._ultima_consulta[0] = 0.0
http, _ = osrm_falso(durs)
ruteo.armar_ruta([A, B, C], O, url_base="http://osrm.test", pausa_s=0.3, cliente_http=http)
check("entre la matriz y el recorrido respeta la pausa (el servidor público pide una consulta por segundo)", time.monotonic() - t0 >= 0.28, f"{time.monotonic() - t0:.2f} s")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
