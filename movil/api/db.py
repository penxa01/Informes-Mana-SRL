"""Conexión a Postgres con el rol `movil_api` (permisos mínimos, ver
`movil/migraciones.py`): lectura de clientes/productos/usuario, inserción de
pedidos y, para el reparto, marcar entregas."""
import hashlib
import socket

import psycopg2

from . import config


def conexion():
    # Igual que _conexion() de programarPedido.py: psycopg2/libpq no siempre
    # resuelve el nombre de máquina de Windows (ej. "DESKTOP-R8E4V7S"), pero
    # socket.gethostbyname sí. Sin esto, conectar a `config.DB_HOST` falla
    # con un OperationalError sin mensaje.
    return psycopg2.connect(
        host=socket.gethostbyname(config.DB_HOST),
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
            "SELECT password_hash, nombre, activo, rol FROM usuario WHERE username = %s",
            (username,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"password_hash": fila[0], "nombre": fila[1], "activo": fila[2], "rol": fila[3] or ""}


def rol_activo(con, username):
    """Rol del usuario ('vendedor', 'reparto', 'admin'...) si existe y está
    activo; `None` si no existe o está dado de baja. Se consulta en cada
    petición (ver `deps.exigir_rol`), no solo en el login: así dar de baja o
    cambiar de rol a alguien le surte efecto al instante."""
    with con.cursor() as cur:
        cur.execute("SELECT activo, rol FROM usuario WHERE username = %s", (username,))
        fila = cur.fetchone()
    if not fila or not fila[0]:
        return None
    return fila[1] or ""


def usuario_activo(con, username):
    """True si el usuario existe y está activo (con cualquier rol)."""
    return rol_activo(con, username) is not None


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


def pedidos_para_reparto(con):
    """Pedidos programados o en camino, con las líneas y los datos del cliente que
    el reparto necesita para llegar (dirección, teléfono y ubicación). Los más
    próximos primero; los sin fecha, al final."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT p.id_pedido, p.estado_pedido, p.fecha_pedido, p.fecha_entrega, "
            "       c.id_cliente, c.nombre, c.direccion, c.telefono, c.localidad, "
            "       c.ubicacion_maps, c.ubicacion_lat, c.ubicacion_lng "
            "FROM pedido p JOIN cliente c ON c.id_cliente = p.id_cliente "
            "WHERE p.estado_pedido IN ('programado', 'en camino') "
            "ORDER BY p.fecha_entrega NULLS LAST, p.id_pedido"
        )
        filas = cur.fetchall()
        ids = [f[0] for f in filas]
        lineas = {i: [] for i in ids}
        if ids:
            cur.execute(
                "SELECT d.id_pedido, d.id_producto, pr.nombre, d.cantidad, d.cantidad_entregada "
                "FROM detallepedido d LEFT JOIN producto pr ON pr.id_producto = d.id_producto "
                "WHERE d.id_pedido = ANY(%s) ORDER BY d.id_pedido, d.id_detalle",
                (ids,),
            )
            for id_pedido, id_producto, nombre, cantidad, entregada in cur.fetchall():
                lineas[id_pedido].append({
                    "id_producto": id_producto, "nombre": nombre,
                    "cantidad": cantidad, "entregada": entregada,
                })
    return [
        {
            "id_pedido": f[0], "estado": f[1], "fecha_pedido": f[2], "fecha_entrega": f[3],
            "cliente": {
                "id": f[4], "nombre": f[5], "direccion": f[6], "telefono": f[7], "localidad": f[8],
                "ubicacion_maps": f[9], "ubicacion_lat": f[10], "ubicacion_lng": f[11],
            },
            "lineas": lineas[f[0]],
        }
        for f in filas
    ]


def marcar_entregado(con, id_pedido):
    """Entrega COMPLETA de un pedido, igual que "Entrega Completa" en la PC: todas las
    líneas quedan entregadas y el pedido pasa a 'entregado' con la fecha de hoy
    (no la programada). No hace commit: lo decide quien llama.

    Devuelve 'entregado' (lo marcó ahora), 'ya_estaba' (ya estaba entregado: reenviar
    la orden no hace nada, es lo que permite reintentar sin riesgo), 'sin_programar'
    (todavía 'pendiente': no es del reparto) o 'no_existe'. La fila se bloquea
    mientras tanto, para que dos celulares a la vez no se pisen."""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe"
        if fila[0] == "entregado":
            return "ya_estaba"
        if fila[0] not in ("programado", "en camino"):
            return "sin_programar"
        cur.execute("UPDATE detallepedido SET cantidad_entregada = cantidad WHERE id_pedido = %s", (id_pedido,))
        cur.execute(
            "UPDATE pedido SET estado_pedido = 'entregado', fecha_entrega = CURRENT_DATE WHERE id_pedido = %s",
            (id_pedido,),
        )
    return "entregado"


def enlace_maps(lat, lng):
    """Enlace de Google Maps a un punto (formato oficial de URLs de Maps). La PC lo
    entiende: de ahí saca las coordenadas para su mapita."""
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"


def guardar_ubicacion_cliente(con, id_cliente, lat, lng):
    """Guarda la ubicación de un cliente (la del reparto, tomada con el GPS del celular).
    No hace commit: lo decide quien llama.

    Solo si el cliente tiene una entrega pendiente (programado / en camino): el reparto
    no tiene por qué tocar a cualquiera. Y nunca pisa una ubicación ya cargada: si la de
    la oficina estuviera mal, se corrige desde la PC. Devuelve 'guardada', 'sin_entregas'
    o 'ya_tiene'."""
    lat, lng = round(lat, 6), round(lng, 6)
    with con.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pedido WHERE id_cliente = %s AND estado_pedido IN ('programado', 'en camino') LIMIT 1",
            (id_cliente,),
        )
        if cur.fetchone() is None:
            return "sin_entregas"
        cur.execute(
            "UPDATE cliente SET ubicacion_maps = %s, ubicacion_lat = %s, ubicacion_lng = %s "
            "WHERE id_cliente = %s AND ubicacion_maps IS NULL AND ubicacion_lat IS NULL",
            (enlace_maps(lat, lng), lat, lng, id_cliente),
        )
        return "guardada" if cur.rowcount == 1 else "ya_tiene"
