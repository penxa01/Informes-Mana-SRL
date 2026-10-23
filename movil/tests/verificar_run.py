"""Lanzador `movil/run.py`: parseo del .env, errores de configuración y un
arranque real (en un puerto libre, con valores falsos: no toca la base real).

Correr desde la raíz:  python movil/tests/verificar_run.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from movil import run

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def escribir(ruta, texto, encoding="utf-8"):
    with open(ruta, "w", encoding=encoding) as f:
        f.write(texto)


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


tmp = tempfile.mkdtemp(prefix="verificar_run_")

print("=== leer_env ===")
ruta = os.path.join(tmp, "a.env")
escribir(ruta, '# comentario\n\nA=1\n B = dos \nC="con espacios"\nD=\'simple\'\nE=a=b\nF=\n')
v = run.leer_env(ruta)
check("clave simple", v["A"] == "1")
check("espacios alrededor de clave y valor", v["B"] == "dos")
check("comillas dobles se sacan", v["C"] == "con espacios")
check("comillas simples se sacan", v["D"] == "simple")
check("el valor puede tener '='", v["E"] == "a=b")
check("valor vacío", v["F"] == "")
check("comentarios y líneas vacías se ignoran", set(v) == {"A", "B", "C", "D", "E", "F"}, sorted(v))

escribir(ruta, "X=1\n", encoding="utf-8-sig")
check("tolera el BOM del Bloc de notas", run.leer_env(ruta) == {"X": "1"})

escribir(ruta, "esto no es una asignacion\n")
try:
    run.leer_env(ruta)
    check("línea sin '=' da error claro", False)
except ValueError as e:
    check("línea sin '=' da error claro (con número de línea)", "línea 1" in str(e), str(e))

print("=== errores de configuración: sale con código 2 y lo deja en el log ===")


def lanzar(env_extra, timeout=20):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith(("PEDIDOS_DB_", "MOVIL_"))}
    entorno.update(env_extra)
    return subprocess.Popen(
        [sys.executable, os.path.join(RAIZ, "movil", "run.py")],
        cwd=tmp, env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def leer_log(directorio):
    try:
        with open(os.path.join(directorio, "api.log"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


logs1 = os.path.join(tmp, "logs1")
p = lanzar({"MOVIL_ENV_FILE": os.path.join(tmp, "no_existe.env"), "MOVIL_LOG_DIR": logs1})
check("sin archivo .env: código de salida 2", p.wait(timeout=20) == 2)
check("sin archivo .env: queda en el log", "No se pudo leer" in leer_log(logs1))

logs2 = os.path.join(tmp, "logs2")
incompleto = os.path.join(tmp, "incompleto.env")
escribir(incompleto, "PEDIDOS_DB_HOST=x\nPEDIDOS_DB_NAME=y\n")
p = lanzar({"MOVIL_ENV_FILE": incompleto, "MOVIL_LOG_DIR": logs2})
check("faltan variables: código de salida 2", p.wait(timeout=20) == 2)
log2 = leer_log(logs2)
check("faltan variables: el log dice cuáles", "PEDIDOS_DB_USER" in log2 and "MOVIL_JWT_SECRET" in log2, log2[-200:])

print("=== arranque real (puerto libre, valores falsos) ===")
puerto = puerto_libre()
logs3 = os.path.join(tmp, "logs3")
completo = os.path.join(tmp, "completo.env")
escribir(
    completo,
    "PEDIDOS_DB_HOST=localhost\nPEDIDOS_DB_NAME=no_existe\nPEDIDOS_DB_USER=movil_api\n"
    f"PEDIDOS_DB_PASSWORD=x\nMOVIL_JWT_SECRET=secreto-de-prueba\nMOVIL_PORT={puerto}\nMOVIL_LOG_DIR={logs3}\n",
)
p = lanzar({"MOVIL_ENV_FILE": completo})
try:
    respuesta = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/health", timeout=2) as r:
                respuesta = json.loads(r.read())
            break
        except OSError:
            time.sleep(0.5)
    check("arranca y responde /health", respuesta is not None and respuesta.get("api") == "ok", respuesta)

    with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=5) as r:
        check("sirve la PWA en /", r.status == 200 and b"Mana Pedidos" in r.read())

    ip_lan = socket.gethostbyname(socket.gethostname())
    if not ip_lan.startswith("127."):
        try:
            socket.create_connection((ip_lan, puerto), timeout=2).close()
            escucha_lan = True
        except OSError:
            escucha_lan = False
        check(f"por defecto NO escucha en la red local ({ip_lan})", not escucha_lan)
    else:
        print("  OMITIDO  no hay IP de red local para comprobar que no escucha afuera")
finally:
    p.terminate()
    p.wait(timeout=10)

log3 = leer_log(logs3)
check("el log registra el arranque", "Arrancando la API móvil" in log3, log3[:120])
check("el log registra los pedidos HTTP (access log)", "GET /health" in log3, log3[-200:])

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
