"""Alta de usuarios de la app móvil en la tabla `usuario` (clave en bcrypt).

No hace commit: quien llama decide (los tests revierten). Roles que entiende la
API: `vendedor` (carga pedidos), `reparto` (marca entregas) y `admin`.
"""
import bcrypt

ROLES = ("admin", "vendedor", "reparto")


def crear_usuario(con, username, password, nombre, rol):
    """Crea el usuario si no existe. Devuelve True si lo creó y False si ya estaba
    (en ese caso no toca ni su clave ni su rol: para eso hay que hacerlo a propósito)."""
    if rol not in ROLES:
        raise ValueError(f"rol desconocido: {rol!r} (válidos: {', '.join(ROLES)})")
    hash_clave = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO usuario (username, password_hash, nombre, rol, activo) "
            "VALUES (%s, %s, %s, %s, true) ON CONFLICT (username) DO NOTHING",
            (username, hash_clave, nombre, rol),
        )
        return cur.rowcount == 1
