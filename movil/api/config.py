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

# Ruta de reparto (movil/api/ruteo.py): el servidor que dice cuánto tarda ir de un cliente a otro por las calles
# (con sus sentidos). Por defecto el servidor público de demostración de OSRM, sin clave; si algún día hace falta
# uno propio (sin límites, sin que las coordenadas salgan de la red), se cambia acá sin tocar código.
# MOVIL_OSRM_PAUSA_S es la pausa entre consultas: el público pide una por segundo; uno propio puede ir en 0.
OSRM_URL = os.getenv("MOVIL_OSRM_URL", "https://router.project-osrm.org").strip().rstrip("/")


def _numero(nombre, por_defecto):
    try:
        return max(0.0, float(os.getenv(nombre, "").strip() or por_defecto))
    except ValueError:
        return por_defecto


OSRM_PAUSA_S = _numero("MOVIL_OSRM_PAUSA_S", 1.1)

TOKEN_DIAS_VENCIMIENTO = 7  # la cola offline tiene que sobrevivir un fin de semana
