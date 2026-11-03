"""Rutas de los avisos (push): la clave pública para suscribirse, y alta/baja de la suscripción de
un celular. Las pueden usar todos los perfiles. Quién recibe qué lo decide el proceso notificador
(`movil/avisos/`), no esta API: acá solo se anota qué celulares aceptaron recibir avisos."""
from fastapi import APIRouter, Depends, HTTPException

from .. import config, db, deps, push
from ..schemas import BajaIn, ClavePublica, Confirmacion, SuscripcionIn

router = APIRouter(prefix="/push", tags=["avisos"])


@router.get("/clave", response_model=ClavePublica)
def clave_publica(_usuario: str = Depends(deps.avisos_actual)):
    if not config.VAPID_PUBLICA:
        raise HTTPException(status_code=503, detail="Los avisos todavía no están configurados en el servidor")
    return ClavePublica(clave=config.VAPID_PUBLICA)


@router.post("/suscribir", response_model=Confirmacion)
def suscribir(datos: SuscripcionIn, usuario: str = Depends(deps.avisos_actual), con=Depends(deps.conexion_actual)):
    """Idempotente: el celular la manda cada vez que abre la app."""
    if not push.endpoint_permitido(datos.endpoint):
        raise HTTPException(status_code=422, detail="La suscripción no es de un servicio de avisos conocido")
    if not (push.clave_p256dh_valida(datos.keys.p256dh) and push.secreto_auth_valido(datos.keys.auth)):
        raise HTTPException(status_code=422, detail="Las claves de la suscripción no son válidas")
    id_usuario = db.id_usuario(con, usuario)
    if id_usuario is None:
        raise HTTPException(status_code=401, detail="Usuario dado de baja")
    try:
        db.guardar_suscripcion(con, id_usuario, datos.endpoint, datos.keys.p256dh, datos.keys.auth,
                               push.MAX_SUSCRIPCIONES_POR_USUARIO)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return Confirmacion()


@router.post("/baja", response_model=Confirmacion)
def baja(datos: BajaIn, usuario: str = Depends(deps.avisos_actual), con=Depends(deps.conexion_actual)):
    """Idempotente: dar de baja algo que ya no está también es OK (por ejemplo, un reintento)."""
    id_usuario = db.id_usuario(con, usuario)
    if id_usuario is None:
        raise HTTPException(status_code=401, detail="Usuario dado de baja")
    try:
        db.borrar_suscripcion(con, id_usuario, datos.endpoint)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return Confirmacion()
