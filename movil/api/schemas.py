"""Validación de entrada/salida de la API (Pydantic)."""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    clave: str


class LoginResponse(BaseModel):
    token: str
    nombre: str
