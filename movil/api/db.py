"""Conexión a Postgres con el rol `movil_api` (permisos mínimos, ver
`movil/migraciones.py`): lectura de clientes/productos/usuario, inserción de
pedidos y, para el reparto y los admin, avanzar los pedidos (en camino, entregas, programar, quitar un artículo)."""
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


def vendedor_id_de(con, username):
    """Código de vendedor (`usuario.vendedor_id`) del usuario activo, o `None` si no existe, está dado de baja
    o no tiene código asignado. De acá sale de quién es el panel de un vendedor (`routers/panel.py`): nunca de
    lo que mande el celular."""
    with con.cursor() as cur:
        cur.execute("SELECT vendedor_id FROM usuario WHERE username = %s AND activo", (username,))
        fila = cur.fetchone()
    return None if not fila or fila[0] is None else int(fila[0])


def id_usuario(con, username):
    """`usuario.id` del usuario activo, o `None`."""
    with con.cursor() as cur:
        cur.execute("SELECT id FROM usuario WHERE username = %s AND activo", (username,))
        fila = cur.fetchone()
    return fila[0] if fila else None


def guardar_suscripcion(con, id_usuario, endpoint, p256dh, auth, maximo):
    """Registra (o actualiza) la suscripción de un celular a los avisos. Idempotente: el celular la manda
    cada vez que abre la app. Si el mismo celular entra con otro usuario, la suscripción pasa a ese usuario
    (así los avisos de reparto no le llegan a quien ya no lo usa). Cada usuario conserva como mucho
    `maximo` dispositivos: se descartan los más viejos."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO push_suscripcion (usuario_id, endpoint, p256dh, auth) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (endpoint) DO UPDATE SET usuario_id = EXCLUDED.usuario_id, p256dh = EXCLUDED.p256dh, "
            "auth = EXCLUDED.auth, creado_en = now()",
            (id_usuario, endpoint, p256dh, auth),
        )
        cur.execute(
            "DELETE FROM push_suscripcion WHERE usuario_id = %s AND id NOT IN "
            "(SELECT id FROM push_suscripcion WHERE usuario_id = %s ORDER BY creado_en DESC, id DESC LIMIT %s)",
            (id_usuario, id_usuario, maximo),
        )


def borrar_suscripcion(con, id_usuario, endpoint):
    """Da de baja la suscripción de ESTE usuario (nunca la de otro). True si existía."""
    with con.cursor() as cur:
        cur.execute("DELETE FROM push_suscripcion WHERE usuario_id = %s AND endpoint = %s", (id_usuario, endpoint))
        return cur.rowcount > 0


def usuario_activo(con, username):
    """True si el usuario existe y está activo (con cualquier rol)."""
    return rol_activo(con, username) is not None


def fijar_sesion(con, username, sid):
    """Anota `sid` como la sesión activa de la cuenta de reparto: pisa la anterior, así el celular que estaba usando
    esa cuenta deja de valer en su próxima petición (ver `deps.exigir_rol`). No hace commit."""
    with con.cursor() as cur:
        cur.execute("UPDATE usuario SET sesion_id = %s WHERE username = %s", (sid, username))


def sesion_vigente(con, username, sid):
    """True si `sid` (el de un token) es la sesión activa de ese usuario. Un token sin `sid` solo vale mientras no
    haya una sesión anotada (los tokens de antes de que existiera esto, hasta que el reparto vuelva a entrar)."""
    with con.cursor() as cur:
        cur.execute("SELECT sesion_id FROM usuario WHERE username = %s", (username,))
        fila = cur.fetchone()
    return fila is not None and fila[0] == sid


def clientes_con_ubicacion(con):
    """Los clientes que tienen la ubicación cargada (latitud y longitud), para el mapa. Solo lo básico para
    reconocerlos en el mapa: nombre, dirección y localidad. Sin teléfono ni CUIT."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT id_cliente, nombre, direccion, localidad, ubicacion_lat, ubicacion_lng FROM cliente "
            "WHERE ubicacion_lat IS NOT NULL AND ubicacion_lng IS NOT NULL ORDER BY nombre"
        )
        return [
            {"id": r[0], "nombre": r[1], "direccion": r[2], "localidad": r[3], "lat": r[4], "lng": r[5]}
            for r in cur.fetchall()
        ]


def guardar_posicion_reparto(con, username, lat, lng, precision_m):
    """Guarda la última posición del celular de la cuenta de reparto (una sola fila por usuario: se pisa, no hay
    historial). No hace commit."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO ubicacion_reparto (username, lat, lng, precision_m, actualizado_en) "
            "VALUES (%s, %s, %s, %s, now()) "
            "ON CONFLICT (username) DO UPDATE SET lat = EXCLUDED.lat, lng = EXCLUDED.lng, "
            "precision_m = EXCLUDED.precision_m, actualizado_en = EXCLUDED.actualizado_en",
            (username, lat, lng, precision_m),
        )


# Una posición más vieja que esto no se muestra: el celular dejó de mandarla (cerró la app, salió, se quedó sin
# señal) y mostrar dónde estaba hace horas confunde y es información que no hace falta.
POSICION_REPARTO_MAX_MINUTOS = 15


def posiciones_reparto(con):
    """Dónde están los celulares de la cuenta de reparto ahora: solo las posiciones recientes. `hace_seg` lo
    calcula la base (con su reloj), así no depende de la hora del celular de quien mira."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT r.username, COALESCE(u.nombre, r.username), r.lat, r.lng, r.precision_m, "
            "       GREATEST(0, EXTRACT(EPOCH FROM (now() - r.actualizado_en)))::int "
            "FROM ubicacion_reparto r LEFT JOIN usuario u ON u.username = r.username "
            "WHERE r.actualizado_en > now() - make_interval(mins => %s) ORDER BY r.username",
            (POSICION_REPARTO_MAX_MINUTOS,),
        )
        return [
            {"usuario": r[0], "nombre": r[1], "lat": r[2], "lng": r[3], "precision_m": r[4], "hace_seg": r[5]}
            for r in cur.fetchall()
        ]


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


def crear_pedido(con, uuid_cliente, id_cliente, fecha_pedido, lineas, creado_por, observaciones=None):
    """Crea el pedido y sus líneas; `lineas` ya viene validada y sumada
    (`movil.api.pedidos.validar_lineas`) y `observaciones` ya viene limpia
    (`pedidos.limpiar_observaciones`: texto o `None`). Idempotente por `uuid_cliente`: si
    ya existe un pedido con ese uuid, no inserta de nuevo y devuelve el id
    existente con `ya_existia=True`. No hace commit: lo decide quien llama."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen, uuid_cliente, creado_por, observaciones) "
            "VALUES (%s, %s, 'pendiente', 'movil', %s, %s, %s) "
            "ON CONFLICT (uuid_cliente) WHERE uuid_cliente IS NOT NULL DO NOTHING RETURNING id_pedido",
            (id_cliente, fecha_pedido, uuid_cliente, creado_por, observaciones),
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


def _con_lineas(cur, filas):
    """Arma los pedidos por entregar (cliente y su ubicación, quién lo cargó y sus líneas) a partir de las filas de
    `_SELECT_GESTION`."""
    ids = [f[0] for f in filas]
    lineas = {i: [] for i in ids}
    if ids:
        cur.execute(
            "SELECT d.id_pedido, d.id_detalle, d.id_producto, pr.nombre, d.cantidad, d.cantidad_entregada "
            "FROM detallepedido d LEFT JOIN producto pr ON pr.id_producto = d.id_producto "
            "WHERE d.id_pedido = ANY(%s) ORDER BY d.id_pedido, d.id_detalle",
            (ids,),
        )
        for id_pedido, id_detalle, id_producto, nombre, cantidad, entregada in cur.fetchall():
            lineas[id_pedido].append({"id_detalle": id_detalle, "id_producto": id_producto, "nombre": nombre,
                                      "cantidad": cantidad, "entregada": entregada})
    return [
        {"id_pedido": f[0], "estado": f[1], "origen": f[2], "fecha_pedido": f[3], "fecha_entrega": f[4],
         "cliente": f[5], "id_cliente": f[6], "direccion": f[7], "ubicacion_maps": f[8], "ubicacion_lat": f[9],
         "ubicacion_lng": f[10], "cargado_por": f[11], "observaciones": f[12], "lineas": lineas[f[0]]}
        for f in filas
    ]


_SELECT_GESTION = (
    "SELECT p.id_pedido, p.estado_pedido, p.origen, p.fecha_pedido, p.fecha_entrega, c.nombre, c.id_cliente, "
    "       c.direccion, c.ubicacion_maps, c.ubicacion_lat, c.ubicacion_lng, u.nombre, p.observaciones "
    "FROM pedido p JOIN cliente c ON c.id_cliente = p.id_cliente "
    "LEFT JOIN usuario u ON u.username = p.creado_por "
)


def pedidos_para_gestion(con):
    """Los pedidos que todavía hay que entregar (pendientes, programados y en camino), los más próximos primero y
    los sin fecha al final. Es la única lista de pedidos de la app: la ven el reparto y los admin. Cada uno trae sus
    líneas (qué se pidió y cuánto se entregó), la dirección del cliente y su ubicación (para llegar, y para
    cargarla si falta). Sin teléfono: nadie llama desde la app. Los entregados no se listan."""
    with con.cursor() as cur:
        cur.execute(_SELECT_GESTION +
                    "WHERE p.estado_pedido IN ('pendiente', 'programado', 'en camino') "
                    "ORDER BY p.fecha_entrega NULLS LAST, p.id_pedido")
        return _con_lineas(cur, cur.fetchall())


def marcar_en_camino(con, id_pedido):
    """Marca el pedido como 'en camino' (sale a repartirse), igual que "En Camino" en la PC: no toca la fecha de
    entrega ni las cantidades, y sirve desde 'pendiente' o 'programado' (no hace falta programarlo antes). No hace
    commit. Devuelve 'en_camino' (lo marcó ahora), 'ya_estaba' (ya estaba así: reintentar no hace nada),
    'ya_entregado' o 'no_existe'."""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe"
        if fila[0] == "entregado":
            return "ya_entregado"
        if fila[0] == "en camino":
            return "ya_estaba"
        cur.execute("UPDATE pedido SET estado_pedido = 'en camino' WHERE id_pedido = %s", (id_pedido,))
    return "en_camino"


def entregar_pedido_total(con, id_pedido):
    """Entrega COMPLETA, igual que "Entrega Completa" en la PC: todas las líneas quedan entregadas y el pedido pasa
    a 'entregado' con la fecha de hoy (la real, no la programada). Sirve desde cualquier estado (pendiente,
    programado o en camino). No hace commit. Devuelve 'entregado', 'ya_estaba' (ya estaba entregado: reintentar no
    hace nada) o 'no_existe'. La fila se bloquea mientras tanto, para que dos celulares a la vez no se pisen."""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe"
        if fila[0] == "entregado":
            return "ya_estaba"
        cur.execute("UPDATE detallepedido SET cantidad_entregada = cantidad WHERE id_pedido = %s", (id_pedido,))
        cur.execute("UPDATE pedido SET estado_pedido = 'entregado', fecha_entrega = CURRENT_DATE WHERE id_pedido = %s",
                    (id_pedido,))
    return "entregado"


def entrega_parcial(con, id_pedido, objetivos):
    """Entrega PARCIAL: `objetivos` es {id_detalle: cantidad entregada que tiene que quedar}. Se manda el total
    que debe quedar (no cuánto se entrega ahora) para que reintentar la misma orden —por ejemplo, si se perdió
    la respuesta— no entregue dos veces. Sirve desde cualquier estado (pendiente, programado o en camino). No hace
    commit. Devuelve `(resultado, detalle)`:
      ('parcial', None)                se aplicó y falta entregar algo: el pedido VUELVE A 'pendiente' (sin fecha
                                       de entrega: hay que programarlo de nuevo) y conserva solo lo que falta
      ('completo', None)               se aplicó y no queda nada por entregar: el pedido pasa a 'entregado' con la
                                       fecha de hoy, como en la PC
      ('sin_cambios', None)            ya estaba así (un reintento)
      ('ya_entregado', None)           el pedido ya estaba entregado
      ('no_existe', None)
      ('linea_ajena', id_detalle)      esa línea no es de este pedido
      ('excede', id_detalle)           más de lo pedido
      ('cambio', id_detalle)           ya se había entregado más que eso (alguien lo cambió mientras tanto)"""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe", None
        if fila[0] == "entregado":
            return "ya_entregado", None
        cur.execute("SELECT id_detalle, cantidad, cantidad_entregada FROM detallepedido "
                    "WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        actuales = {f[0]: (f[1], f[2]) for f in cur.fetchall()}
        for id_detalle, objetivo in objetivos.items():
            if id_detalle not in actuales:
                return "linea_ajena", id_detalle
            cantidad, entregada = actuales[id_detalle]
            if objetivo > cantidad:
                return "excede", id_detalle
            if objetivo < entregada:
                return "cambio", id_detalle
        cambios = {i: o for i, o in objetivos.items() if o > actuales[i][1]}
        if not cambios:
            return "sin_cambios", None
        for id_detalle, objetivo in cambios.items():
            cur.execute("UPDATE detallepedido SET cantidad_entregada = %s WHERE id_detalle = %s AND id_pedido = %s",
                        (objetivo, id_detalle, id_pedido))
        cur.execute("SELECT count(*) FROM detallepedido WHERE id_pedido = %s AND cantidad_entregada < cantidad", (id_pedido,))
        if cur.fetchone()[0] == 0:
            cur.execute("UPDATE pedido SET estado_pedido = 'entregado', fecha_entrega = CURRENT_DATE WHERE id_pedido = %s",
                        (id_pedido,))
            return "completo", None
        # Queda algo por entregar: el pedido vuelve a la lista de pendientes, a la espera de que se programe otra vez.
        cur.execute("UPDATE pedido SET estado_pedido = 'pendiente', fecha_entrega = NULL WHERE id_pedido = %s",
                    (id_pedido,))
    return "parcial", None


def quitar_linea(con, id_pedido, id_detalle):
    """Quita UN artículo de un pedido que todavía no se entregó (el cliente lo sacó, o se cargó por error). Es el
    mismo borrado que hace la PC en el detalle del pedido. No hace commit. Devuelve:
      'quitada'              se quitó; el pedido sigue con los demás artículos
      'completo'             se quitó y lo que queda ya estaba todo entregado: el pedido pasa a 'entregado' con la
                             fecha de hoy (igual que al completar una entrega parcial)
      'ya_no_estaba'         esa línea ya no está en el pedido (un reintento no hace nada)
      'no_existe'            el pedido no existe
      'ya_entregado'         el pedido ya está entregado (es historia de ventas: se toca desde la PC)
      'entregada_en_parte'   de ese artículo ya se entregó algo: borrarlo borraría lo entregado
      'es_la_unica'          es el único artículo: un pedido vacío no tiene sentido, se borra el pedido entero"""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe"
        if fila[0] == "entregado":
            return "ya_entregado"
        cur.execute("SELECT id_detalle, cantidad_entregada FROM detallepedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        lineas = dict(cur.fetchall())
        if id_detalle not in lineas:
            return "ya_no_estaba"
        if lineas[id_detalle] > 0:
            return "entregada_en_parte"
        if len(lineas) == 1:
            return "es_la_unica"
        cur.execute("DELETE FROM detallepedido WHERE id_detalle = %s AND id_pedido = %s", (id_detalle, id_pedido))
        cur.execute("SELECT count(*) FROM detallepedido WHERE id_pedido = %s AND cantidad_entregada < cantidad", (id_pedido,))
        if cur.fetchone()[0] == 0:
            cur.execute("UPDATE pedido SET estado_pedido = 'entregado', fecha_entrega = CURRENT_DATE WHERE id_pedido = %s",
                        (id_pedido,))
            return "completo"
    return "quitada"


def programar_pedido(con, id_pedido, fecha):
    """Programa el pedido para esa fecha (estado 'programado'), igual que "Programar" en la PC; sirve también
    para reprogramar uno que no se pudo entregar. La fecha no puede ser anterior a hoy (la del servidor) y un
    pedido ya entregado no se programa. No hace commit.
    Devuelve 'programado', 'no_existe', 'ya_entregado' o 'fecha_pasada'."""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido, %s::date >= CURRENT_DATE FROM pedido WHERE id_pedido = %s FOR UPDATE",
                    (fecha, id_pedido))
        fila = cur.fetchone()
        if fila is None:
            return "no_existe"
        if fila[0] == "entregado":
            return "ya_entregado"
        if not fila[1]:
            return "fecha_pasada"
        cur.execute("UPDATE pedido SET estado_pedido = 'programado', fecha_entrega = %s WHERE id_pedido = %s",
                    (fecha, id_pedido))
    return "programado"


def borrar_pedido(con, id_pedido):
    """Borra el pedido (y sus líneas, por la clave foránea) de forma física, como "Eliminar" en la PC: es para
    cuando un cliente cancela. Un pedido ya ENTREGADO no se borra desde el celular (es historia de ventas y se
    toca desde la PC). No hace commit. Devuelve 'borrado', 'ya_no_estaba' (reintentar no hace nada) o 'entregado'."""
    with con.cursor() as cur:
        cur.execute("SELECT estado_pedido FROM pedido WHERE id_pedido = %s FOR UPDATE", (id_pedido,))
        fila = cur.fetchone()
        if fila is None:
            return "ya_no_estaba"
        if fila[0] == "entregado":
            return "entregado"
        cur.execute("DELETE FROM pedido WHERE id_pedido = %s", (id_pedido,))
    return "borrado"


def enlace_maps(lat, lng):
    """Enlace de Google Maps a un punto (formato oficial de URLs de Maps). La PC lo
    entiende: de ahí saca las coordenadas para su mapita."""
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"


def guardar_ubicacion_cliente(con, id_cliente, lat, lng):
    """Guarda la ubicación de un cliente (la del reparto, tomada con el GPS del celular).
    No hace commit: lo decide quien llama.

    Solo si el cliente tiene un pedido sin entregar (pendiente, programado o en camino) o entregado
    en los últimos 3 días: el reparto no tiene por qué tocar a cualquiera, y lo de "entregado
    hace poco" cubre la ubicación que se sincroniza DESPUÉS de la entrega (sin señal). Y
    nunca pisa una ubicación ya cargada: si la de la oficina estuviera mal, se corrige desde
    la PC. Devuelve 'guardada', 'sin_entregas' o 'ya_tiene'."""
    lat, lng = round(lat, 6), round(lng, 6)
    with con.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pedido WHERE id_cliente = %s AND (estado_pedido <> 'entregado' "
            "OR fecha_entrega >= CURRENT_DATE - 3) LIMIT 1",
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
