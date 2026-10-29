"""Reglas de las suscripciones a avisos (push): lógica pura, sin FastAPI ni base.

Cada celular que acepta avisos le entrega a la API una "suscripción": un `endpoint` (una URL del
servicio de push de Google, Apple, Mozilla o Microsoft) y dos claves para cifrar el contenido. El
servidor después le hace un POST a esa URL. Como la URL la manda el celular, se acepta solo si es de
uno de esos servicios: si no, cualquier usuario podría hacer que el servidor le pegue a una dirección
de la red interna (la base, el panel de Tailscale, etc.).
"""
import base64
import binascii
import re
from urllib.parse import urlsplit

# Dominios de los servicios de push de los navegadores (el sufijo cubre sus subdominios).
_SERVICIOS = (
    "fcm.googleapis.com",                 # Chrome, Edge y Samsung Internet en Android
    "push.services.mozilla.com",          # Firefox
    "push.apple.com",                     # Safari / iPhone (web.push.apple.com)
    "notify.windows.com",                 # Edge en Windows (wns2-*.notify.windows.com)
)

MAX_ENDPOINT = 1024
MAX_SUSCRIPCIONES_POR_USUARIO = 10   # un celular, una tablet, la PC... y algo de margen

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def endpoint_permitido(endpoint):
    """True si `endpoint` es una URL https de un servicio de push conocido (sin usuario, puerto raro ni IP)."""
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > MAX_ENDPOINT:
        return False
    try:
        partes = urlsplit(endpoint)
        puerto = partes.port
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or partes.username or partes.password or puerto not in (None, 443):
        return False
    return any(host == s or host.endswith("." + s) for s in _SERVICIOS)


def _decodificar(valor):
    if not isinstance(valor, str) or not _BASE64URL.match(valor):
        return None
    try:
        return base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))
    except (binascii.Error, ValueError):
        return None


def clave_p256dh_valida(valor):
    """Clave pública del celular: un punto de la curva P-256 sin comprimir (65 bytes, empieza con 0x04)."""
    crudo = _decodificar(valor)
    return crudo is not None and len(crudo) == 65 and crudo[0] == 4


def secreto_auth_valido(valor):
    """Secreto de autenticación del celular: 16 bytes."""
    crudo = _decodificar(valor)
    return crudo is not None and len(crudo) == 16
