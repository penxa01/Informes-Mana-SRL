"""Gestión de pedidos del admin desde el celular: ver los pendientes y los entregados de la última semana, y
actuar sobre uno (entrega total o parcial, programar o reprogramar, borrar), con las mismas reglas que la PC.

Solo `admin` y `superadmin` (ver `deps.admin_actual`). Todo es idempotente: reintentar una orden (se cortó la
señal justo al tocar el botón) nunca la aplica dos veces ni da error.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from .. import db, deps
from ..schemas import (BorradoResultado, EntregaParcialIn, EntregaParcialResultado, EntregaResultado, GestionRespuesta,
                       ProgramarIn, ProgramarResultado)

router = APIRouter(prefix="/pedidos", tags=["gestion de pedidos"])
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


@router.get("/gestion", response_model=GestionRespuesta)
def listar(_usuario: str = Depends(deps.admin_actual), con=Depends(deps.conexion_actual)):
    return db.pedidos_para_gestion(con)


@router.post("/{id_pedido}/entregar", response_model=EntregaResultado)
def entregar(id_pedido: int, usuario: str = Depends(deps.admin_actual), con=Depends(deps.conexion_actual)):
    """Entrega completa. Sirve también para un pedido que todavía no estaba programado."""
    resultado = _aplicar(con, lambda: db.entregar_pedido_total(con, id_pedido))
    if resultado == "no_existe":
        raise HTTPException(status_code=404, detail=f"El pedido {id_pedido} no existe")
    if resultado == "entregado":
        log.info("Pedido %s entregado por completo por %s", id_pedido, usuario)
    return EntregaResultado(id_pedido=id_pedido, ya_estaba=(resultado == "ya_estaba"))


@router.post("/{id_pedido}/entrega-parcial", response_model=EntregaParcialResultado)
def entregar_parcial(id_pedido: int, datos: EntregaParcialIn, usuario: str = Depends(deps.admin_actual),
                     con=Depends(deps.conexion_actual)):
    """Entrega parcial. Cada línea trae el TOTAL entregado que tiene que quedar (no cuánto se entrega ahora), así
    reintentar la misma orden no entrega dos veces."""
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
        estado="entregado" if completo else "parcial",
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


@router.delete("/{id_pedido}", response_model=BorradoResultado)
def borrar(id_pedido: int, usuario: str = Depends(deps.admin_actual), con=Depends(deps.conexion_actual)):
    """Borra el pedido (para cuando el cliente lo cancela). Un pedido ya entregado no se borra desde el celular."""
    resultado = _aplicar(con, lambda: db.borrar_pedido(con, id_pedido))
    if resultado == "entregado":
        raise HTTPException(status_code=409, detail="Un pedido ya entregado no se borra desde el celular (se hace desde la PC)")
    if resultado == "borrado":
        log.warning("Pedido %s BORRADO por %s", id_pedido, usuario)
    return BorradoResultado(id_pedido=id_pedido, ya_no_estaba=(resultado == "ya_no_estaba"))
