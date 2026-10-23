"""Ubicación de un cliente a partir de un enlace de Google Maps.

Sin Qt: son funciones puras (más la red, que se puede cortar) para poder probarlas
sin abrir ventanas. La ventana que las usa está en `Views/Pedidos/mapa_ubicacion.py`.

- `extraer_coordenadas`: lee latitud/longitud de un enlace largo de Maps.
- `resolver_coordenadas`: igual, pero si es un enlace corto (maps.app.goo.gl) lo abre
  y sigue la redirección para llegar al largo.
- `plan_teselas`: qué teselas de OpenStreetMap hacen falta para dibujar el mapita.
"""
import math
import os
import re
import tempfile
import time
from urllib.parse import unquote
from urllib.request import Request, urlopen

# OpenStreetMap pide identificar la aplicación y no usar el servidor para otra cosa
# que mapas puntuales (acá: unas pocas teselas por cliente, y se guardan en disco).
_USER_AGENT = "ManaInformes/1.0 (uso interno de Mana S.R.L.)"
_TESELA_PX = 256
_VIGENCIA_CACHE_SEG = 30 * 24 * 3600

_NUM = r"(-?\d{1,3}(?:\.\d+)?)"
# De más a menos exacto: `!3d..!4d..` es el pin del lugar, `@..,..` es el centro de
# la vista (suele ser el mismo), y los parámetros `q=`/`ll=`... son enlaces armados a mano.
_PATRONES = (
    re.compile(r"!3d" + _NUM + r"!4d" + _NUM),
    re.compile(r"@" + _NUM + r"," + _NUM),
    re.compile(r"[?&](?:q|ll|query|destination|center|daddr)=" + _NUM + r",\s*" + _NUM),
)


def es_enlace_valido(texto):
    """True si es un enlace http(s): lo mismo que exige la base (CHECK de `ubicacion_maps`)."""
    return bool(re.match(r"^https?://\S+$", (texto or "").strip(), re.IGNORECASE))


def _en_rango(lat, lng):
    return -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0)


def extraer_coordenadas(texto):
    """(lat, lng) leídas del enlace o texto, o None si no hay coordenadas a la vista."""
    texto = unquote(texto or "")
    for patron in _PATRONES:
        m = patron.search(texto)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if _en_rango(lat, lng):
                return lat, lng
    return None


def resolver_coordenadas(enlace, timeout=6):
    """Coordenadas del enlace, abriéndolo si es corto. None si no se pudieron leer
    (sin internet, enlace que no es de un lugar, página de consentimiento, etc.)."""
    directo = extraer_coordenadas(enlace)
    if directo:
        return directo
    try:
        pedido = Request(enlace, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es"})
        with urlopen(pedido, timeout=timeout) as resp:
            final = resp.geturl()
            cuerpo = resp.read(300_000).decode("utf-8", errors="ignore")
    except Exception:
        return None
    return extraer_coordenadas(final) or extraer_coordenadas(cuerpo)


def plan_teselas(lat, lng, zoom, ancho, alto):
    """Teselas necesarias para una vista de `ancho` x `alto` px centrada en (lat, lng).

    Devuelve una lista de (tx, ty, dx, dy): la tesela (zoom, tx, ty) se dibuja con su
    esquina superior izquierda en (dx, dy) dentro de la vista.
    """
    n = 2 ** zoom
    x = (lng + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    izq = x * _TESELA_PX - ancho / 2
    arr = y * _TESELA_PX - alto / 2
    plan = []
    for ty in range(math.floor(arr / _TESELA_PX), math.floor((arr + alto - 1) / _TESELA_PX) + 1):
        for tx in range(math.floor(izq / _TESELA_PX), math.floor((izq + ancho - 1) / _TESELA_PX) + 1):
            if 0 <= ty < n:
                plan.append((tx % n, ty, round(tx * _TESELA_PX - izq), round(ty * _TESELA_PX - arr)))
    return plan


def _carpeta_cache():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    carpeta = os.path.join(base, "ManaInformes", "teselas")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def descargar_tesela(zoom, tx, ty, timeout=5):
    """Bytes PNG de una tesela de OpenStreetMap (con caché en disco). Lanza si no hay red."""
    ruta = os.path.join(_carpeta_cache(), f"{zoom}_{tx}_{ty}.png")
    if os.path.exists(ruta) and time.time() - os.path.getmtime(ruta) < _VIGENCIA_CACHE_SEG:
        with open(ruta, "rb") as f:
            return f.read()
    pedido = Request(f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png", headers={"User-Agent": _USER_AGENT})
    with urlopen(pedido, timeout=timeout) as resp:
        datos = resp.read()
    with open(ruta, "wb") as f:
        f.write(datos)
    return datos
