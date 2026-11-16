"""El panel de control, en tres rutas según quién pregunta:

  GET /panel             el panel general (litros del mes, % premium y recaudado de la semana): `admin` y `superadmin`.
  GET /panel/cobranzas   las cobranzas de TODA la empresa (la cartera, lo cobrado por mes y todos los clientes con sus
                         facturas): `admin` y `superadmin`.
  GET /panel/mio         el panel de un vendedor con SUS números (sus litros y sus cobranzas, solo los clientes de su
                         código): el rol `vendedor`.

La API no calcula nada: entrega lo que dejó en la base el proceso del servidor (`movil/panel/worker.py`), así responde al
instante y no lee los archivos del sistema.
"""
from fastapi import APIRouter, Depends, HTTPException

from ...panel import almacen
from .. import deps
from ..schemas import PanelRespuesta

router = APIRouter(tags=["panel"])

# El proceso del servidor revisa cada 5 minutos y deja un "latido" aunque no haya nada nuevo que
# calcular: si pasan más de 15 minutos sin latido (tres ciclos), está caído y los números pueden ser viejos.
SEGUNDOS_SIN_LATIDO = 15 * 60


def _estado_del_panel(con):
    """El estado del panel (el latido y el último error), o un 503 con el motivo si todavía no se calculó nada."""
    estado = almacen.leer_para_api(con)
    if estado is None or estado["datos"] is None:
        motivo = f" Último error: {estado['error']}" if estado and estado["error"] else ""
        raise HTTPException(status_code=503, detail="El panel todavía no se calculó, probá en un momento." + motivo)
    return estado


def _respuesta(datos, calculado_en, estado):
    return PanelRespuesta(
        datos=datos,
        calculado_en=calculado_en,
        verificado_hace_seg=estado["verificado_hace_seg"],
        desactualizado=estado["verificado_hace_seg"] > SEGUNDOS_SIN_LATIDO,
        error=estado["error"],
    )


@router.get("/panel/mio", response_model=PanelRespuesta)
def obtener_panel_propio(codigo: int = Depends(deps.vendedor_con_codigo), con=Depends(deps.conexion_actual)):
    """El panel del vendedor que pregunta: SUS litros, su cartera, lo cobrado a sus clientes y la lista de sus
    clientes con el detalle de facturas. El código sale de su usuario en la base (sin código: 404) y la ruta no
    recibe ningún parámetro: nadie tiene cómo pedir los datos de otro vendedor."""
    estado = _estado_del_panel(con)
    propio = almacen.leer_vendedor(con, codigo)
    if propio is None:
        raise HTTPException(status_code=404, detail="Todavía no hay datos de tu panel (aparecen cuando tenés clientes asignados). "
                                                    "Si ya los tenés, probá en unos minutos.")
    return _respuesta(propio["datos"], propio["calculado_en"], estado)


@router.get("/panel/cobranzas", response_model=PanelRespuesta)
def obtener_cobranzas_de_la_empresa(_usuario: str = Depends(deps.panel_actual), con=Depends(deps.conexion_actual)):
    """Las cobranzas de TODA la empresa, para el admin y el superadmin: la cartera de todos los clientes, lo cobrado por
    mes y cada cliente con el detalle de sus facturas. Un vendedor no la ve: solo ve lo suyo (`/panel/mio`)."""
    estado = _estado_del_panel(con)
    empresa = almacen.leer_empresa(con)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Todavía no hay datos de cobranzas, probá en unos minutos.")
    return _respuesta(empresa["datos"], empresa["calculado_en"], estado)


@router.get("/panel", response_model=PanelRespuesta)
def obtener_panel(_usuario: str = Depends(deps.panel_actual), con=Depends(deps.conexion_actual)):
    estado = _estado_del_panel(con)
    return _respuesta(estado["datos"], estado["calculado_en"], estado)
