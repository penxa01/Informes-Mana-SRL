"""Pedidos por entregar desde el celular: la lista (pendientes, programados y en camino) y lo que se puede hacer con
cada uno, con las mismas reglas que la PC.

Dos perfiles, un solo panel:
  - reparto, admin y superadmin (`deps.reparto_actual`): ver la lista, marcar un pedido EN CAMINO y entregarlo, por
    completo o en parte. Sin importar que esté pendiente o programado.
  - solo admin y superadmin (`deps.admin_actual`): programar o reprogramar, quitar un artículo y borrar el pedido.
    El reparto NO puede borrar pedidos.

Todo es idempotente: reintentar una orden (se cortó la señal justo al tocar el botón, o la mandó la cola del teléfono
dos veces) nunca la aplica dos veces ni da error.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps
from ..schemas import (BorradoResultado, EntregaParcialIn, EntregaParcialResultado, EntregaResultado, PedidoGestion,
                       ProgramarIn, ProgramarResultado, QuitarLineaResultado)

router = APIRouter(prefix="/pedidos", tags=["pedidos por entregar"])
log = logging.getLogger("movil.api")


def _aplicar(con, accion):
    """Corre una acción de base y confirma; si algo falla, no queda nada a medias."""
    try:
        resultado = accion()
        con.commit()
        return resultado
    except Exception:
        con.rollback()
        raise


@router.get("/gestion", response_model=List[PedidoGestion])
def listar(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    return db.pedidos_para_gestion(con)


@router.post("/{id_pedido}/en-camino", response_model=EntregaResultado)
def en_camino(id_pedido: int, usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    """Marca el pedido como en camino. Sirve desde pendiente o programado."""
    resultado = _aplicar(con, lambda: db.marcar_en_camino(con, id_pedido))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "ya_entregado":
        raise HTTPException(status_code=409, detail="Ese pedido ya está entregado")
    if resultado == "en_camino":
        log.info("Pedido %s en camino, marcado por %s", id_pedido, usuario)
    return EntregaResultado(id_pedido=id_pedido, ya_estaba=(resultado == "ya_estaba"))


@router.post("/{id_pedido}/entregar", response_model=EntregaResultado)
def entregar(id_pedido: int, usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    """Entrega completa. Sirve desde pendiente, programado o en camino."""
    resultado = _aplicar(con, lambda: db.entregar_pedido_total(con, id_pedido))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "entregado":
        log.info("Pedido %s entregado por completo por %s", id_pedido, usuario)
    return EntregaResultado(id_pedido=id_pedido, ya_estaba=(resultado == "ya_estaba"))


@router.post("/{id_pedido}/entrega-parcial", response_model=EntregaParcialResultado)
def entregar_parcial(id_pedido: int, datos: EntregaParcialIn, usuario: str = Depends(deps.reparto_actual),
                     con=Depends(deps.conexion_actual)):
    """Entrega parcial. Cada línea trae el TOTAL entregado que tiene que quedar (no cuánto se entrega ahora), así
    reintentar la misma orden no entrega dos veces. Si falta entregar algo, el pedido vuelve a 'pendiente' con lo que
    falta; si no queda nada, pasa a 'entregado'."""
    if not datos.lineas:
        raise HTTPException(status_code=422, detail="Falta indicar qué se entrega")
    objetivos = {}
    for l in datos.lineas:
        if l.id_detalle in objetivos:
            raise HTTPException(status_code=422, detail=f"La línea {l.id_detalle} está repetida")
        objetivos[l.id_detalle] = l.entregada
    resultado, detalle = _aplicar(con, lambda: db.entrega_parcial(con, id_pedido, objetivos))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "linea_ajena":
        raise HTTPException(status_code=422, detail=f"La línea {detalle} no es de este pedido")
    if resultado == "excede":
        raise HTTPException(status_code=422, detail="No se puede entregar más de lo que se pidió")
    if resultado == "cambio":
        raise HTTPException(status_code=409, detail="El pedido cambió mientras lo mirabas (ya se había entregado más). Actualizá la lista.")
    if resultado in ("parcial", "completo"):
        log.info("Pedido %s: entrega %s hecha por %s", id_pedido, resultado, usuario)
    completo = resultado in ("completo", "ya_entregado")   # si ya estaba entregado, reintentar es lo mismo
    return EntregaParcialResultado(
        id_pedido=id_pedido,
        estado="entregado" if completo else "pendiente",
        completo=completo,
        sin_cambios=resultado in ("sin_cambios", "ya_entregado"),
    )


@router.post("/{id_pedido}/programar", response_model=ProgramarResultado)
def programar(id_pedido: int, datos: ProgramarIn, usuario: str = Depends(deps.admin_actual),
              con=Depends(deps.conexion_actual)):
    """Programa (o reprograma) la entrega para esa fecha. No puede ser anterior a hoy."""
    resultado = _aplicar(con, lambda: db.programar_pedido(con, id_pedido, datos.fecha))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "ya_entregado":
        raise HTTPException(status_code=409, detail="Un pedido ya entregado no se puede programar")
    if resultado == "fecha_pasada":
        raise HTTPException(status_code=422, detail="La fecha no puede ser anterior a hoy")
    log.info("Pedido %s programado para el %s por %s", id_pedido, datos.fecha, usuario)
    return ProgramarResultado(id_pedido=id_pedido, fecha_entrega=datos.fecha)


@router.delete("/{id_pedido}/lineas/{id_detalle}", response_model=QuitarLineaResultado)
def quitar_linea(id_pedido: int, id_detalle: int, usuario: str = Depends(deps.admin_actual),
                 con=Depends(deps.conexion_actual)):
    """Quita un artículo del pedido (como la ✕ del detalle en la PC). Solo de un pedido sin entregar, y no el
    último artículo (para eso está borrar el pedido) ni uno del que ya se entregó algo."""
    resultado = _aplicar(con, lambda: db.quitar_linea(con, id_pedido, id_detalle))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "ya_entregado":
        raise HTTPException(status_code=409, detail="Un pedido ya entregado no se modifica desde el celular (se hace desde la PC)")
    if resultado == "entregada_en_parte":
        raise HTTPException(status_code=409, detail="De ese artículo ya se entregó una parte: no se puede quitar del pedido")
    if resultado == "es_la_unica":
        raise HTTPException(status_code=409, detail="Es el único artículo del pedido: si no se entrega, borrá el pedido entero")
    if resultado in ("quitada", "completo"):
        log.warning("Pedido %s: artículo (línea %s) QUITADO por %s", id_pedido, id_detalle, usuario)
    return QuitarLineaResultado(id_pedido=id_pedido, id_detalle=id_detalle,
                                ya_no_estaba=(resultado == "ya_no_estaba"), completo=(resultado == "completo"))


@router.delete("/{id_pedido}", response_model=BorradoResultado)
def borrar(id_pedido: int, usuario: str = Depends(deps.admin_actual), con=Depends(deps.conexion_actual)):
    """Borra el pedido (para cuando el cliente lo cancela). Un pedido ya entregado no se borra desde el celular."""
    resultado = _aplicar(con, lambda: db.borrar_pedido(con, id_pedido))
    if resultado == "entregado":
        raise HTTPException(status_code=409, detail="Un pedido ya entregado no se borra desde el celular (se hace desde la PC)")
    if resultado == "borrado":
        log.warning("Pedido %s BORRADO por %s", id_pedido, usuario)
    return BorradoResultado(id_pedido=id_pedido, ya_no_estaba=(resultado == "ya_no_estaba"))
