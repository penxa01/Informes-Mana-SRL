"""Migración aditiva de la base de Pedidos para la toma de pedidos desde el
celular, y el rol `movil_api` con permisos mínimos para esa API.

No importa nada de `src/` (arrastra PyQt): este módulo vive fuera del `.exe`
y se conecta a la base por su cuenta. Ver `sql/001_movil.sql` (tabla `pedido`)
y `sql/002_reparto.sql` (ubicación del cliente) para el detalle de los cambios.

No hace commit: quien llama decide (el script de despliegue commitea; los
tests revierten).
"""
import os

_SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")
_ARCHIVOS_SQL = ("001_movil.sql", "002_reparto.sql")


def _leer(nombre):
    with open(os.path.join(_SQL_DIR, nombre), encoding="utf-8") as f:
        return f.read()


SQL_MIGRACION = "\n".join(_leer(n) for n in _ARCHIVOS_SQL)


def aplicar(con):
    """Aplica los cambios aditivos (`pedido` y `cliente`), en orden (idempotente)."""
    with con.cursor() as cur:
        cur.execute(SQL_MIGRACION)


def asegurar_rol(con, password):
    """Crea el rol `movil_api` si no existe, le pone la clave y le deja los
    permisos mínimos (idempotente). Ver `asegurar_permisos`."""
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'movil_api'")
        if cur.fetchone() is None:
            cur.execute("CREATE ROLE movil_api LOGIN PASSWORD %s", (password,))
        else:
            cur.execute("ALTER ROLE movil_api PASSWORD %s", (password,))
    asegurar_permisos(con)


def asegurar_permisos(con):
    """Deja a `movil_api` con los permisos mínimos (idempotente; el rol ya tiene
    que existir). Sin permisos de superusuario, `cliente`/`producto` solo de
    lectura, y de `usuario` solo las columnas del login y del control de rol
    (nunca `vendedor_id`).

    Para el reparto puede modificar únicamente lo que cambia una entrega:
    `pedido.estado_pedido`/`fecha_entrega` y `detallepedido.cantidad_entregada`.
    No puede borrar ni cambiar el cliente de un pedido, ni tocar de `cliente` nada que
    no sea su ubicación (`ubicacion_*`). El trigger que cierra el
    pedido cuando todo está entregado corre con estos mismos permisos."""
    with con.cursor() as cur:
        cur.execute("GRANT SELECT ON cliente, producto TO movil_api")
        cur.execute("GRANT SELECT (id, username, password_hash, nombre, rol, activo) ON usuario TO movil_api")
        cur.execute("GRANT SELECT, INSERT ON pedido, detallepedido TO movil_api")
        cur.execute("GRANT UPDATE (estado_pedido, fecha_entrega) ON pedido TO movil_api")
        cur.execute("GRANT UPDATE (cantidad_entregada) ON detallepedido TO movil_api")
        # El reparto puede guardar la ubicación de un cliente (solo esas tres columnas).
        cur.execute("GRANT UPDATE (ubicacion_maps, ubicacion_lat, ubicacion_lng) ON cliente TO movil_api")
        cur.execute("GRANT USAGE ON SEQUENCE pedido_id_pedido_seq, detallepedido_id_detalle_seq TO movil_api")
