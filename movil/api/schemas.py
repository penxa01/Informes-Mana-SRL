"""Validación de entrada/salida de la API (Pydantic)."""
from typing import List, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    clave: str


class LoginResponse(BaseModel):
    token: str
    nombre: str


class ClienteCatalogo(BaseModel):
    id: int
    nombre: Optional[str] = None
    cuit: Optional[str] = None
    localidad: Optional[str] = None


class ProductoCatalogo(BaseModel):
    id: str
    nombre: Optional[str] = None


class CatalogoResponse(BaseModel):
    version: str
    clientes: List[ClienteCatalogo]
    productos: List[ProductoCatalogo]
