"""Conexión a Postgres con el rol `movil_api` (permisos mínimos, ver
`movil/migraciones.py`): solo lectura de clientes/productos/usuario e
inserción de pedidos."""
import psycopg2

from . import config


def conexion():
    return psycopg2.connect(
        host=config.DB_HOST,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        connect_timeout=6,
    )


def buscar_usuario(con, username):
    """Fila de `usuario` para el login, o `None` si no existe. Solo las
    columnas que `movil_api` puede leer (ver el GRANT en `migraciones.py`)."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT password_hash, nombre, activo FROM usuario WHERE username = %s",
            (username,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"password_hash": fila[0], "nombre": fila[1], "activo": fila[2]}
