"""Envío de un aviso a un celular, con Web Push (`pywebpush`).

`pywebpush` se importa recién al crear el emisor: este módulo carga aunque la librería no esté instalada
(en la PC de desarrollo `cryptography`, de la que depende, no funciona), y el resto del proceso se puede
probar con un emisor simulado. Cada envío devuelve:
  "ok"      el servicio de push lo aceptó
  "muerta"  el servicio dice que esa suscripción ya no existe (404/410) o su destino no es de confianza:
            hay que borrarla
  "error"   falló por otra causa (sin conexión, servicio caído...): se puede reintentar
"""
import json
import logging

from movil.api import push

log = logging.getLogger("movil.avisos")

TTL_SEG = 24 * 3600       # si el celular está apagado, el servicio de push guarda el aviso hasta 24 horas
TIMEOUT_SEG = 10


def crear_emisor(vapid_privada, vapid_contacto, _libreria=None):
    """Devuelve `enviar(destino, payload) -> 'ok' | 'muerta' | 'error'`. Falla con ImportError si falta pywebpush.
    `_libreria` = (webpush, WebPushException): solo para probar el envío sin la librería real."""
    if _libreria is None:
        from pywebpush import WebPushException, webpush
    else:
        webpush, WebPushException = _libreria

    def enviar(destino, payload):
        # Defensa en profundidad: la API ya valida el destino al suscribir, pero acá es donde el servidor
        # hace el pedido de red, así que se vuelve a comprobar.
        if not push.endpoint_permitido(destino["endpoint"]):
            log.warning("Suscripción %s con un destino que no es de un servicio de push conocido: se descarta", destino["id"])
            return "muerta"
        try:
            webpush(
                subscription_info={"endpoint": destino["endpoint"], "keys": {"p256dh": destino["p256dh"], "auth": destino["auth"]}},
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=vapid_privada,
                vapid_claims={"sub": vapid_contacto},   # un diccionario nuevo cada vez: pywebpush lo modifica
                ttl=TTL_SEG,
                timeout=TIMEOUT_SEG,
            )
            return "ok"
        except WebPushException as e:
            estado = getattr(getattr(e, "response", None), "status_code", None)
            if estado in (404, 410):
                return "muerta"
            log.warning("El servicio de push rechazó un aviso (HTTP %s): %s", estado, str(e)[:200])
            return "error"
        except Exception:
            log.exception("No se pudo enviar un aviso")
            return "error"

    return enviar
