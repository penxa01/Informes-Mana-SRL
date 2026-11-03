"""Reglas de los avisos (movil/avisos/reglas.py): qué se avisa según el estado del pedido, a quién y con
qué texto, y la configuración del proceso notificador. Sin base ni red.

Correr desde la raíz:  python movil/tests/verificar_avisos_reglas.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from movil import vapid
from movil.avisos import reglas, worker

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=== qué se avisa según el estado del pedido ===")
d = reglas.decidir
check("pedido nuevo del celular, pendiente -> avisa 'nuevo'", d("pendiente", "movil", set()) == (["nuevo"], []))
check("pedido de la PC, pendiente -> no hay aviso (los vendedores son los que avisan)", d("pendiente", "pc", set()) == ([], []))
check("programado -> avisa 'programado'", d("programado", "pc", set()) == (["programado"], []))
check("entregado, con lo anterior ya avisado -> avisa solo 'entregado'", d("entregado", "pc", {"programado"}) == (["entregado"], [])
      and d("entregado", "movil", {"nuevo", "programado"}) == (["entregado"], []))
check("ya avisado no se repite", d("pendiente", "movil", {"nuevo"}) == ([], []) and d("programado", "pc", {"programado"}) == ([], [])
      and d("entregado", "movil", {"nuevo", "programado", "entregado"}) == ([], []))
check("un pedido del celular que ya está programado y nunca se avisó como nuevo: avisa lo de AHORA y silencia lo viejo",
      d("programado", "movil", set()) == (["programado"], ["nuevo"]))
check("uno que pasó directo a entregado: solo avisa la entrega, silencia lo anterior",
      d("entregado", "movil", set()) == (["entregado"], ["nuevo", "programado"])
      and d("entregado", "pc", set()) == (["entregado"], ["programado"]))
check("'en camino' (entrega parcial) ya pasó por programado: no avisa nada y silencia lo anterior",
      d("en camino", "pc", set()) == ([], ["programado"]) and d("en camino", "pc", {"programado"}) == ([], []))
check("un estado desconocido no genera nada (ni silencia)", d("cancelado", "movil", set()) == ([], []) and d(None, "movil", set()) == ([], []))
check("el estado se compara sin mayúsculas ni espacios", d(" Programado ", "pc", set()) == (["programado"], []))

print("=== a quién ===")
check("nuevo -> admin y superadmin, y no a quien lo cargó", reglas.destinatarios("nuevo", "jose") == (["admin", "superadmin"], [], ["jose"]))
check("nuevo cargado por la PC (sin creador) -> nadie se excluye", reglas.destinatarios("nuevo", None) == (["admin", "superadmin"], [], []))
check("programado -> reparto", reglas.destinatarios("programado", "jose") == (["reparto"], [], []))
check("entregado -> admin, superadmin y el vendedor que lo cargó", reglas.destinatarios("entregado", "jose") == (["admin", "superadmin"], ["jose"], []))
check("entregado de un pedido de la PC -> solo admin y superadmin", reglas.destinatarios("entregado", None) == (["admin", "superadmin"], [], []))
try:
    reglas.destinatarios("inventado", None)
    check("un aviso desconocido da error", False)
except ValueError:
    check("un aviso desconocido da error", True)

print("=== el texto ===")
pedido = {"id_pedido": 42, "cliente": "DISTRIBUIDORA LOS ANDES S.R.L.", "vendedor": "Jose Banco", "creado_por": "jose",
          "fecha_entrega": dt.date(2026, 11, 3)}
m = reglas.mensaje("nuevo", pedido)
check("nuevo: dice el cliente y quién lo cargó", (m["titulo"], m["cuerpo"]) == ("Pedido nuevo", "DISTRIBUIDORA LOS ANDES S.R.L. · cargado por Jose Banco"), m)
m = reglas.mensaje("programado", pedido)
check("programado: dice la fecha de entrega", (m["titulo"], m["cuerpo"]) == ("Pedido programado", "DISTRIBUIDORA LOS ANDES S.R.L. · entrega el 3/11"), m)
check("programado sin fecha: lo dice", "sin fecha" in reglas.mensaje("programado", {**pedido, "fecha_entrega": None})["cuerpo"])
m = reglas.mensaje("entregado", pedido)
check("entregado: el cliente", (m["titulo"], m["cuerpo"]) == ("Pedido entregado", "DISTRIBUIDORA LOS ANDES S.R.L."), m)
check("trae el aviso y el pedido, para que la app sepa a dónde ir al tocarlo",
      (m["evento"], m["id_pedido"], m["etiqueta"]) == ("entregado", 42, "pedido-42-entregado"), m)
check("sin nombre de vendedor usa el usuario", "cargado por jose" in reglas.mensaje("nuevo", {**pedido, "vendedor": None})["cuerpo"])
check("un cliente sin nombre no rompe", reglas.mensaje("entregado", {**pedido, "cliente": None})["cuerpo"] == "Cliente sin nombre")
largo = reglas.mensaje("entregado", {**pedido, "cliente": "X" * 300})["cuerpo"]
check("un nombre larguísimo se corta", len(largo) <= 40, len(largo))

print("=== configuración del proceso (claves VAPID del .env) ===")
publica, privada = vapid.generar()
otra_publica, _ = vapid.generar()
ok = {"MOVIL_VAPID_PRIVADA": privada, "MOVIL_VAPID_PUBLICA": publica, "MOVIL_VAPID_CONTACTO": "mailto:avisos@ejemplo.com"}


def falla(env):
    try:
        worker.configuracion(env)
        return False
    except ValueError:
        return True


check("un .env completo y coherente anda", worker.configuracion(ok) == (privada, "mailto:avisos@ejemplo.com"))
check("la pública es opcional para el proceso", worker.configuracion({k: v for k, v in ok.items() if k != "MOVIL_VAPID_PUBLICA"}) == (privada, "mailto:avisos@ejemplo.com"))
check("sin la privada o sin el contacto: error", falla({**ok, "MOVIL_VAPID_PRIVADA": ""}) and falla({**ok, "MOVIL_VAPID_CONTACTO": ""}) and falla({}))
check("una pública que no es la de esa privada: error (los servicios de push rechazarían todo)", falla({**ok, "MOVIL_VAPID_PUBLICA": otra_publica}))
check("contacto que no es mailto: ni https://: error", falla({**ok, "MOVIL_VAPID_CONTACTO": "avisos@ejemplo.com"}))
check("una privada que no es una clave: error", falla({**ok, "MOVIL_VAPID_PRIVADA": "no-es-una-clave", "MOVIL_VAPID_PUBLICA": ""}))

print("=== envío (con pywebpush simulado: acá no hay red ni la librería) ===")
import importlib.util
import json
import logging

from movil.avisos import envio

logging.disable(logging.CRITICAL)


class _ExcepcionPush(Exception):
    def __init__(self, estado):
        super().__init__(f"HTTP {estado}")
        self.response = type("Respuesta", (), {"status_code": estado})() if estado else None


llamadas = []
comportamiento = {"error": None}


def _webpush(**kwargs):
    llamadas.append(kwargs)
    if comportamiento["error"] is not None:
        raise comportamiento["error"]


enviar = envio.crear_emisor("privada", "mailto:avisos@ejemplo.com", (_webpush, _ExcepcionPush))
destino = {"id": 7, "endpoint": "https://fcm.googleapis.com/fcm/send/abc", "p256dh": "k", "auth": "a"}
payload = {"evento": "nuevo", "id_pedido": 1, "titulo": "Pedido nuevo", "cuerpo": "Cliente · cargado por Ñandú"}
check("un envío aceptado -> ok", enviar(destino, payload) == "ok")
llamada = llamadas[-1]
check("le pasa a la librería el destino, las claves y el contenido en JSON (con acentos sin escapar)",
      llamada["subscription_info"] == {"endpoint": destino["endpoint"], "keys": {"p256dh": "k", "auth": "a"}}
      and json.loads(llamada["data"]) == payload and "Ñandú" in llamada["data"], llamada)
check("firma con la clave VAPID y el contacto, y el aviso dura 24 horas si el celular está apagado",
      llamada["vapid_private_key"] == "privada" and llamada["vapid_claims"] == {"sub": "mailto:avisos@ejemplo.com"} and llamada["ttl"] == 86400)
enviar(destino, payload)
check("cada envío usa un diccionario de claims nuevo (la librería lo modifica)", llamadas[-1]["vapid_claims"] is not llamadas[-2]["vapid_claims"])
for estado, esperado in ((404, "muerta"), (410, "muerta"), (400, "error"), (429, "error"), (500, "error"), (None, "error")):
    comportamiento["error"] = _ExcepcionPush(estado)
    check(f"el servicio de push responde {estado} -> {esperado}", enviar(destino, payload) == esperado)
comportamiento["error"] = ConnectionError("sin internet")
check("sin internet u otro fallo -> error (se reintenta), sin romper el ciclo", enviar(destino, payload) == "error")
comportamiento["error"] = None
n = len(llamadas)
check("un destino que no es de un servicio de push conocido no se llama nunca -> muerta (se borra)",
      enviar({**destino, "endpoint": "https://127.0.0.1/algo"}, payload) == "muerta" and len(llamadas) == n)
if importlib.util.find_spec("pywebpush") is None:
    try:
        envio.crear_emisor("privada", "mailto:a@b.com")
        check("sin la librería instalada, crear el emisor falla con ImportError (el proceso lo avisa y no arranca)", False)
    except ImportError:
        check("sin la librería instalada, crear el emisor falla con ImportError (el proceso lo avisa y no arranca)", True)
else:
    print("  OMITIDO  la comprobación de 'falta pywebpush' (acá sí está instalada)")

print("=== arranque del proceso ===")
import tempfile

env_anterior = dict(os.environ)
try:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOVIL_LOG_DIR"] = tmp
        for v in ("PEDIDOS_DB_HOST", "PEDIDOS_DB_NAME", "PEDIDOS_DB_USER", "PEDIDOS_DB_PASSWORD"):
            os.environ.pop(v, None)
        env_malo = os.path.join(tmp, "malo.env")
        with open(env_malo, "w", encoding="utf-8") as f:
            f.write("PEDIDOS_DB_HOST=localhost\n")
        os.environ["MOVIL_ENV_FILE"] = env_malo
        check("un .env al que le faltan variables -> código 2 (la tarea no arranca a ciegas)", worker.cargar_entorno() == 2)
        os.environ["MOVIL_ENV_FILE"] = os.path.join(tmp, "no_existe.env")
        check("un .env que no existe -> código 2", worker.cargar_entorno() == 2)
        env_bueno = os.path.join(tmp, "bueno.env")
        with open(env_bueno, "w", encoding="utf-8") as f:
            f.write("PEDIDOS_DB_HOST=h\nPEDIDOS_DB_NAME=n\nPEDIDOS_DB_USER=u\nPEDIDOS_DB_PASSWORD=p\n")
        os.environ["MOVIL_ENV_FILE"] = env_bueno
        check("un .env completo -> sigue (None) y deja el log en avisos.log", worker.cargar_entorno() is None
              and os.path.exists(os.path.join(tmp, "avisos.log")))
        check("sin claves VAPID en el .env el proceso no arranca (código 2)", worker.main(["--una-vez"]) == 2)
        for h in list(logging.getLogger().handlers):   # suelta el archivo para poder borrar la carpeta temporal
            h.close()
            logging.getLogger().removeHandler(h)
finally:
    os.environ.clear()
    os.environ.update(env_anterior)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
