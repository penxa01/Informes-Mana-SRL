"""Lanzador de la API móvil: lo usa la tarea programada de Windows (ver
deploy/instalar_servicio.ps1) y sirve igual para arrancarla a mano:

    python movil/run.py

Lee `movil/.env` y deja esos valores SOLO en este proceso (pisan a las
variables del sistema: así `PEDIDOS_DB_*` no se mezcla con la app de escritorio,
que usa los mismos nombres). Escribe los logs en `movil/logs/api.log`.

Valores opcionales del `.env`: MOVIL_HOST (127.0.0.1), MOVIL_PORT (8000),
MOVIL_LOG_DIR (movil/logs). Por defecto escucha solo en 127.0.0.1: la expone
por HTTPS `tailscale serve`, no hace falta abrirla a la red local.

Se puede apuntar a otro archivo con la variable de entorno MOVIL_ENV_FILE.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

CARPETA_MOVIL = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(CARPETA_MOVIL)
VARIABLES_OBLIGATORIAS = (
    "PEDIDOS_DB_HOST", "PEDIDOS_DB_NAME", "PEDIDOS_DB_USER", "PEDIDOS_DB_PASSWORD", "MOVIL_JWT_SECRET",
)


def leer_env(ruta):
    """Parsea un `.env` simple (CLAVE=valor, # comentarios, comillas opcionales,
    sin comentarios a mitad de línea). `utf-8-sig` tolera el BOM del Bloc de notas."""
    valores = {}
    with open(ruta, encoding="utf-8-sig") as f:
        for numero, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if "=" not in linea:
                raise ValueError(f"{ruta}, línea {numero}: falta el '='")
            clave, _, valor = linea.partition("=")
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            valores[clave.strip()] = valor
    return valores


def configurar_logs(directorio):
    os.makedirs(directorio, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    archivo = RotatingFileHandler(
        os.path.join(directorio, "api.log"), maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    archivo.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(archivo)
    if sys.stderr is not None and sys.stderr.isatty():  # a mano en una consola: también se ve ahí
        consola = logging.StreamHandler()
        consola.setFormatter(formato)
        raiz.addHandler(consola)

    def excepcion_no_atrapada(tipo, valor, tb):
        logging.getLogger("movil").critical("La API se cayó", exc_info=(tipo, valor, tb))

    sys.excepthook = excepcion_no_atrapada


def main():
    ruta_env = os.environ.get("MOVIL_ENV_FILE") or os.path.join(CARPETA_MOVIL, ".env")
    try:
        os.environ.update(leer_env(ruta_env))
    except (OSError, ValueError) as e:
        configurar_logs(os.environ.get("MOVIL_LOG_DIR") or os.path.join(CARPETA_MOVIL, "logs"))
        logging.getLogger("movil").critical("No se pudo leer %s: %s", ruta_env, e)
        return 2

    configurar_logs(os.environ.get("MOVIL_LOG_DIR") or os.path.join(CARPETA_MOVIL, "logs"))
    log = logging.getLogger("movil")

    faltan = [v for v in VARIABLES_OBLIGATORIAS if not os.environ.get(v)]
    if faltan:
        log.critical("Faltan variables en %s: %s", ruta_env, ", ".join(faltan))
        return 2

    host = os.environ.get("MOVIL_HOST", "127.0.0.1")
    puerto = int(os.environ.get("MOVIL_PORT", "8000"))
    log.info("Arrancando la API móvil en %s:%s (config: %s)", host, puerto, ruta_env)

    sys.path.insert(0, RAIZ)
    import uvicorn

    uvicorn.run("movil.api.app:app", host=host, port=puerto, log_config=None, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
