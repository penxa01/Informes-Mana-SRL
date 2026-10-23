"""Dependencias de FastAPI (inyección en las rutas). Separado de auth.py para
que ese módulo siga siendo lógica pura, sin importar FastAPI."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth, db

_bearer = HTTPBearer(auto_error=False)


def conexion_actual():
    """Conexión a la base para una ruta, cerrada sola al terminar. Si la base
    no responde, 503 en vez de un 500 crudo (a un vendedor en la calle un
    stacktrace no le dice nada). FastAPI la comparte entre todas las
    dependencias de una misma petición: es una sola conexión por pedido HTTP."""
    try:
        con = db.conexion()
    except Exception:
        raise HTTPException(status_code=503, detail="No se pudo conectar con la base, probá de nuevo en un momento")
    try:
        yield con
    finally:
        con.close()


def _usuario_del_token(credenciales: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Falta el token (Authorization: Bearer ...)")
    try:
        return auth.verificar_token(credenciales.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def usuario_actual(username: str = Depends(_usuario_del_token), con=Depends(conexion_actual)) -> str:
    """Exige `Authorization: Bearer <token>` válido Y que el usuario siga activo
    en la base, y devuelve el username. Así dar de baja a un vendedor
    (`usuario.activo = false`) le corta el acceso al instante, sin esperar a que
    venza su token (7 días). La usan todas las rutas salvo `/auth/login` y
    `/health`. El token se valida primero: sin token ni se toca la base."""
    if not db.usuario_activo(con, username):
        raise HTTPException(status_code=401, detail="Usuario dado de baja")
    return username
