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


CLAVE_MINIMA = 8
CLAVE_MAXIMA_BYTES = 72  # bcrypt ignora en silencio lo que pase de 72 bytes


def validar_clave(password, username=""):
    """Motivo por el que la clave no sirve, o None si está bien."""
    if len(password or "") < CLAVE_MINIMA:
        return f"La clave tiene que tener al menos {CLAVE_MINIMA} caracteres"
    if len(password.encode("utf-8")) > CLAVE_MAXIMA_BYTES:
        return f"La clave es demasiado larga (máximo {CLAVE_MAXIMA_BYTES} caracteres)"
    if password.strip().lower() == (username or "").strip().lower():
        return "La clave no puede ser igual al usuario"
    if password != password.strip():
        return "La clave no puede empezar ni terminar con espacios"
    return None


def fijar_clave(con, username, password):
    """Cambia la clave de un usuario que ya existe (queda en bcrypt, nunca en claro).
    Devuelve True si lo encontró. No hace commit. No toca el rol ni si está activo, y las
    sesiones ya abiertas siguen valiendo hasta que venzan (7 días): para cortar un acceso
    de inmediato se lo da de baja (`activo = false`)."""
    hash_clave = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with con.cursor() as cur:
        cur.execute("UPDATE usuario SET password_hash = %s WHERE username = %s", (hash_clave, username))
        return cur.rowcount == 1


def listar_usuarios(con):
    """[(username, nombre, rol, activo)] ordenados por rol y usuario."""
    with con.cursor() as cur:
        cur.execute("SELECT username, nombre, rol, activo FROM usuario ORDER BY rol, username")
        return cur.fetchall()
