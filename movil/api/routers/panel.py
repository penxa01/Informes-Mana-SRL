"""GET /panel: el panel de control (litros del mes, % premium y recaudado de la semana).

Solo `admin` y `superadmin`. La API no calcula nada: entrega lo que dejó en la base el proceso
del servidor (`movil/panel/worker.py`), así responde al instante y no lee los archivos del sistema.
"""
from fastapi import APIRouter, Depends, HTTPException

from ...panel import almacen
from .. import deps
from ..schemas import PanelRespuesta

router = APIRouter(tags=["panel"])

# El proceso del servidor revisa cada 5 minutos y deja un "latido" aunque no haya nada nuevo que
# calcular: si pasan más de 15 minutos sin latido (tres ciclos), está caído y los números pueden ser viejos.
SEGUNDOS_SIN_LATIDO = 15 * 60


@router.get("/panel", response_model=PanelRespuesta)
def obtener_panel(_usuario: str = Depends(deps.panel_actual), con=Depends(deps.conexion_actual)):
    estado = almacen.leer_para_api(con)
    if estado is None or estado["datos"] is None:
        motivo = f" Último error: {estado['error']}" if estado and estado["error"] else ""
        raise HTTPException(status_code=503, detail="El panel todavía no se calculó, probá en un momento." + motivo)
    return PanelRespuesta(
        datos=estado["datos"],
        calculado_en=estado["calculado_en"],
        verificado_hace_seg=estado["verificado_hace_seg"],
        desactualizado=estado["verificado_hace_seg"] > SEGUNDOS_SIN_LATIDO,
        error=estado["error"],
    )
