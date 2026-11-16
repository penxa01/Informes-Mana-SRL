"""Dependencias de FastAPI (inyección en las rutas). Separado de auth.py para
que ese módulo siga siendo lógica pura, sin importar FastAPI."""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth, db

_bearer = HTTPBearer(auto_error=False)

# Lo que se le dice al celular que quedó desplazado cuando la cuenta de reparto inicia sesión en otro.
MENSAJE_OTRA_SESION = "Se inició sesión con esta cuenta en otro celular. Volvé a entrar si querés usar este."


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


def _token_valido(credenciales: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """El contenido del token (`{"sub", "sid"}`) si la firma y el vencimiento están bien."""
    if credenciales is None:
        raise HTTPException(status_code=401, detail="Falta el token (Authorization: Bearer ...)")
    try:
        return auth.leer_token(credenciales.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def exigir_rol(*roles):
    """Dependencia que exige `Authorization: Bearer <token>` válido, que el usuario
    siga activo en la base y que su rol esté entre `roles`; devuelve el username.

    Activo y rol se leen de la base en cada petición, no del token: dar de baja a
    alguien (`usuario.activo = false`) o cambiarle el rol le surte efecto al
    instante, sin esperar a que venza su token (7 días). El token se valida
    primero: sin token ni se toca la base. 401 = hay que volver a entrar;
    403 = entró, pero su perfil no puede hacer esto.

    La cuenta de reparto tiene UNA sola sesión: su token lleva el `sid` de la sesión y se compara con el que está en
    la base (`usuario.sesion_id`). Quien inicia sesión en otro celular anota un `sid` nuevo y el celular anterior
    recibe 401 en su próxima petición."""
    def dependencia(token: dict = Depends(_token_valido), con=Depends(conexion_actual)) -> str:
        username = token["sub"]
        rol = db.rol_activo(con, username)
        if rol is None:
            raise HTTPException(status_code=401, detail="Usuario dado de baja")
        if rol not in roles:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene permiso para esto")
        if rol == "reparto" and not db.sesion_vigente(con, username, token["sid"]):
            raise HTTPException(status_code=401, detail=MENSAJE_OTRA_SESION)
        return username
    return dependencia


# `admin` ve todas las pantallas y puede usarlas; `superadmin` es el admin con más control sobre
# la app (gestión de usuarios y demás, a medida que se agregue). Todo lo del admin lo tiene.
ROLES_ADMIN = ("admin", "superadmin")

# Perfiles que ven el panel de control (ventas y recaudación).
panel_actual = exigir_rol(*ROLES_ADMIN)

# El panel propio (sus litros, su cartera y lo cobrado a sus clientes): SOLO el rol `vendedor`. El admin y el superadmin
# ven las cobranzas de TODA la empresa (`GET /panel/cobranzas`, con `panel_actual`) y el reparto no ve números del negocio.
_vendedor_solo = exigir_rol("vendedor")


def vendedor_con_codigo(username: str = Depends(_vendedor_solo), con=Depends(conexion_actual)) -> int:
    """Código de vendedor del usuario que inició sesión, leído de la base. No hay forma de pedir el panel de
    otro: la ruta no recibe ningún código ni nombre, solo el token.

    Sin código asignado es 404 y no 403: la app trata todo 403 como "tu perfil cambió" y vuelve al login, y acá el
    perfil es el correcto, solo falta que el administrador le cargue el código."""
    codigo = db.vendedor_id_de(con, username)
    if codigo is None or codigo <= 0:   # 0 es la fila de la empresa entera: nunca es de un vendedor
        raise HTTPException(status_code=404, detail="Tu usuario no tiene un código de vendedor asignado: pedile al administrador que lo cargue")
    return codigo


# Perfiles que programan, quitan artículos y borran pedidos desde el celular: los admin. El reparto NO.
admin_actual = exigir_rol(*ROLES_ADMIN)

# Todos los perfiles pueden activar avisos en su celular (qué recibe cada uno lo decide el proceso notificador).
avisos_actual = exigir_rol("vendedor", "reparto", *ROLES_ADMIN)

# Perfiles que cargan pedidos y bajan el catálogo.
vendedor_actual = exigir_rol("vendedor", *ROLES_ADMIN)

# Solo la cuenta de reparto manda la posición de su celular (los admin la ven en el mapa, pero no mandan la suya).
solo_reparto = exigir_rol("reparto")

# Perfiles que ven los pedidos por entregar y los llevan hasta el cliente (en camino, entregado total o parcial, y la
# ubicación del cliente): el reparto y los admin.
reparto_actual = exigir_rol("reparto", *ROLES_ADMIN)
