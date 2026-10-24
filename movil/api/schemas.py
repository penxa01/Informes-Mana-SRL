"""Validación de entrada/salida de la API (Pydantic)."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    clave: str


class LoginResponse(BaseModel):
    token: str
    nombre: str
    rol: str  # 'vendedor' | 'reparto' | 'admin': decide qué pantalla muestra la app


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


class ClienteReparto(BaseModel):
    id: int
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    localidad: Optional[str] = None
    ubicacion_maps: Optional[str] = None   # enlace de Google Maps (solo http/https: lo exige la base)
    ubicacion_lat: Optional[float] = None
    ubicacion_lng: Optional[float] = None


class LineaReparto(BaseModel):
    id_producto: str
    nombre: Optional[str] = None
    cantidad: int
    entregada: int


class PedidoReparto(BaseModel):
    id_pedido: int
    estado: str   # 'programado' | 'en camino'
    fecha_pedido: Optional[date] = None
    fecha_entrega: Optional[date] = None
    cliente: ClienteReparto
    lineas: List[LineaReparto]


class EntregaResultado(BaseModel):
    id_pedido: int
    ya_estaba: bool  # True si ya estaba entregado (por ejemplo, un reintento)


class UbicacionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class UbicacionGuardada(BaseModel):
    id_cliente: int
    ubicacion_maps: str


class PanelRespuesta(BaseModel):
    datos: Dict[str, Any]          # litros del mes, % premium y recaudado de la semana (movil/panel/calculo.py)
    calculado_en: datetime         # cuándo se calcularon esos datos
    verificado_hace_seg: int       # hace cuánto revisó el proceso del servidor (aunque no hubiera nada nuevo)
    desactualizado: bool           # el proceso del servidor no da señales de vida: los números pueden ser viejos
    error: Optional[str] = None    # motivo del último intento fallido (los datos son los de antes)
