"""Configuración de la API móvil: se lee de variables de entorno (o de un
`.env` cargado antes de arrancar). No importa nada de `src/` (arrastra PyQt).

A diferencia de la PC (`programarPedido.py`), esta API queda expuesta a la
red de Tailscale: no hay valores por defecto para credenciales ni para el
secreto del token. Si falta algo, falla al arrancar en vez de arrancar insegura.
"""
import os


def _requerida(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (ver movil/env.example)")
    return valor


DB_HOST = _requerida("PEDIDOS_DB_HOST")
DB_NAME = _requerida("PEDIDOS_DB_NAME")
DB_USER = _requerida("PEDIDOS_DB_USER")
DB_PASSWORD = _requerida("PEDIDOS_DB_PASSWORD")

JWT_SECRET = _requerida("MOVIL_JWT_SECRET")

# Avisos (push): clave PÚBLICA de VAPID, la que el navegador necesita para suscribirse. Es opcional: sin
# ella la API arranca igual y simplemente no ofrece avisos (la privada la usa solo el proceso notificador).
# Se genera con `python movil/vapid.py`.
VAPID_PUBLICA = os.getenv("MOVIL_VAPID_PUBLICA", "").strip()
TOKEN_DIAS_VENCIMIENTO = 7  # la cola offline tiene que sobrevivir un fin de semana
