"""POST /auth/login: verifica usuario y clave contra la base y devuelve un
token de sesión firmado.

La cuenta de reparto tiene UNA sola sesión a la vez: al iniciar sesión se anota un identificador nuevo (`sesion_id`) y
el celular que la estaba usando recibe 401 en su próxima petición (ver `deps.exigir_rol`). Los demás perfiles pueden
tener la sesión abierta en varios celulares."""
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, db, deps
from ..schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("movil.api")


@router.post("/login", response_model=LoginResponse)
def login(datos: LoginRequest, con=Depends(deps.conexion_actual)):
    usuario_db = db.buscar_usuario(con, datos.username)
    es_reparto = usuario_db is not None and usuario_db.get("rol") == "reparto"
    sid = secrets.token_hex(16) if es_reparto else None
    try:
        token = auth.intentar_login(datos.username, datos.clave, usuario_db, sid=sid)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if sid is not None:
        try:
            db.fijar_sesion(con, datos.username, sid)
            con.commit()
        except Exception:
            con.rollback()
            raise
        log.info("La cuenta de reparto %s inició sesión: la sesión anterior (si había) deja de valer", datos.username)

    return LoginResponse(token=token, nombre=usuario_db["nombre"], rol=usuario_db["rol"])
