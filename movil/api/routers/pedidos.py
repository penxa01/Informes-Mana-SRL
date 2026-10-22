"""POST /pedidos: crea un pedido desde el celular. Idempotente por `uuid`
(lo genera el celular): reenviar el mismo pedido (reconexión, doble tap) no
lo duplica."""
from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps, pedidos
from ..schemas import PedidoCreado, PedidoCreate

router = APIRouter(tags=["pedidos"])


@router.post("/pedidos", response_model=PedidoCreado)
def crear_pedido(datos: PedidoCreate, username: str = Depends(deps.usuario_actual)):
    try:
        lineas = pedidos.validar_lineas([(l.id_producto, l.cantidad) for l in datos.lineas])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    con = db.conexion()
    try:
        if not db.cliente_existe(con, datos.id_cliente):
            raise HTTPException(status_code=422, detail=f"El cliente {datos.id_cliente} no existe")
        faltantes = db.productos_inexistentes(con, [id_producto for id_producto, _ in lineas])
        if faltantes:
            raise HTTPException(status_code=422, detail=f"Productos inexistentes: {', '.join(faltantes)}")

        id_pedido, ya_existia = db.crear_pedido(
            con, str(datos.uuid), datos.id_cliente, datos.fecha_pedido, lineas, username,
        )
        con.commit()
        return PedidoCreado(id_pedido=id_pedido, ya_existia=ya_existia)
    finally:
        con.close()
