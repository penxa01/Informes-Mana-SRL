"""Proceso que arma el panel de control en el servidor y lo guarda en la base.

Lo corre una tarea programada (deploy/instalar_panel.ps1) y también sirve a mano:

    python -m movil.panel.worker               # queda corriendo, un ciclo cada PANEL_INTERVALO_SEG
    python -m movil.panel.worker --una-vez     # un solo ciclo y termina

En cada ciclo mira los archivos del sistema (tamaño y fecha) y solo vuelve a calcular si cambiaron
o si cambió el día: leer `fachist.DBF` lleva unos segundos y no tiene sentido hacerlo cada vez.
Si un cálculo falla, los datos anteriores quedan como estaban y el error se guarda en la base (la
API lo informa); el ciclo siguiente reintenta.

Usa `movil/.env` como la API (mismo `PEDIDOS_DB_*`). Opcionales del `.env`:
  PANEL_BASE_PATH      carpeta del sistema de gestión (por defecto D:/tiempo)
  PANEL_INTERVALO_SEG  segundos entre ciclos (por defecto 300)
Los logs van a movil/logs/panel.log.
"""
import datetime as dt
import logging
import os
import socket
import sys
import time

from . import almacen, calculo, lectura

log = logging.getLogger("movil.panel")

INTERVALO_POR_DEFECTO = 300


def rutas_desde_entorno(env=None):
    """(carpeta de los DBF, ruta del Excel de clasificación Premium), con la misma estructura
    de carpetas que usa el escritorio (src/controllers/config.py)."""
    env = os.environ if env is None else env
    base = env.get("PANEL_BASE_PATH", "D:/tiempo")
    return (os.path.join(base, "vtiempoges", "GESTION", "MANA2014"),
            os.path.join(base, "Thalamus", "LITROS SHELL.xlsx"))


def conectar():
    import psycopg2

    # Igual que la API: libpq no siempre resuelve el nombre de máquina de Windows.
    return psycopg2.connect(
        host=socket.gethostbyname(os.environ["PEDIDOS_DB_HOST"]), dbname=os.environ["PEDIDOS_DB_NAME"],
        user=os.environ["PEDIDOS_DB_USER"], password=os.environ["PEDIDOS_DB_PASSWORD"], connect_timeout=6,
    )


def ciclo(con, hoy, leer_firma, calcular):
    """Un ciclo. Devuelve 'sin_cambios', 'calculado' o 'error'. Hace commit.

    :param leer_firma: función que devuelve la firma (tamaño y fecha) de los archivos de entrada.
    :param calcular: función que devuelve el panel (dict). Se pasa como parámetro para poder probar
                     el ciclo sin leer los archivos reales.
    """
    try:
        firma = leer_firma()
        estado = almacen.leer_estado(con)
        if (estado and estado["datos"] and not estado["error"]
                and estado["fuentes"] == firma and estado["datos"].get("hoy") == hoy.isoformat()):
            return "sin_cambios"
        datos = calcular()
        if leer_firma() != firma:
            # El sistema de gestión escribió un archivo mientras lo leíamos: el resultado puede estar
            # a medias. No se guarda; el ciclo siguiente lo recalcula con el archivo ya estable.
            raise RuntimeError("los archivos del sistema cambiaron mientras se leían")
    except Exception as e:
        log.exception("No se pudo calcular el panel")
        con.rollback()
        almacen.guardar_error(con, f"{type(e).__name__}: {e}"[:500])
        con.commit()
        return "error"
    almacen.guardar_resultado(con, datos, firma)
    con.commit()
    return "calculado"


def cargar_entorno():
    """Lee movil/.env (o MOVIL_ENV_FILE) y configura los logs. Devuelve el código de salida si falla."""
    from movil import run

    ruta_env = os.environ.get("MOVIL_ENV_FILE") or os.path.join(run.CARPETA_MOVIL, ".env")
    carpeta_logs = os.environ.get("MOVIL_LOG_DIR") or os.path.join(run.CARPETA_MOVIL, "logs")
    try:
        os.environ.update(run.leer_env(ruta_env))
    except (OSError, ValueError) as e:
        run.configurar_logs(carpeta_logs, "panel.log")
        log.critical("No se pudo leer %s: %s", ruta_env, e)
        return 2
    run.configurar_logs(carpeta_logs, "panel.log")
    faltan = [v for v in ("PEDIDOS_DB_HOST", "PEDIDOS_DB_NAME", "PEDIDOS_DB_USER", "PEDIDOS_DB_PASSWORD") if not os.environ.get(v)]
    if faltan:
        log.critical("Faltan variables en %s: %s", ruta_env, ", ".join(faltan))
        return 2
    return None


def main(argv=None):
    una_vez = "--una-vez" in (argv if argv is not None else sys.argv[1:])
    salida = cargar_entorno()
    if salida is not None:
        return salida

    base_dbf, excel = rutas_desde_entorno()
    intervalo = int(os.environ.get("PANEL_INTERVALO_SEG", INTERVALO_POR_DEFECTO))
    log.info("Arrancando el cálculo del panel (archivos en %s, cada %s s)", base_dbf, intervalo)

    while True:
        try:
            hoy = dt.date.today()
            con = conectar()
            try:
                resultado = ciclo(
                    con, hoy,
                    leer_firma=lambda: lectura.firma_de_archivos(base_dbf, excel),
                    calcular=lambda: calculo.calcular_desde_archivos(base_dbf, excel, hoy),
                )
            finally:
                con.close()
            (log.debug if resultado == "sin_cambios" else log.info)("Ciclo: %s", resultado)
        except Exception:
            log.exception("El ciclo falló (¿la base no responde?); se reintenta")
        if una_vez:
            return 0
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
