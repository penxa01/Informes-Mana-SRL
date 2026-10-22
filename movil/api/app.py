"""FastAPI de la toma de pedidos desde el celular.

Arrancar:  uvicorn movil.api.app:app --host <ip de tailscale> --port 8000
"""
from fastapi import FastAPI

from . import db

app = FastAPI(title="Mana Móvil API")


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
