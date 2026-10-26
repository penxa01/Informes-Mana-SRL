"""POST /auth/login: verifica usuario y clave contra la base y devuelve un
token de sesión firmado."""
from fastapi import APIRouter, Depends, HTTPException

from .. import auth, db, deps
from ..schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(datos: LoginRequest, con=Depends(deps.conexion_actual)):
    usuario_db = db.buscar_usuario(con, datos.username)
    try:
        token = auth.intentar_login(datos.username, datos.clave, usuario_db)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return LoginResponse(token=token, nombre=usuario_db["nombre"], rol=usuario_db["rol"])
