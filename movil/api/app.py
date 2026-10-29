"""FastAPI de la toma de pedidos desde el celular.

Arrancar:  uvicorn movil.api.app:app --host <ip de tailscale> --port 8000
"""
import hashlib
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import auth as auth_router
from .routers import catalogo as catalogo_router
from .routers import panel as panel_router
from .routers import pedidos as pedidos_router
from .routers import push as push_router
from .routers import reparto as reparto_router

_CARPETA_MOVIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _huella_del_codigo():
    """Resumen del CONTENIDO de los .py de la API (y del cálculo del panel que ella importa).
    No se usan las fechas de los archivos: `robocopy` las conserva, y un archivo copiado hoy puede
    tener fecha de ayer."""
    resumen = hashlib.sha1()
    for carpeta in ("api", "panel"):
        for raiz, subcarpetas, archivos in os.walk(os.path.join(_CARPETA_MOVIL, carpeta)):
            subcarpetas.sort()
            for nombre in sorted(archivos):
                if nombre.endswith(".py"):
                    ruta = os.path.join(raiz, nombre)
                    resumen.update(os.path.relpath(ruta, _CARPETA_MOVIL).encode("utf-8"))
                    with open(ruta, "rb") as f:
                        resumen.update(f.read())
    return resumen.hexdigest()


# El código que ESTE proceso cargó al arrancar. Si después se copian archivos nuevos y no se
# reinicia la tarea, el proceso sigue con el código viejo: /health lo avisa (`reiniciar`).
_HUELLA_AL_ARRANCAR = _huella_del_codigo()

app = FastAPI(title="Mana Móvil API")
app.include_router(auth_router.router)
app.include_router(catalogo_router.router)
app.include_router(pedidos_router.router)
app.include_router(panel_router.router)
app.include_router(reparto_router.router)
app.include_router(push_router.router)


@app.get("/health")
def health():
    """La API y la base por separado: si la base falla no tira abajo el
    servicio, para que se note cuál de las dos es el problema."""
    estado_db = "ok"
    try:
        con = db.conexion()
        con.close()
    except Exception as e:
        estado_db = f"error: {type(e).__name__}"
    try:
        # True = en el disco hay código distinto del que está corriendo: hay que reiniciar la tarea.
        reiniciar = _huella_del_codigo() != _HUELLA_AL_ARRANCAR
    except OSError:
        reiniciar = None   # no se pudo leer la carpeta: no se afirma nada
    return {"api": "ok", "db": estado_db, "reiniciar": reiniciar}


# La PWA (movil/pwa/) se sirve desde la misma app/puerto que la API: un solo
# origen HTTPS por Tailscale, sin CORS. Va al final a propósito: Starlette
# prueba las rutas en orden, así que las de arriba (/auth, /catalogo, /pedidos,
# /reparto, /panel, /push, /health) siempre ganan antes de caer acá.
_PWA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pwa")
app.mount("/", StaticFiles(directory=_PWA_DIR, html=True), name="pwa")
