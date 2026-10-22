"""Detección de entorno: D:/tiempo (local) o Z: (remoto) — src/controllers/entorno.py.

Reglas:
* Se prefiere LOCAL (D:/tiempo); si no está, REMOTO (Z:).
* Un entorno "existe" solo si está la carpeta de DBF (vtiempoges/GESTION/MANA2014),
  no basta con que exista la carpeta base.
* Si LOCAL sirve, NO se toca la red (Z: caído podría colgar el arranque).
* Una unidad sola ("Z:") se normaliza a "Z:/": "Z:vtiempoges" es una ruta relativa
  al directorio actual de la unidad, no a su raíz.

Correr desde la raíz:  python tests/verificar_entorno.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers.entorno import SUBRUTA_DBF, normalizar_base, resolver_entorno, resolver_host_db

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def norm(p):
    return os.path.normcase(os.path.normpath(p))


def falso_disco(*existentes):
    """`existe` simulado: solo true para las rutas dadas. Registra cada consulta."""
    validas = {norm(p) for p in existentes}
    llamadas = []

    def existe(ruta):
        llamadas.append(norm(ruta))
        return norm(ruta) in validas

    existe.llamadas = llamadas
    return existe


CANDIDATOS = [("LOCAL", "d:/tiempo"), ("REMOTO", "Z:")]
DBF_LOCAL = "d:/tiempo/" + SUBRUTA_DBF
DBF_REMOTO = "Z:/" + SUBRUTA_DBF

print("=== normalizar_base ===")
for entrada, esperado in (("Z:", "Z:/"), ("z:", "z:/"), (" Z: ", "Z:/"), ("Z:/", "Z:/"), ("Z:\\", "Z:\\"),
                          ("d:/tiempo", "d:/tiempo"), ("  d:/tiempo ", "d:/tiempo"), ("", "")):
    check(f"{entrada!r} -> {esperado!r}", normalizar_base(entrada) == esperado, repr(normalizar_base(entrada)))

print("=== resolver_entorno ===")
r = resolver_entorno(CANDIDATOS, falso_disco(DBF_LOCAL, DBF_REMOTO))
check("existen los dos -> LOCAL", r[0] == "LOCAL", str(r))

r = resolver_entorno(CANDIDATOS, falso_disco(DBF_REMOTO))
check("sin D:/tiempo -> REMOTO", r[0] == "REMOTO", str(r))
check("la base remota queda como 'Z:/' (no 'Z:')", r[1] == "Z:/", repr(r[1]))

r = resolver_entorno(CANDIDATOS, falso_disco("d:/tiempo", DBF_REMOTO))
check("D:/tiempo existe pero sin la carpeta de DBF -> REMOTO", r[0] == "REMOTO", str(r))

r = resolver_entorno(CANDIDATOS, falso_disco("d:/tiempo", "Z:/"))
check("existen las bases pero ninguna tiene DBF -> ninguno", r == (None, None), str(r))

r = resolver_entorno(CANDIDATOS, falso_disco())
check("no existe nada -> (None, None)", r == (None, None), str(r))

r = resolver_entorno([("REMOTO", "Z:")], falso_disco(DBF_REMOTO))
check("un solo candidato", r == ("REMOTO", "Z:/"), str(r))
check("sin candidatos -> (None, None)", resolver_entorno([], falso_disco()) == (None, None))

print("=== no toca la red si el local sirve ===")
disco = falso_disco(DBF_LOCAL, DBF_REMOTO)
resolver_entorno(CANDIDATOS, disco)
check("solo consultó la ruta local", len(disco.llamadas) == 1 and "d:" in disco.llamadas[0].lower(),
      str(disco.llamadas))

print("=== consulta la carpeta de DBF, no solo la base ===")
disco = falso_disco(DBF_REMOTO)
resolver_entorno(CANDIDATOS, disco)
check("preguntó por vtiempoges/GESTION/MANA2014",
      all(norm(SUBRUTA_DBF) in c for c in disco.llamadas), str(disco.llamadas))

print("=== orden de prioridad configurable ===")
r = resolver_entorno([("REMOTO", "Z:"), ("LOCAL", "d:/tiempo")], falso_disco(DBF_LOCAL, DBF_REMOTO))
check("respeta el orden dado", r[0] == "REMOTO", str(r))

print("=== host de la base de datos (Pedidos / reclamos) ===")
SERVIDOR = "DESKTOP-R8E4V7S"
for equipo, esperado, motivo in (
    ("DESKTOP-R8E4V7S", "localhost", "es el servidor -> su propio Postgres"),
    ("desktop-r8e4v7s", "localhost", "sin distinguir mayúsculas"),
    ("DESKTOP-R8E4V7S.local", "localhost", "nombre con dominio"),
    (" DESKTOP-R8E4V7S ", "localhost", "espacios alrededor"),
    ("Penxita", SERVIDOR, "otra PC (la de desarrollo) -> base del servidor, NO su Postgres de prueba"),
    ("PC-REMOTA", SERVIDOR, "PC remota -> base del servidor"),
    ("DESKTOP-R8E4V7S2", SERVIDOR, "nombre parecido pero distinto"),
    ("", SERVIDOR, "nombre desconocido -> la del servidor"),
):
    r = resolver_host_db(SERVIDOR, equipo)
    check(f"{equipo!r}: {motivo}", r == esperado, repr(r))
check("host local configurable", resolver_host_db(SERVIDOR, "DESKTOP-R8E4V7S", host_local="127.0.0.1") == "127.0.0.1")
check("sin nombre de servidor configurado -> 'localhost'", resolver_host_db("", "Penxita") == "localhost")
check("sin 'nombre_equipo' usa el de esta PC", isinstance(resolver_host_db(SERVIDOR), str))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
