"""Herramienta de claves (movil/claves.py) contra la base real, dentro de una transacción que
siempre se revierte. Las claves se "tipean" con una función falsa; la prueba no usa getpass.
Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_claves.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import bcrypt

from movil import claves, usuarios

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=== validar_clave ===")
check("clave corta -> rechazada", usuarios.validar_clave("corta1", "jose") is not None)
check("igual al usuario -> rechazada", usuarios.validar_clave("josejose", "josejose") is not None)
check("con espacios en los bordes -> rechazada", usuarios.validar_clave(" unaclave123", "jose") is not None)
check("más de 72 bytes -> rechazada (bcrypt la cortaría)", usuarios.validar_clave("a" * 73, "jose") is not None)
check("una clave razonable -> ok", usuarios.validar_clave("Camión-Azul-42", "jose") is None)

print("=== herramienta contra la base real (transacción que se revierte) ===")
try:
    from src.Views.Pedidos.programarPedido import _conexion
    real = _conexion()
except Exception as e:
    real = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")


class _Proxy:
    """commit() no hace nada; rollback() sí (la herramienta lo usa si algo sale mal)."""
    def __init__(self, real):
        self._real = real

    def commit(self):
        pass

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def guion(*respuestas):
    """Función que reemplaza a getpass: devuelve las respuestas en orden y anota lo que se pidió."""
    cola, pedidos = list(respuestas), []

    def leer(prompt):
        pedidos.append(prompt)
        return cola.pop(0)
    leer.pedidos = pedidos
    return leer


def guion_por_usuario(claves_por_usuario):
    """Como `guion`, pero contesta según a quién se le pide la clave (en la base real hay otros
    vendedores y el orden no es asunto de la prueba): los que no figuran la saltean con Enter."""
    estado, pedidos = {"actual": None}, []

    def leer(prompt):
        pedidos.append(prompt)
        if prompt.startswith("Clave nueva para"):
            estado["actual"] = prompt.split()[3]
            return claves_por_usuario.get(estado["actual"], "")
        return claves_por_usuario[estado["actual"]]   # "Repetila:"
    leer.pedidos = pedidos
    return leer


if real is not None:
    real.autocommit = False
    con = _Proxy(real)
    cur = real.cursor()
    try:
        cur.execute("INSERT INTO usuario (username, password_hash, nombre, rol, activo) VALUES "
                    "('vend_a_tmp', 'x', 'Vendedor A', 'vendedor', true), ('vend_b_tmp', 'x', 'Vendedor B', 'vendedor', true), "
                    "('vend_baja_tmp', 'x', 'Vendedor de baja', 'vendedor', false)")

        def hash_de(u):
            cur.execute("SELECT password_hash FROM usuario WHERE username = %s", (u,))
            return cur.fetchone()[0]

        def ns(**kw):
            return argparse.Namespace(**kw)

        salida = []
        claves.ejecutar(con, ns(comando="listar"), salida=salida.append)
        texto = "\n".join(salida)
        check("listar muestra usuarios, rol y estado", "reparto" in texto and "vend_baja_tmp" in texto and "DADO DE BAJA" in texto)
        check("listar no muestra hashes", "$2b$" not in texto and "password" not in texto.lower())

        print("  -- fijar --")
        salida.clear()
        leer = guion("corta", "Camión-Azul-42", "otra-distinta", "Camión-Azul-42", "Camión-Azul-42")
        codigo = claves.ejecutar(con, ns(comando="fijar", usuarios=["vend_a_tmp"]), leer_clave=leer, salida=salida.append)
        check("termina bien", codigo == 0)
        check("clave corta rechazada y se vuelve a pedir", any("al menos" in s for s in salida))
        check("si no coinciden se vuelve a pedir", any("No coinciden" in s for s in salida))
        h = hash_de("vend_a_tmp")
        check("queda en bcrypt y verifica", bcrypt.checkpw("Camión-Azul-42".encode(), h.encode()))
        check("la clave nunca se imprime", not any("Camión" in s for s in salida))
        check("no se tocó la de otro vendedor", hash_de("vend_b_tmp") == "x")
        cur.execute("SELECT rol, activo FROM usuario WHERE username = 'vend_a_tmp'")
        check("rol y estado intactos", cur.fetchone() == ("vendedor", True))

        print("  -- vendedores (uno por uno) --")
        salida.clear()
        leer = guion_por_usuario({"vend_b_tmp": "Segunda-Clave-77"})   # a los demás, Enter = saltear
        claves.ejecutar(con, ns(comando="vendedores"), leer_clave=leer, salida=salida.append)
        preguntados = [p for p in leer.pedidos if p.startswith("Clave nueva para")]
        check("pregunta solo por vendedores activos (no por el dado de baja, el admin ni reparto)",
              not any("vend_baja_tmp" in p or "admin" in p or "reparto" in p for p in preguntados), preguntados)
        check("pregunta por todos los vendedores activos", any("vend_a_tmp" in p for p in preguntados)
              and any("vend_b_tmp" in p for p in preguntados))
        check("Enter saltea sin cambiar nada", hash_de("vend_a_tmp") == h)
        check("la segunda queda cambiada", hash_de("vend_b_tmp") != "x")

        print("  -- rol y crear --")
        salida.clear()
        codigo = claves.ejecutar(con, ns(comando="rol", usuario="vend_a_tmp", rol="admin"), salida=salida.append)
        cur.execute("SELECT rol FROM usuario WHERE username = 'vend_a_tmp'")
        check("rol: cambia el rol y avisa que hay que volver a entrar", codigo == 0 and cur.fetchone()[0] == "admin" and any("volver a entrar" in s for s in salida))
        codigo = claves.ejecutar(con, ns(comando="rol", usuario="no_existe_zzz", rol="admin"), salida=salida.append)
        check("rol: usuario inexistente -> error", codigo == 1)

        # (el error anterior hizo rollback de TODO lo de esta prueba: se vuelve a armar lo mínimo)
        cur.execute("INSERT INTO usuario (username, password_hash, nombre, rol, activo) VALUES ('vend_a_tmp', 'x', 'Vendedor A', 'vendedor', true)")
        salida.clear()
        leer = guion("Clave-De-Juan-1", "Clave-De-Juan-1")
        codigo = claves.ejecutar(con, ns(comando="crear", usuario="super_prueba_tmp", nombre="Juan", rol="superadmin"), leer_clave=leer, salida=salida.append)
        cur.execute("SELECT rol, nombre, activo, vendedor_id FROM usuario WHERE username = 'super_prueba_tmp'")
        check("crear: deja el usuario con rol, nombre y activo", codigo == 0 and cur.fetchone() == ("superadmin", "Juan", True, None))
        check("crear: la clave queda en bcrypt", bcrypt.checkpw(b"Clave-De-Juan-1", hash_de("super_prueba_tmp").encode()))
        check("crear: la clave nunca se imprime", not any("Clave-De-Juan" in s for s in salida))
        codigo = claves.ejecutar(con, ns(comando="crear", usuario="super_prueba_tmp", nombre="Otro", rol="admin"), leer_clave=guion("x"), salida=salida.append)
        check("crear: si ya existe no lo toca", codigo == 1 and hash_de("super_prueba_tmp") != "x")
        codigo = claves.ejecutar(con, ns(comando="crear", usuario="otro_tmp", nombre="O", rol="admin"), leer_clave=guion(""), salida=salida.append)
        check("crear: sin clave no crea nada", codigo == 1)

        print("  -- usuario inexistente: no guarda nada --")
        salida.clear()
        cur.execute("INSERT INTO usuario (username, password_hash, nombre, rol, activo) VALUES "
                    "('vend_b_tmp', 'x', 'Vendedor B', 'vendedor', true)")
        leer = guion("Tercera-Clave-88", "Tercera-Clave-88")
        codigo = claves.ejecutar(con, ns(comando="fijar", usuarios=["vend_b_tmp", "no_existe_zzz"]), leer_clave=leer, salida=salida.append)
        check("devuelve error y avisa", codigo == 1 and any("No existe" in s for s in salida))
    finally:
        real.rollback()
        cur = real.cursor()
        cur.execute("SELECT count(*) FROM usuario WHERE username LIKE '%\_tmp'")
        check("rollback: ningún usuario de prueba quedó", cur.fetchone()[0] == 0)
        real.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
