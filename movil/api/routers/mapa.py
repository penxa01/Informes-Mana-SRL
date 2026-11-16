"""Mapa de la pantalla Pedidos: dónde están los clientes (los que tienen la ubicación cargada) y dónde está el celular
de la cuenta de reparto.

  GET  /mapa/clientes       reparto, admin y superadmin   los clientes con ubicación (nombre, dirección y localidad)
  GET  /mapa/reparto        reparto, admin y superadmin   dónde está el reparto ahora (solo posiciones recientes)
  POST /mapa/mi-ubicacion   SOLO la cuenta de reparto     manda su posición (el celular lo hace solo, con la app abierta)

De la posición del reparto se guarda únicamente la última (se pisa, sin historial) y no se muestra si es vieja
(`db.POSICION_REPARTO_MAX_MINUTOS`). Los admin ven al reparto pero no mandan su propia posición."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps
from ..schemas import ClienteMapa, Confirmacion, PosicionIn, PosicionReparto

router = APIRouter(prefix="/mapa", tags=["mapa"])


@router.get("/clientes", response_model=List[ClienteMapa])
def clientes(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    return db.clientes_con_ubicacion(con)


@router.get("/reparto", response_model=List[PosicionReparto])
def reparto(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    return db.posiciones_reparto(con)


@router.post("/mi-ubicacion", response_model=Confirmacion)
def mi_ubicacion(datos: PosicionIn, usuario: str = Depends(deps.solo_reparto), con=Depends(deps.conexion_actual)):
    if datos.lat == 0 and datos.lng == 0:
        raise HTTPException(status_code=422, detail="La ubicación recibida no es válida")
    try:
        db.guardar_posicion_reparto(con, usuario, datos.lat, datos.lng, datos.precision_m)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return Confirmacion()
