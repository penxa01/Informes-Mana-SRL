"""FastAPI de la toma de pedidos desde el celular.

Arrancar:  uvicorn movil.api.app:app --host <ip de tailscale> --port 8000
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import auth as auth_router
from .routers import catalogo as catalogo_router
from .routers import pedidos as pedidos_router

app = FastAPI(title="Mana Móvil API")
app.include_router(auth_router.router)
app.include_router(catalogo_router.router)
app.include_router(pedidos_router.router)


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
    return {"api": "ok", "db": estado_db}


# La PWA (movil/pwa/) se sirve desde la misma app/puerto que la API: un solo
# origen HTTPS por Tailscale, sin CORS. Va al final a propósito: Starlette
# prueba las rutas en orden, así que las de arriba (/auth, /catalogo, /pedidos,
# /health) siempre ganan antes de caer acá.
_PWA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pwa")
app.mount("/", StaticFiles(directory=_PWA_DIR, html=True), name="pwa")
