"""Login de la API móvil (movil/api/auth.py): bcrypt, token con vencimiento
y límite de intentos. Sin base: todo con datos en memoria.

Correr desde la raíz:  python movil/tests/verificar_auth.py
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

import bcrypt

from movil.api import auth

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def lanza(fn, *args, **kw):
    try:
        fn(*args, **kw)
        return None
    except ValueError as e:
        return str(e)


def hash_de(clave):
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


CLAVE_OK = "laClaveCorrecta123"
HASH_OK = hash_de(CLAVE_OK)
activo = {"password_hash": HASH_OK, "nombre": "MIGUEL ORTUÑO", "activo": True}
inactivo = {**activo, "activo": False}

print("=== verificar_clave ===")
check("clave correcta", auth.verificar_clave(CLAVE_OK, HASH_OK))
check("clave incorrecta", not auth.verificar_clave("otra", HASH_OK))
check("clave vacía", not auth.verificar_clave("", HASH_OK))
check("hash vacío/None no rompe", not auth.verificar_clave(CLAVE_OK, None))

print("=== token ===")
tok = auth.crear_token("miguel")
check("token válido devuelve el username", auth.verificar_token(tok) == "miguel")

hace_10_dias = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
tok_viejo = auth.crear_token("miguel", ahora=hace_10_dias)  # vence a los 7 días
err = lanza(auth.verificar_token, tok_viejo)
check("token vencido -> error", err is not None and "venc" in err.lower(), err)
check("token con otra clave no es válido", lanza(auth.verificar_token, tok + "x") is not None)

print("=== intentar_login (clave mala, usuario inactivo, inexistente) ===")
tok2 = auth.intentar_login("miguel", CLAVE_OK, activo)
check("login correcto devuelve un token válido", auth.verificar_token(tok2) == "miguel")
check("clave mala", lanza(auth.intentar_login, "miguel", "mala", activo) is not None)
check("usuario inactivo", lanza(auth.intentar_login, "exempleado", CLAVE_OK, inactivo) is not None)
check("usuario inexistente", lanza(auth.intentar_login, "fantasma", "x", None) is not None)
check("no distingue inexistente de clave mala (mismo mensaje)",
      lanza(auth.intentar_login, "fantasma", "x", None) == lanza(auth.intentar_login, "miguel", "mala", activo))

print("=== bloqueo tras varios intentos ===")
t0 = dt.datetime.now(dt.timezone.utc)
for _ in range(auth.MAX_INTENTOS - 1):
    lanza(auth.intentar_login, "bloqueable", "mala", activo, t0)
check("todavía no bloqueado antes de llegar al límite", not auth.bloqueado("bloqueable", t0))
lanza(auth.intentar_login, "bloqueable", "mala", activo, t0)  # fallo número MAX_INTENTOS
check("bloqueado al llegar a MAX_INTENTOS fallos", auth.bloqueado("bloqueable", t0))
err = lanza(auth.intentar_login, "bloqueable", CLAVE_OK, activo, t0)
check("bloqueado rechaza aunque la clave sea correcta", err is not None, err)

despues = t0 + dt.timedelta(minutes=auth.BLOQUEO_MINUTOS + 1)
check("el bloqueo se levanta solo, pasados BLOQUEO_MINUTOS", not auth.bloqueado("bloqueable", despues))
tok3 = auth.intentar_login("bloqueable", CLAVE_OK, activo, despues)
check("y ahí sí puede loguearse de nuevo", auth.verificar_token(tok3) == "bloqueable")

print("=== un login correcto resetea el contador de fallos ===")
for _ in range(auth.MAX_INTENTOS - 1):
    lanza(auth.intentar_login, "resetable", "mala", activo)
auth.intentar_login("resetable", CLAVE_OK, activo)
check("después de loguearse bien, no queda bloqueado", not auth.bloqueado("resetable"))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
