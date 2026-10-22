"""Login de la API móvil: verificación de clave contra `usuario.password_hash`
(bcrypt), token de sesión firmado y límite de intentos por usuario.

El límite de intentos vive en memoria de proceso (no se guarda en la base):
se resetea si se reinicia el servicio. Es intencional, son 7 usuarios.

El token es JWT HS256 armado a mano con `hmac`/`hashlib` de la librería
estándar (en vez de `pyjwt`): en esta máquina ningún paquete con extensión
en Rust carga (`cryptography`, que `pyjwt` importa siempre aunque no haga
falta para HS256, revienta con "DLL load failed"). HS256 es solo un HMAC-SHA256
sobre header+payload en base64url; no hay nada más que replicar.
"""
import base64
import datetime as dt
import hashlib
import hmac
import json

import bcrypt

from . import config

_HEADER_B64 = base64.urlsafe_b64encode(
    json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
).rstrip(b"=").decode("ascii")

MAX_INTENTOS = 5
BLOQUEO_MINUTOS = 15

_intentos = {}  # username -> {"fallos": int, "bloqueado_hasta": datetime | None}


def _estado(username):
    return _intentos.setdefault(username, {"fallos": 0, "bloqueado_hasta": None})


def bloqueado(username, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    hasta = _estado(username)["bloqueado_hasta"]
    return hasta is not None and ahora < hasta


def _registrar_fallo(username, ahora):
    e = _estado(username)
    e["fallos"] += 1
    if e["fallos"] >= MAX_INTENTOS:
        e["bloqueado_hasta"] = ahora + dt.timedelta(minutes=BLOQUEO_MINUTOS)


def _registrar_exito(username):
    _intentos.pop(username, None)


def verificar_clave(clave, password_hash):
    if not clave or not password_hash:
        return False
    return bcrypt.checkpw(clave.encode("utf-8"), password_hash.encode("utf-8"))


def intentar_login(username, clave, usuario_db, ahora=None):
    """`usuario_db` es la fila de `usuario` para ese username (o `None` si no
    existe): `{"password_hash", "nombre", "activo"}`. Devuelve un token si el
    login es válido; si no, lanza `ValueError` con el motivo. El mensaje no
    distingue "no existe" de "clave mala" para no filtrar qué usuarios hay."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    if bloqueado(username, ahora):
        raise ValueError(f"Demasiados intentos fallidos, esperá {BLOQUEO_MINUTOS} minutos")
    valido = (
        usuario_db is not None
        and usuario_db.get("activo", False)
        and verificar_clave(clave, usuario_db.get("password_hash"))
    )
    if not valido:
        _registrar_fallo(username, ahora)
        raise ValueError("Usuario o clave incorrectos")
    _registrar_exito(username)
    return crear_token(username)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _firma(mensaje: str) -> str:
    return _b64url(hmac.new(config.JWT_SECRET.encode("utf-8"), mensaje.encode("ascii"), hashlib.sha256).digest())


def crear_token(username, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": username,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + dt.timedelta(days=config.TOKEN_DIAS_VENCIMIENTO)).timestamp()),
    }
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    mensaje = f"{_HEADER_B64}.{payload_b64}"
    return f"{mensaje}.{_firma(mensaje)}"


def verificar_token(token, ahora=None):
    """Devuelve el username si el token es válido y no venció; si no, lanza
    `ValueError`."""
    try:
        header_b64, payload_b64, firma = token.split(".")
    except ValueError:
        raise ValueError("Token inválido")
    mensaje = f"{header_b64}.{payload_b64}"
    if header_b64 != _HEADER_B64 or not hmac.compare_digest(firma, _firma(mensaje)):
        raise ValueError("Token inválido")
    try:
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        sub, exp = payload["sub"], payload["exp"]
    except Exception:
        raise ValueError("Token inválido")
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    if ahora.timestamp() > exp:
        raise ValueError("El token venció, hay que loguearse de nuevo")
    return sub
