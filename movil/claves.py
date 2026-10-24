"""Herramienta de administración: ver los usuarios de la app móvil y asignarles clave.

Las claves se piden por consola SIN mostrarse (nunca van por argumentos ni quedan en el
historial) y se guardan en bcrypt. Necesita un usuario de PostgreSQL que pueda modificar la
tabla `usuario` (el `postgres` del servidor): `movil_api` no puede, a propósito.

    python movil/claves.py --host DESKTOP-R8E4V7S listar
    python movil/claves.py --host DESKTOP-R8E4V7S vendedores      # una clave por cada vendedor
    python movil/claves.py --host DESKTOP-R8E4V7S fijar jose matias

En el servidor, `--host localhost` (es el valor por defecto). La clave de PostgreSQL se toma
de la variable `PEDIDOS_ADMIN_PASSWORD` o se pide por consola.
"""
import argparse
import getpass
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from movil import usuarios  # noqa: E402


def conectar(host, dbname, user, password):
    import psycopg2

    # Igual que en la API: libpq no siempre resuelve el nombre de máquina de Windows.
    return psycopg2.connect(host=socket.gethostbyname(host), dbname=dbname, user=user,
                            password=password, connect_timeout=6)


def pedir_clave_nueva(username, leer_clave, salida):
    """Pide la clave dos veces y valida. Devuelve la clave, o None si se dejó vacía (saltear)."""
    while True:
        clave = leer_clave(f"Clave nueva para {username} (Enter = saltear): ")
        if clave == "":
            return None
        motivo = usuarios.validar_clave(clave, username)
        if motivo:
            salida(f"  {motivo}.")
            continue
        if leer_clave("Repetila: ") != clave:
            salida("  No coinciden, probá de nuevo.")
            continue
        return clave


def mostrar_usuarios(filas, salida):
    salida(f"{'USUARIO':<12}{'NOMBRE':<28}{'ROL':<10}ESTADO")
    for username, nombre, rol, activo in filas:
        salida(f"{username:<12}{(nombre or ''):<28}{rol or '':<10}{'activo' if activo else 'DADO DE BAJA'}")


def asignar(con, username, leer_clave, salida):
    """Pide y guarda la clave de un usuario. Devuelve 'cambiada', 'salteada' o 'no_existe'."""
    existentes = {f[0] for f in usuarios.listar_usuarios(con)}
    if username not in existentes:
        salida(f"No existe el usuario '{username}'.")
        return "no_existe"
    clave = pedir_clave_nueva(username, leer_clave, salida)
    if clave is None:
        salida(f"  {username}: sin cambios.")
        return "salteada"
    usuarios.fijar_clave(con, username, clave)
    salida(f"  {username}: clave actualizada.")
    return "cambiada"


def ejecutar(con, args, leer_clave=getpass.getpass, salida=print):
    """Corre el comando sobre una conexión ya abierta. Hace commit solo si todo salió bien."""
    if args.comando == "listar":
        mostrar_usuarios(usuarios.listar_usuarios(con), salida)
        return 0

    if args.comando == "vendedores":
        nombres = [f[0] for f in usuarios.listar_usuarios(con) if f[2] == "vendedor" and f[3]]
    else:  # fijar
        nombres = args.usuarios
    resultados = [asignar(con, n, leer_clave, salida) for n in nombres]
    if "no_existe" in resultados:
        con.rollback()
        salida("No se guardó nada: corregí el nombre del usuario y volvé a correr el comando.")
        return 1
    con.commit()
    salida(f"Listo: {resultados.count('cambiada')} clave(s) cambiada(s).")
    return 0


def armar_parser():
    p = argparse.ArgumentParser(description="Usuarios y claves de la app móvil de Mana")
    p.add_argument("--host", default=os.environ.get("PEDIDOS_DB_HOST", "localhost"), help="servidor de la base")
    p.add_argument("--db", default="pedidosMana", help="nombre de la base")
    p.add_argument("--admin", default="postgres", help="usuario de PostgreSQL con permiso para modificar `usuario`")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("listar", help="muestra los usuarios, su rol y si están activos")
    sub.add_parser("vendedores", help="pide una clave nueva para cada vendedor activo (Enter = saltear)")
    f = sub.add_parser("fijar", help="pide una clave nueva para los usuarios indicados")
    f.add_argument("usuarios", nargs="+")
    return p


def main(argv=None):
    args = armar_parser().parse_args(argv)
    clave_db = os.environ.get("PEDIDOS_ADMIN_PASSWORD") or getpass.getpass(f"Clave de PostgreSQL ({args.admin}): ")
    try:
        con = conectar(args.host, args.db, args.admin, clave_db)
    except Exception as e:
        print(f"No se pudo conectar a {args.host}: {type(e).__name__} {str(e)[:100]}")
        return 1
    try:
        return ejecutar(con, args)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
