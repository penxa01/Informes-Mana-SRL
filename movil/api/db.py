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
