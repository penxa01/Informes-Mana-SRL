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


def cliente_existe(con, id_cliente):
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM cliente WHERE id_cliente = %s", (id_cliente,))
        return cur.fetchone() is not None


def productos_inexistentes(con, ids):
    """Subconjunto de `ids` que NO está en `producto`, en el mismo orden."""
    if not ids:
        return []
    with con.cursor() as cur:
        cur.execute("SELECT id_producto FROM producto WHERE id_producto = ANY(%s)", (list(ids),))
        existentes = {r[0] for r in cur.fetchall()}
    return [i for i in ids if i not in existentes]


def crear_pedido(con, uuid_cliente, id_cliente, fecha_pedido, lineas, creado_por):
    """Crea el pedido y sus líneas; `lineas` ya viene validada y sumada
    (`movil.api.pedidos.validar_lineas`). Idempotente por `uuid_cliente`: si
    ya existe un pedido con ese uuid, no inserta de nuevo y devuelve el id
    existente con `ya_existia=True`. No hace commit: lo decide quien llama."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen, uuid_cliente, creado_por) "
            "VALUES (%s, %s, 'pendiente', 'movil', %s, %s) "
            "ON CONFLICT (uuid_cliente) WHERE uuid_cliente IS NOT NULL DO NOTHING RETURNING id_pedido",
            (id_cliente, fecha_pedido, uuid_cliente, creado_por),
        )
        fila = cur.fetchone()
        if fila is not None:
            id_pedido = fila[0]
            for id_producto, cantidad in lineas:
                cur.execute(
                    "INSERT INTO detallepedido (id_pedido, id_producto, cantidad, precio_unitario) "
                    "VALUES (%s, %s, %s, 0)",
                    (id_pedido, id_producto, cantidad),
                )
            return id_pedido, False

        cur.execute("SELECT id_pedido FROM pedido WHERE uuid_cliente = %s", (uuid_cliente,))
        return cur.fetchone()[0], True
