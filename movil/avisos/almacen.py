"""Lo que el proceso notificador lee y escribe en la base (como `movil_api`): qué pedidos revisar, los
avisos ya enviados y las suscripciones de los celulares. No hace commit: lo decide quien llama."""


def hay_registros(con):
    """True si ya se anotó algún aviso (si no, es la primera vez que corre: hay que sembrar)."""
    with con.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM notificacion_enviada)")
        return cur.fetchone()[0]


def sembrar(con):
    """Anota como ya avisado todo lo que los pedidos existentes ya superaron, para que al instalar el
    proceso no llegue un aviso por cada pedido que ya estaba. Devuelve cuántos renglones anotó."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO notificacion_enviada (evento, id_pedido) "
            "SELECT 'nuevo', id_pedido FROM pedido WHERE origen = 'movil' "
            "UNION ALL SELECT 'programado', id_pedido FROM pedido WHERE estado_pedido IN ('programado', 'en camino', 'entregado') "
            "UNION ALL SELECT 'entregado', id_pedido FROM pedido WHERE estado_pedido = 'entregado' "
            "ON CONFLICT DO NOTHING"
        )
        return cur.rowcount


def pedidos_a_revisar(con):
    """Los pedidos que todavía pueden generar avisos: todos menos los ya entregados y avisados. Cada uno trae
    los avisos que ya se registraron (`hechos`)."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT p.id_pedido, p.estado_pedido, p.origen, p.creado_por, p.fecha_entrega, c.nombre, u.nombre, "
            "       COALESCE(array_agg(n.evento) FILTER (WHERE n.evento IS NOT NULL), ARRAY[]::text[]) "
            "FROM pedido p "
            "LEFT JOIN cliente c ON c.id_cliente = p.id_cliente "
            "LEFT JOIN usuario u ON u.username = p.creado_por "
            "LEFT JOIN notificacion_enviada n ON n.id_pedido = p.id_pedido "
            "WHERE NOT EXISTS (SELECT 1 FROM notificacion_enviada e WHERE e.id_pedido = p.id_pedido AND e.evento = 'entregado') "
            "GROUP BY p.id_pedido, p.estado_pedido, p.origen, p.creado_por, p.fecha_entrega, c.nombre, u.nombre "
            "ORDER BY p.id_pedido"
        )
        filas = cur.fetchall()
    return [
        {"id_pedido": f[0], "estado": f[1], "origen": f[2], "creado_por": f[3], "fecha_entrega": f[4],
         "cliente": f[5], "vendedor": f[6], "hechos": set(f[7])}
        for f in filas
    ]


def registrar(con, evento, id_pedido):
    """Anota que ese aviso de ese pedido ya está resuelto (idempotente)."""
    with con.cursor() as cur:
        cur.execute("INSERT INTO notificacion_enviada (evento, id_pedido) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (evento, id_pedido))


def suscripciones(con, roles, usuarios, excluir):
    """Los celulares a los que hay que avisar: los de usuarios ACTIVOS con alguno de esos roles o esos
    usernames, menos los excluidos."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.endpoint, s.p256dh, s.auth FROM push_suscripcion s JOIN usuario u ON u.id = s.usuario_id "
            "WHERE u.activo AND (u.rol = ANY(%s::text[]) OR u.username = ANY(%s::text[])) "
            "AND NOT (u.username = ANY(%s::text[])) ORDER BY s.id",
            (list(roles), list(usuarios), list(excluir)),
        )
        return [{"id": f[0], "endpoint": f[1], "p256dh": f[2], "auth": f[3]} for f in cur.fetchall()]


def borrar_suscripcion(con, id_suscripcion):
    """Quita una suscripción que el servicio de push dio por muerta (el celular la canceló o desinstaló la app)."""
    with con.cursor() as cur:
        cur.execute("DELETE FROM push_suscripcion WHERE id = %s", (id_suscripcion,))
