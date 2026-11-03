"""Rutas del perfil de reparto: ver los pedidos programados, marcarlos como entregados y
guardar la ubicación de un cliente con el GPS del celular.

Solo los roles `reparto`, `admin` y `superadmin` (ver `deps.reparto_actual`). Ve dirección, teléfono y ubicación del
cliente, pero únicamente de los pedidos de su lista (programados y en camino; el reparto, solo los de hoy y los
atrasados)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps
from ..schemas import EntregaResultado, PedidoReparto, UbicacionGuardada, UbicacionIn

router = APIRouter(prefix="/reparto", tags=["reparto"])


@router.get("/pedidos", response_model=List[PedidoReparto])
def listar_pedidos(usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    """El perfil de reparto ve solo lo que se entrega hoy o quedó atrasado (no lo programado para otro
    día, que se prestaba a confusión); admin y superadmin ven todo, porque son quienes programan."""
    return db.pedidos_para_reparto(con, hasta_hoy=db.rol_activo(con, usuario) == "reparto")


@router.post("/pedidos/{id_pedido}/entregar", response_model=EntregaResultado)
def entregar_pedido(id_pedido: int, _usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    """Entrega completa. Idempotente: si ya estaba entregado responde OK con `ya_estaba=True`,
    así un reintento (señal que se corta justo al tocar el botón) nunca da error."""
    try:
        resultado = db.marcar_entregado(con, id_pedido)
        con.commit()
    except Exception:
        con.rollback()
        raise
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "sin_programar":
        raise HTTPException(status_code=409, detail=f"El pedido {id_pedido} todavía no está programado para entrega")
    return EntregaResultado(id_pedido=id_pedido, ya_estaba=(resultado == "ya_estaba"))


@router.post("/clientes/{id_cliente}/ubicacion", response_model=UbicacionGuardada)
def guardar_ubicacion(id_cliente: int, datos: UbicacionIn, _usuario: str = Depends(deps.reparto_actual),
                      con=Depends(deps.conexion_actual)):
    """Guarda la ubicación del cliente con el GPS del reparto (estando en el lugar). Solo
    clientes con una entrega pendiente o reciente, y nunca pisa una ubicación ya cargada."""
    if datos.lat == 0 and datos.lng == 0:
        raise HTTPException(status_code=422, detail="La ubicación recibida no es válida")
    try:
        resultado = db.guardar_ubicacion_cliente(con, id_cliente, datos.lat, datos.lng)
        con.commit()
    except Exception:
        con.rollback()
        raise
    if resultado == "sin_entregas":
        raise HTTPException(status_code=404, detail="Ese cliente no tiene entregas pendientes ni recientes")
    if resultado == "ya_tiene":
        raise HTTPException(status_code=409, detail="Ese cliente ya tiene una ubicación cargada")
    return UbicacionGuardada(id_cliente=id_cliente, ubicacion_maps=db.enlace_maps(round(datos.lat, 6), round(datos.lng, 6)))
