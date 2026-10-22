"""Migración aditiva de la base de Pedidos para la toma de pedidos desde el
celular, y el rol `movil_api` con permisos mínimos para esa API.

No importa nada de `src/` (arrastra PyQt): este módulo vive fuera del `.exe`
y se conecta a la base por su cuenta. Ver `sql/001_movil.sql` para el detalle
de los cambios a la tabla `pedido`.

No hace commit: quien llama decide (el script de despliegue commitea; los
tests revierten).
"""
import os

_SQL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", "001_movil.sql")

with open(_SQL_PATH, encoding="utf-8") as _f:
    SQL_MIGRACION = _f.read()


def aplicar(con):
    """Aplica los cambios aditivos a `pedido` (idempotente)."""
    with con.cursor() as cur:
        cur.execute(SQL_MIGRACION)


def asegurar_rol(con, password):
    """Crea el rol `movil_api` si no existe y le deja los permisos mínimos
    (idempotente). Sin permisos de superusuario ni sobre `Cliente`/`Producto`
    más allá de lectura, y solo puede leer de `usuario` las columnas que
    necesita para el login (nunca `rol` ni `vendedor_id`)."""
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'movil_api'")
        if cur.fetchone() is None:
            cur.execute("CREATE ROLE movil_api LOGIN PASSWORD %s", (password,))
        else:
            cur.execute("ALTER ROLE movil_api PASSWORD %s", (password,))
        cur.execute("GRANT SELECT ON cliente, producto TO movil_api")
        cur.execute("GRANT SELECT (id, username, password_hash, nombre, activo) ON usuario TO movil_api")
        cur.execute("GRANT SELECT, INSERT ON pedido, detallepedido TO movil_api")
        cur.execute("GRANT USAGE ON SEQUENCE pedido_id_pedido_seq, detallepedido_id_detalle_seq TO movil_api")
