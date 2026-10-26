"""GET /catalogo: clientes y productos para armar un pedido desde el celular.
Nunca teléfono, dirección, stock ni saldos — eso vive en la cartera completa
de la PC, no en el celular (si se pierde, se corta por Tailscale y listo)."""
from fastapi import APIRouter, Depends

from .. import db, deps
from ..schemas import CatalogoResponse

router = APIRouter(tags=["catalogo"])


@router.get("/catalogo", response_model=CatalogoResponse)
def obtener_catalogo(_usuario: str = Depends(deps.vendedor_actual), con=Depends(deps.conexion_actual)):
    clientes, productos, version = db.catalogo(con)
    return CatalogoResponse(version=version, clientes=clientes, productos=productos)
