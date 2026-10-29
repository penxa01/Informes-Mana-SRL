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


def exigir_rol(*roles):
    """Dependencia que exige `Authorization: Bearer <token>` válido, que el usuario
    siga activo en la base y que su rol esté entre `roles`; devuelve el username.

    Activo y rol se leen de la base en cada petición, no del token: dar de baja a
    alguien (`usuario.activo = false`) o cambiarle el rol le surte efecto al
    instante, sin esperar a que venza su token (7 días). El token se valida
    primero: sin token ni se toca la base. 401 = hay que volver a entrar;
    403 = entró, pero su perfil no puede hacer esto."""
    def dependencia(username: str = Depends(_usuario_del_token), con=Depends(conexion_actual)) -> str:
        rol = db.rol_activo(con, username)
        if rol is None:
            raise HTTPException(status_code=401, detail="Usuario dado de baja")
        if rol not in roles:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene permiso para esto")
        return username
    return dependencia


# `admin` ve todas las pantallas y puede usarlas; `superadmin` es el admin con más control sobre
# la app (gestión de usuarios y demás, a medida que se agregue). Todo lo del admin lo tiene.
ROLES_ADMIN = ("admin", "superadmin")

# Perfiles que ven el panel de control (ventas y recaudación).
panel_actual = exigir_rol(*ROLES_ADMIN)

# Todos los perfiles pueden activar avisos en su celular (qué recibe cada uno lo decide el proceso notificador).
avisos_actual = exigir_rol("vendedor", "reparto", *ROLES_ADMIN)

# Perfiles que cargan pedidos y bajan el catálogo.
vendedor_actual = exigir_rol("vendedor", *ROLES_ADMIN)

# Perfiles que ven los pedidos a entregar y los marcan como entregados: el reparto y los admin
# (si hubiera que dejarlos solo mirando, se cambia acá).
reparto_actual = exigir_rol("reparto", *ROLES_ADMIN)
