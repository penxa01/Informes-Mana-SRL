"""Armar la mejor ruta entre los clientes con pedidos en camino.

Es el problema del viajante: dadas unas paradas, en qué orden visitarlas para tardar lo menos posible. Con pocas
paradas (el reparto lleva de 3 a 8) se resuelve de forma EXACTA —no es una aproximación—, probando todas las
combinaciones de forma inteligente (Held-Karp).

Qué tarda ir de una parada a otra se lo pregunta a OSRM (un motor de rutas con los mapas de OpenStreetMap):
  - `/table`  → la matriz de tiempos por calle. NO es simétrica: ir de A a B puede tardar distinto que de B a A
                porque hay calles de un solo sentido. Por eso el orden de la ruta respeta los sentidos.
  - `/route`  → el trazado real por las calles, para dibujarlo en el mapa.
Solo viajan coordenadas (nada de nombres ni datos del cliente). La dirección del servidor sale de
`MOVIL_OSRM_URL`: por defecto el servidor público de demostración; se puede apuntar a uno propio sin tocar código.

Si OSRM no responde (sin internet, caído, lento), se arma igual con distancias en línea recta y se avisa que es
aproximada: mejor una ruta razonable que ninguna.

Este módulo no toca la base ni la configuración: recibe todo por parámetro (se prueba con un OSRM falso)."""
import math
import threading
import time

import httpx

URL_PUBLICA = "https://router.project-osrm.org"
MAX_PARADAS = 12            # Held-Karp crece como 2^n: con 12 sigue siendo instantáneo; más no hace falta
TIMEOUT_S = 8.0
# El servidor público de OSRM pide como mucho una consulta por segundo.
PAUSA_ENTRE_CONSULTAS_S = 1.1

# Sin calles (fallback): el recorrido real es más largo que la recta y en ciudad se anda despacio.
FACTOR_RODEO = 1.3
VELOCIDAD_CIUDAD_MS = 25 / 3.6


class ErrorRuteo(Exception):
    """El servidor de rutas no pudo responder (o respondió algo que no sirve)."""


class DemasiadasParadas(ValueError):
    def __init__(self, cantidad):
        super().__init__(f"{cantidad} paradas: la ruta admite hasta {MAX_PARADAS}")
        self.cantidad = cantidad


# ── el orden ─────────────────────────────────────────────────────────────────
def mejor_orden(costo, desde_origen=None):
    """El orden de las paradas con el menor costo total, como lista de índices.

    `costo[i][j]` es lo que cuesta ir de la parada i a la j (puede ser distinto de ir de la j a la i: sentidos de
    calle). `desde_origen[j]` es lo que cuesta llegar a la parada j desde la salida; si es None no hay salida
    fija y la ruta puede arrancar en la parada que más convenga. Es un recorrido abierto: no vuelve al inicio."""
    n = len(costo)
    if n == 0:
        return []
    if n > MAX_PARADAS:
        raise DemasiadasParadas(n)
    inicio = desde_origen if desde_origen is not None else [0.0] * n
    inf = float("inf")
    llena = (1 << n) - 1
    # dp[conjunto][j]: el menor costo de recorrer ese conjunto de paradas terminando en la j.
    dp = [[inf] * n for _ in range(1 << n)]
    padre = [[-1] * n for _ in range(1 << n)]
    for j in range(n):
        dp[1 << j][j] = inicio[j]
    for conjunto in range(1, llena + 1):
        for j in range(n):
            actual = dp[conjunto][j]
            if actual == inf:
                continue
            for k in range(n):
                if conjunto & (1 << k):
                    continue
                nuevo = actual + costo[j][k]
                con_k = conjunto | (1 << k)
                if nuevo < dp[con_k][k]:
                    dp[con_k][k] = nuevo
                    padre[con_k][k] = j
    ultimo = min(range(n), key=lambda j: dp[llena][j])
    orden = []
    conjunto, j = llena, ultimo
    while j != -1:
        orden.append(j)
        anterior = padre[conjunto][j]
        conjunto ^= 1 << j
        j = anterior
    orden.reverse()
    return orden


# ── sin calles: línea recta ──────────────────────────────────────────────────
def distancia_recta_m(a, b):
    """Distancia en metros entre dos puntos (lat, lng) sobre la superficie de la Tierra (haversine)."""
    radio = 6371000.0
    f1, f2 = math.radians(a[0]), math.radians(b[0])
    df = f2 - f1
    dl = math.radians(b[1] - a[1])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(h))


def matriz_recta(puntos):
    """(duraciones en s, distancias en m) estimadas en línea recta, con un factor por las vueltas de las calles."""
    distancias = [[distancia_recta_m(a, b) * FACTOR_RODEO for b in puntos] for a in puntos]
    duraciones = [[d / VELOCIDAD_CIUDAD_MS for d in fila] for fila in distancias]
    return duraciones, distancias


# ── OSRM ─────────────────────────────────────────────────────────────────────
_turno = threading.Lock()
_ultima_consulta = [0.0]


def _esperar_turno(pausa_s):
    """Respeta la pausa entre consultas al servidor (aunque dos personas pidan una ruta a la vez)."""
    if pausa_s <= 0:
        return
    with _turno:
        falta = _ultima_consulta[0] + pausa_s - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        _ultima_consulta[0] = time.monotonic()


def _coordenadas(puntos):
    # OSRM pide longitud,latitud (al revés que lat,lng)
    return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in puntos)


def _pedir(url, cliente, pausa_s):
    _esperar_turno(pausa_s)
    try:
        respuesta = cliente.get(url, timeout=TIMEOUT_S)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ErrorRuteo(f"no respondió el servidor de rutas: {error}") from error
    if not isinstance(datos, dict) or datos.get("code") != "Ok":
        codigo = datos.get("code") if isinstance(datos, dict) else "?"
        raise ErrorRuteo(f"el servidor de rutas no pudo armar el recorrido ({codigo})")
    return datos


def pedir_matriz(url_base, puntos, cliente, pausa_s=0.0):
    """(duraciones en s, distancias en m) por calle entre todos los puntos. Asimétrica: respeta los sentidos."""
    url = f"{url_base}/table/v1/driving/{_coordenadas(puntos)}?annotations=duration,distance"
    datos = _pedir(url, cliente, pausa_s)
    n = len(puntos)
    try:
        duraciones, distancias = datos["durations"], datos["distances"]
        for matriz in (duraciones, distancias):
            if len(matriz) != n or any(len(fila) != n for fila in matriz):
                raise ValueError("forma inesperada")
            if any(valor is None for fila in matriz for valor in fila):
                raise ValueError("hay puntos a los que no se puede llegar por calle")
        return ([[float(v) for v in fila] for fila in duraciones], [[float(v) for v in fila] for fila in distancias])
    except (KeyError, TypeError, ValueError) as error:
        raise ErrorRuteo(f"respuesta de la matriz inválida: {error}") from error


def pedir_trazado(url_base, puntos, cliente, pausa_s=0.0):
    """El recorrido real por las calles pasando por los puntos en ese orden: {"coordenadas": [[lat, lng], ...],
    "metros", "segundos", "tramos": [(metros, segundos), ...]} (un tramo entre cada par de puntos)."""
    url = f"{url_base}/route/v1/driving/{_coordenadas(puntos)}?overview=full&geometries=geojson&steps=false"
    datos = _pedir(url, cliente, pausa_s)
    try:
        ruta = datos["routes"][0]
        coordenadas = [[round(lat, 5), round(lng, 5)] for lng, lat in ruta["geometry"]["coordinates"]]
        tramos = [(float(t["distance"]), float(t["duration"])) for t in ruta["legs"]]
        if len(tramos) != len(puntos) - 1 or len(coordenadas) < 2:
            raise ValueError("forma inesperada")
        return {"coordenadas": coordenadas, "metros": float(ruta["distance"]), "segundos": float(ruta["duration"]),
                "tramos": tramos}
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ErrorRuteo(f"respuesta del recorrido inválida: {error}") from error


# ── la ruta completa ─────────────────────────────────────────────────────────
def armar_ruta(paradas, origen=None, url_base=URL_PUBLICA, pausa_s=PAUSA_ENTRE_CONSULTAS_S, cliente_http=None):
    """La mejor ruta para visitar las `paradas` [(lat, lng), ...], saliendo de `origen` (lat, lng) o None.

    Devuelve:
      orden               índices de `paradas` en el orden en que conviene visitarlas
      tramos              uno por parada, en ese orden: {"metros", "segundos"} desde la parada anterior (o desde la
                          salida; la primera parada, si no hay salida, es 0)
      trazado             [[lat, lng], ...] para dibujar el recorrido
      metros, segundos    el total
      aproximada          True si no se pudo consultar las calles y el orden se calculó en línea recta
      trazado_por_calles  False si el trazado es una poligonal recta entre las paradas (aunque el orden sea por calles)
    """
    n = len(paradas)
    if n == 0:
        return {"orden": [], "tramos": [], "trazado": [], "metros": 0, "segundos": 0, "aproximada": False,
                "trazado_por_calles": True}
    if n > MAX_PARADAS:
        raise DemasiadasParadas(n)
    propio = cliente_http is None
    cliente = httpx.Client() if propio else cliente_http
    try:
        return _armar(paradas, origen, url_base.rstrip("/"), pausa_s, cliente)
    finally:
        if propio:
            cliente.close()


def _armar(paradas, origen, url_base, pausa_s, cliente):
    n = len(paradas)
    desfase = 1 if origen else 0   # en `puntos` la salida (si hay) es el índice 0
    puntos = ([tuple(origen)] if origen else []) + [tuple(p) for p in paradas]
    aproximada = False
    if len(puntos) >= 2:
        try:
            duraciones, distancias = pedir_matriz(url_base, puntos, cliente, pausa_s)
        except ErrorRuteo:
            duraciones, distancias = matriz_recta(puntos)
            aproximada = True
    else:
        duraciones = distancias = [[0.0]]

    costo = [[duraciones[desfase + i][desfase + j] for j in range(n)] for i in range(n)]
    desde_origen = [duraciones[0][desfase + j] for j in range(n)] if origen else None
    orden = mejor_orden(costo, desde_origen)

    en_ruta = ([tuple(origen)] if origen else []) + [tuple(paradas[i]) for i in orden]
    indices = ([0] if origen else []) + [desfase + i for i in orden]   # lugar de cada punto de la ruta en la matriz
    de_la_matriz = [(distancias[a][b], duraciones[a][b]) for a, b in zip(indices, indices[1:])]

    trazado, tramos_ruta, por_calles = [list(p) for p in en_ruta], de_la_matriz, False
    if len(en_ruta) >= 2 and not aproximada:
        try:
            real = pedir_trazado(url_base, en_ruta, cliente, pausa_s)
            trazado, tramos_ruta, por_calles = real["coordenadas"], real["tramos"], True
        except ErrorRuteo:
            pass   # el orden ya salió por calles; solo el dibujo queda en recta
    if len(en_ruta) < 2:
        por_calles = not aproximada

    # un tramo por parada: sin salida fija la primera parada no tiene tramo de llegada
    tramos_por_parada = tramos_ruta if origen else [(0.0, 0.0)] + list(tramos_ruta)
    tramos = [{"metros": int(round(m)), "segundos": int(round(s))} for m, s in tramos_por_parada]
    return {
        "orden": orden,
        "tramos": tramos,
        "trazado": trazado,
        "metros": sum(t["metros"] for t in tramos),
        "segundos": sum(t["segundos"] for t in tramos),
        "aproximada": aproximada,
        "trazado_por_calles": por_calles,
    }
