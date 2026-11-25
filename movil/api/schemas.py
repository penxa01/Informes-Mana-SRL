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
    # Texto libre y opcional (ver pedidos.limpiar_observaciones: ahí se limpia y se pone el tope real; este es solo un
    # corte grueso para no recibir un cuerpo enorme).
    observaciones: Optional[str] = Field(default=None, max_length=5000)


class PedidoCreado(BaseModel):
    id_pedido: int
    ya_existia: bool  # True si este uuid ya se había recibido antes


class EntregaResultado(BaseModel):
    """Respuesta de marcar un pedido como entregado o como en camino."""
    id_pedido: int
    ya_estaba: bool  # True si ya estaba en ese estado (por ejemplo, un reintento)


class ClienteMapa(BaseModel):
    id: int
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    lat: float
    lng: float


class PosicionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    precision_m: Optional[float] = Field(default=None, ge=0, le=100000)   # precisión del GPS, en metros


class PosicionReparto(BaseModel):
    nombre: Optional[str] = None
    lat: float
    lng: float
    precision_m: Optional[float] = None
    hace_seg: int   # hace cuánto llegó esa posición (con el reloj de la base)


class OrigenRuta(BaseModel):
    lat: float
    lng: float
    hace_seg: int   # hace cuánto llegó esa posición del reparto


class ParadaRuta(BaseModel):
    orden: int                 # 1, 2, 3...: el orden en que conviene visitarla
    id_cliente: int
    cliente: Optional[str] = None
    direccion: Optional[str] = None
    lat: float
    lng: float
    pedidos: List[int]         # los pedidos en camino de ese cliente (una sola parada por cliente)
    metros: int                # desde la parada anterior (o desde la salida)
    segundos: int


class ClienteSinUbicacion(BaseModel):
    id_cliente: int
    cliente: Optional[str] = None
    pedidos: List[int]


class RutaRespuesta(BaseModel):
    paradas: List[ParadaRuta]
    trazado: List[List[float]]          # [[lat, lng], ...] para dibujar el recorrido
    metros: int
    segundos: int
    origen: Optional[OrigenRuta] = None  # None: no hay posición reciente del reparto y la ruta arranca donde convenga
    aproximada: bool                     # True: no se pudo consultar las calles, el orden salió en línea recta
    trazado_por_calles: bool             # False: el dibujo es una poligonal recta entre las paradas
    sin_ubicacion: List[ClienteSinUbicacion]   # clientes en camino a los que les falta la ubicación: no entran en la ruta


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


class ClavePublica(BaseModel):
    clave: str   # clave pública VAPID (base64url): el navegador la necesita para suscribirse a los avisos


class ClavesSuscripcion(BaseModel):
    p256dh: str = Field(max_length=128)
    auth: str = Field(max_length=64)


class SuscripcionIn(BaseModel):
    """Lo que entrega el navegador (`PushSubscription.toJSON()`) al aceptar los avisos."""
    endpoint: str = Field(max_length=1024)
    keys: ClavesSuscripcion


class BajaIn(BaseModel):
    endpoint: str = Field(max_length=1024)


class Confirmacion(BaseModel):
    ok: bool = True


# ── Pedidos por entregar: admin y reparto (routers/gestion.py) ────────────────
class LineaGestion(BaseModel):
    id_detalle: int      # la entrega parcial y quitar un artículo identifican la línea por esto, no por el producto
    id_producto: str
    nombre: Optional[str] = None
    cantidad: int
    entregada: int


class PedidoGestion(BaseModel):
    id_pedido: int
    estado: str                       # 'pendiente' | 'programado' | 'en camino' (los entregados no se listan)
    origen: str                       # 'pc' | 'movil'
    fecha_pedido: Optional[date] = None
    fecha_entrega: Optional[date] = None
    cliente: Optional[str] = None
    id_cliente: int
    direccion: Optional[str] = None
    ubicacion_maps: Optional[str] = None   # enlace de Google Maps (solo http/https: lo exige la base)
    ubicacion_lat: Optional[float] = None
    ubicacion_lng: Optional[float] = None
    cargado_por: Optional[str] = None  # nombre de quien lo cargó desde el celular (None si lo cargó la PC)
    observaciones: Optional[str] = None
    lineas: List[LineaGestion]


class LineaEntregaIn(BaseModel):
    id_detalle: int
    entregada: int = Field(ge=0, le=1000000)   # el TOTAL entregado que tiene que quedar (no cuánto se entrega ahora)


class EntregaParcialIn(BaseModel):
    lineas: List[LineaEntregaIn]


class EntregaParcialResultado(BaseModel):
    id_pedido: int
    estado: str          # 'entregado' si con esto no queda nada por entregar; si no, 'pendiente' (queda lo que falta)
    completo: bool
    sin_cambios: bool    # True si ya estaba así (por ejemplo, un reintento)


class QuitarLineaResultado(BaseModel):
    id_pedido: int
    id_detalle: int
    ya_no_estaba: bool   # True si esa línea ya no estaba (por ejemplo, un reintento)
    completo: bool       # True si al quitarla el pedido quedó entregado (todo lo que quedaba ya se había entregado)


class ProgramarIn(BaseModel):
    fecha: date


class ProgramarResultado(BaseModel):
    id_pedido: int
    fecha_entrega: date


class BorradoResultado(BaseModel):
    id_pedido: int
    ya_no_estaba: bool   # True si ya no existía (por ejemplo, un reintento)

