"""Proceso del servidor que manda los avisos (push) a los celulares.

Lo corre una tarea programada (deploy/instalar_avisos.ps1) y también sirve a mano:

    python -m movil.avisos.worker               # queda corriendo, un ciclo cada AVISOS_INTERVALO_SEG
    python -m movil.avisos.worker --una-vez     # un solo ciclo y termina
    python -m movil.avisos.worker --sembrar     # además, da por avisado todo lo que ya existe

Los cambios de estado de un pedido los hace la PC (o el reparto) directo en Postgres, y `pedido` no
tiene triggers ni fecha de cambio de estado: por eso este proceso mira la tabla cada pocos segundos y
compara contra lo ya avisado (`notificacion_enviada`). La primera vez que arranca (esa tabla vacía) siembra
lo que ya existe, para no mandar un aviso por cada pedido viejo.

Usa `movil/.env` como la API (mismo `PEDIDOS_DB_*`) y las claves de `movil/vapid.py`
(`MOVIL_VAPID_PRIVADA`, `MOVIL_VAPID_CONTACTO`). Opcional del `.env`:
  AVISOS_INTERVALO_SEG  segundos entre ciclos (por defecto 20)
Los logs van a movil/logs/avisos.log (nunca se escriben las direcciones de los celulares ni las claves).
"""
import logging
import os
import socket
import sys
import time

from . import almacen, envio, reglas

log = logging.getLogger("movil.avisos")

INTERVALO_POR_DEFECTO = 20
MAX_INTENTOS = 5   # si un aviso falla siempre por motivos pasajeros, a la 5ª vez se rinde (para no insistir para siempre)


def conectar():
    import psycopg2

    # Igual que la API: libpq no siempre resuelve el nombre de máquina de Windows.
    return psycopg2.connect(
        host=socket.gethostbyname(os.environ["PEDIDOS_DB_HOST"]), dbname=os.environ["PEDIDOS_DB_NAME"],
        user=os.environ["PEDIDOS_DB_USER"], password=os.environ["PEDIDOS_DB_PASSWORD"], connect_timeout=6,
    )


def _avisar(con, pedido, evento, enviar, intentos, resumen):
    """Manda un aviso a todos sus destinatarios y decide si queda resuelto. No hace commit."""
    roles, usuarios, excluir = reglas.destinatarios(evento, pedido["creado_por"])
    destinos = almacen.suscripciones(con, roles, usuarios, excluir)
    if not destinos:
        # Nadie a quien avisar (todavía nadie activó los avisos): se da por resuelto. Si no, quien active los
        # avisos mañana recibiría de golpe todo lo que pasó antes.
        almacen.registrar(con, evento, pedido["id_pedido"])
        return
    payload = reglas.mensaje(evento, pedido)
    ok = errores = 0
    for destino in destinos:
        resultado = enviar(destino, payload)
        if resultado == "ok":
            ok += 1
        elif resultado == "muerta":
            almacen.borrar_suscripcion(con, destino["id"])
            resumen["bajas"] += 1
        else:
            errores += 1
    clave = (evento, pedido["id_pedido"])
    if ok or not errores:
        almacen.registrar(con, evento, pedido["id_pedido"])
        intentos.pop(clave, None)
        resumen["enviados"] += ok
        log.info("Aviso '%s' del pedido %s: %s enviados, %s fallaron", evento, pedido["id_pedido"], ok, errores)
    else:
        # Todos fallaron por motivos que pueden ser pasajeros (sin internet, servicio caído): se reintenta.
        intentos[clave] = intentos.get(clave, 0) + 1
        resumen["fallidos"] += 1
        if intentos[clave] >= MAX_INTENTOS:
            almacen.registrar(con, evento, pedido["id_pedido"])
            intentos.pop(clave, None)
            log.error("Aviso '%s' del pedido %s: se descarta después de %s intentos fallidos", evento, pedido["id_pedido"], MAX_INTENTOS)
        else:
            log.warning("Aviso '%s' del pedido %s: falló (intento %s de %s), se reintenta", evento, pedido["id_pedido"],
                        intentos[clave], MAX_INTENTOS)


def ciclo(con, enviar, intentos=None):
    """Un ciclo: revisa los pedidos y manda los avisos que corresponden. Hace commit pedido por pedido (así un
    error en uno no deshace los avisos ya enviados de los otros). Devuelve un resumen:
    {enviados, silenciados, bajas, fallidos}.

    :param enviar: `enviar(destino, payload) -> 'ok' | 'muerta' | 'error'` (ver envio.py). Se pasa como
                   parámetro para poder probar el ciclo sin red.
    :param intentos: {(evento, id_pedido): fallos seguidos}, para no insistir para siempre. Si el proceso
                     lo reutiliza entre ciclos, el reintento tiene memoria.
    """
    intentos = {} if intentos is None else intentos
    resumen = {"enviados": 0, "silenciados": 0, "bajas": 0, "fallidos": 0}
    for pedido in almacen.pedidos_a_revisar(con):
        a_enviar, a_silenciar = reglas.decidir(pedido["estado"], pedido["origen"], pedido["hechos"])
        if not (a_enviar or a_silenciar):
            continue
        try:
            for evento in a_silenciar:
                almacen.registrar(con, evento, pedido["id_pedido"])
                resumen["silenciados"] += 1
            for evento in a_enviar:
                _avisar(con, pedido, evento, enviar, intentos, resumen)
            con.commit()
        except Exception:
            log.exception("No se pudo procesar el pedido %s", pedido["id_pedido"])
            con.rollback()
    return resumen


def configuracion(env=None):
    """(clave privada, contacto) de VAPID desde el entorno. Falla con ValueError si falta algo o si el par
    del `.env` no es coherente (con una pública que no corresponde, los servicios de push rechazan todo)."""
    env = os.environ if env is None else env
    privada = (env.get("MOVIL_VAPID_PRIVADA") or "").strip()
    contacto = (env.get("MOVIL_VAPID_CONTACTO") or "").strip()
    publica = (env.get("MOVIL_VAPID_PUBLICA") or "").strip()
    if not privada or not contacto:
        raise ValueError("Faltan MOVIL_VAPID_PRIVADA y/o MOVIL_VAPID_CONTACTO en el .env (se generan con python movil\\vapid.py --contacto mailto:...)")
    from movil import vapid

    if not vapid.contacto_valido(contacto):
        raise ValueError("MOVIL_VAPID_CONTACTO tiene que empezar con mailto: o https://")
    try:
        derivada = vapid.publica_de(privada)   # valida la privada aunque no haya pública con qué compararla
    except Exception:
        raise ValueError("MOVIL_VAPID_PRIVADA no es una clave válida")
    if publica and publica != derivada:
        raise ValueError("MOVIL_VAPID_PUBLICA no corresponde a MOVIL_VAPID_PRIVADA")
    return privada, contacto


def cargar_entorno():
    """Lee movil/.env (o MOVIL_ENV_FILE) y configura los logs. Devuelve el código de salida si falla."""
    from movil import run

    ruta_env = os.environ.get("MOVIL_ENV_FILE") or os.path.join(run.CARPETA_MOVIL, ".env")
    carpeta_logs = os.environ.get("MOVIL_LOG_DIR") or os.path.join(run.CARPETA_MOVIL, "logs")
    try:
        os.environ.update(run.leer_env(ruta_env))
    except (OSError, ValueError) as e:
        run.configurar_logs(carpeta_logs, "avisos.log")
        log.critical("No se pudo leer %s: %s", ruta_env, e)
        return 2
    run.configurar_logs(carpeta_logs, "avisos.log")
    faltan = [v for v in ("PEDIDOS_DB_HOST", "PEDIDOS_DB_NAME", "PEDIDOS_DB_USER", "PEDIDOS_DB_PASSWORD") if not os.environ.get(v)]
    if faltan:
        log.critical("Faltan variables en %s: %s", ruta_env, ", ".join(faltan))
        return 2
    return None


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    una_vez, forzar_siembra = "--una-vez" in args, "--sembrar" in args
    salida = cargar_entorno()
    if salida is not None:
        return salida
    try:
        privada, contacto = configuracion()
    except ValueError as e:
        log.critical("%s", e)
        return 2
    try:
        enviar = envio.crear_emisor(privada, contacto)
    except ImportError as e:
        log.critical("Falta la librería de avisos (pip install -r movil\\requirements-avisos.txt) o no carga: %s", e)
        return 2

    intervalo = int(os.environ.get("AVISOS_INTERVALO_SEG", INTERVALO_POR_DEFECTO))
    log.info("Arrancando los avisos (cada %s s)", intervalo)
    intentos = {}
    primera_vez = True
    while True:
        try:
            con = conectar()
            try:
                if primera_vez:
                    if forzar_siembra or not almacen.hay_registros(con):
                        anotados = almacen.sembrar(con)
                        con.commit()
                        log.info("Siembra inicial: %s avisos dados por hechos (lo que ya existía no se avisa)", anotados)
                    primera_vez = False
                    log.info("Avisos listos")
                resumen = ciclo(con, enviar, intentos)
            finally:
                con.close()
            if any(resumen.values()):
                log.info("Ciclo: %s", resumen)
        except Exception:
            log.exception("El ciclo falló (¿la base no responde o falta aplicar la migración 004?); se reintenta")
        if una_vez:
            return 0
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
