"""Aplica en la base los cambios de `movil/sql/` y deja los permisos de `movil_api` (idempotente: se puede
correr cuantas veces haga falta). Hay que correrlo cada vez que aparece un archivo nuevo en `movil\\sql\\`.

    python movil/migrar.py --host DESKTOP-R8E4V7S --solo-verificar     # muestra qué falta, no cambia nada
    python movil/migrar.py --host DESKTOP-R8E4V7S                      # aplica lo que falta

En el servidor, `--host localhost` (es el valor por defecto). Necesita el `postgres` del servidor (crea tablas y
da permisos: `movil_api` no puede, a propósito). La clave de PostgreSQL se toma de la variable
`PEDIDOS_ADMIN_PASSWORD` o se pide por consola, sin mostrarse. Si algo falla no queda nada a medias: es una sola
transacción.
"""
import argparse
import getpass
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from movil import migraciones  # noqa: E402

# Lo que tiene que existir cuando todas las migraciones están aplicadas: (descripción, consulta que devuelve una fila si está).
_REVISIONES = (
    ("pedido.origen y pedido.uuid_cliente (001, pedidos del celular)",
     "SELECT 1 WHERE (SELECT count(*) FROM information_schema.columns WHERE table_name = 'pedido' AND column_name IN ('origen', 'uuid_cliente')) = 2"),
    ("cliente.ubicacion_maps/lat/lng (002, reparto)",
     "SELECT 1 WHERE (SELECT count(*) FROM information_schema.columns WHERE table_name = 'cliente' "
     "AND column_name IN ('ubicacion_maps', 'ubicacion_lat', 'ubicacion_lng')) = 3"),
    ("tabla panel_resumen (003, panel de control)", "SELECT 1 FROM information_schema.tables WHERE table_name = 'panel_resumen'"),
    ("tablas push_suscripcion y notificacion_enviada (004, avisos)",
     "SELECT 1 WHERE (SELECT count(*) FROM information_schema.tables WHERE table_name IN ('push_suscripcion', 'notificacion_enviada')) = 2"),
    ("rol movil_api", "SELECT 1 FROM pg_roles WHERE rolname = 'movil_api'"),
)


def conectar(host, dbname, user, password):
    import psycopg2

    # Igual que en la API: libpq no siempre resuelve el nombre de máquina de Windows.
    return psycopg2.connect(host=socket.gethostbyname(host), dbname=dbname, user=user,
                            password=password, connect_timeout=6)


def faltantes(con):
    """Descripción de lo que todavía no está en la base (lista vacía = todo aplicado)."""
    falta = []
    with con.cursor() as cur:
        for descripcion, consulta in _REVISIONES:
            cur.execute(consulta)
            if cur.fetchone() is None:
                falta.append(descripcion)
    return falta


def ejecutar(con, solo_verificar, salida=print):
    """Verifica o aplica. Devuelve 0 si la base quedó al día; con `solo_verificar`, 1 si falta algo.
    Hace commit solo si todo salió bien."""
    falta = faltantes(con)
    if solo_verificar:
        if falta:
            salida("Falta aplicar:")
            for f in falta:
                salida(f"  - {f}")
            return 1
        salida("La base está al día: no falta aplicar nada.")
        return 0

    if not falta:
        salida("Ya estaba todo aplicado; se repasan los permisos igual (es idempotente).")
    else:
        salida("Se aplica:")
        for f in falta:
            salida(f"  - {f}")
    try:
        migraciones.aplicar(con)
        migraciones.asegurar_permisos(con)
        pendiente = faltantes(con)
        if pendiente:
            con.rollback()
            salida("No se guardó nada: después de aplicar seguía faltando " + "; ".join(pendiente))
            return 1
        con.commit()
    except Exception as e:
        con.rollback()
        salida(f"No se guardó nada: {type(e).__name__}: {str(e)[:200]}")
        return 1
    salida("Listo: la base está al día y los permisos de movil_api quedaron al día.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Aplica las migraciones de la app móvil de Mana")
    p.add_argument("--host", default=os.environ.get("PEDIDOS_DB_HOST", "localhost"), help="servidor de la base")
    p.add_argument("--db", default="pedidosMana", help="nombre de la base")
    p.add_argument("--admin", default="postgres", help="usuario de PostgreSQL con permiso para crear tablas")
    p.add_argument("--solo-verificar", action="store_true", help="muestra qué falta, sin cambiar nada")
    args = p.parse_args(argv)

    clave_db = os.environ.get("PEDIDOS_ADMIN_PASSWORD") or getpass.getpass(f"Clave de PostgreSQL ({args.admin}): ")
    try:
        con = conectar(args.host, args.db, args.admin, clave_db)
    except Exception as e:
        print(f"No se pudo conectar a {args.host}: {type(e).__name__} {str(e)[:100]}")
        return 1
    try:
        return ejecutar(con, args.solo_verificar)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
