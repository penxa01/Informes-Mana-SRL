"""Ubicación de los clientes desde el celular: el reparto (y los admin) guardan con el GPS del teléfono, estando en
el lugar, la ubicación de un cliente que no la tiene. Para consultarla no hace falta una ruta propia: viaja en la
lista de pedidos (`GET /pedidos/gestion`, ver `routers/gestion.py`).

Roles `reparto`, `admin` y `superadmin` (ver `deps.reparto_actual`)."""
from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps
from ..schemas import UbicacionGuardada, UbicacionIn

router = APIRouter(prefix="/reparto", tags=["ubicacion de clientes"])


@router.post("/clientes/{id_cliente}/ubicacion", response_model=UbicacionGuardada)
def guardar_ubicacion(id_cliente: int, datos: UbicacionIn, _usuario: str = Depends(deps.reparto_actual),
                      con=Depends(deps.conexion_actual)):
    """Guarda la ubicación del cliente con el GPS del reparto (estando en el lugar). Solo
    clientes con un pedido sin entregar o entregado hace poco, y nunca pisa una ubicación ya cargada."""
    if datos.lat == 0 and datos.lng == 0:
        raise HTTPException(status_code=422, detail="La ubicación recibida no es válida")
    try:
        resultado = db.guardar_ubicacion_cliente(con, id_cliente, datos.lat, datos.lng)
        con.commit()
    except Exception:
        con.rollback()
        raise
    if resultado == "sin_entregas":
        raise HTTPException(status_code=404, detail="Ese cliente no tiene pedidos pendientes ni entregados hace poco")
    if resultado == "ya_tiene":
        raise HTTPException(status_code=409, detail="Ese cliente ya tiene una ubicación cargada")
    return UbicacionGuardada(id_cliente=id_cliente, ubicacion_maps=db.enlace_maps(round(datos.lat, 6), round(datos.lng, 6)))
