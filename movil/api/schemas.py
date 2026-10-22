"""Validación de entrada/salida de la API (Pydantic)."""
from datetime import date
from typing import List, Optional
from uuid import UUID

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


class LineaPedido(BaseModel):
    id_producto: str
    cantidad: int


class PedidoCreate(BaseModel):
    uuid: UUID  # lo genera el celular; es la clave de idempotencia
    id_cliente: int
    fecha_pedido: date
    lineas: List[LineaPedido]


class PedidoCreado(BaseModel):
    id_pedido: int
    ya_existia: bool  # True si este uuid ya se había recibido antes
