"""Conexión a Postgres con el rol `movil_api` (permisos mínimos, ver
`movil/migraciones.py`): solo lectura de clientes/productos/usuario e
inserción de pedidos."""
import hashlib

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


def catalogo(con):
    """Clientes y productos para armar un pedido desde el celular: nunca
    teléfono, dirección, stock ni saldos. `version` es un hash del contenido,
    para que el celular sepa si lo que tiene cacheado cambió sin tener que
    volver a bajar 2.100+ filas por Tailscale cada vez."""
    with con.cursor() as cur:
        cur.execute("SELECT id_cliente, nombre, cuit, localidad FROM cliente ORDER BY id_cliente")
        clientes = [{"id": r[0], "nombre": r[1], "cuit": r[2], "localidad": r[3]} for r in cur.fetchall()]
        cur.execute("SELECT id_producto, nombre FROM producto ORDER BY id_producto")
        productos = [{"id": r[0], "nombre": r[1]} for r in cur.fetchall()]

    firma = hashlib.sha256()
    for c in clientes:
        firma.update(f"{c['id']}|{c['nombre']}|{c['cuit']}|{c['localidad']}\n".encode("utf-8"))
    for p in productos:
        firma.update(f"{p['id']}|{p['nombre']}\n".encode("utf-8"))
    return clientes, productos, firma.hexdigest()
