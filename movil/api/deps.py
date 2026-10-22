"""Dependencias de FastAPI (inyección en las rutas). Separado de auth.py para
que ese módulo siga siendo lógica pura, sin importar FastAPI."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth, db

_bearer = HTTPBearer(auto_error=False)


def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    """Exige `Authorization: Bearer <token>` válido y devuelve el username.
    La usan todas las rutas salvo `/auth/login` y `/health`."""
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Falta el token (Authorization: Bearer ...)")
    try:
        return auth.verificar_token(credenciales.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def conexion_actual():
    """Conexión a la base para una ruta, cerrada sola al terminar. Si la base
    no responde, 503 en vez de un 500 crudo (a un vendedor en la calle un
    stacktrace no le dice nada)."""
    try:
        con = db.conexion()
    except Exception:
        raise HTTPException(status_code=503, detail="No se pudo conectar con la base, probá de nuevo en un momento")
    try:
        yield con
    finally:
        con.close()
