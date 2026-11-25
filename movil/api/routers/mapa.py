"""Mapa de la pantalla Pedidos: dónde están los clientes (los que tienen la ubicación cargada) y dónde está el celular
de la cuenta de reparto.

  GET  /mapa/clientes       reparto, admin y superadmin   los clientes con ubicación (nombre, dirección y localidad)
  GET  /mapa/reparto        reparto, admin y superadmin   dónde está el reparto ahora (solo posiciones recientes)
  POST /mapa/mi-ubicacion   SOLO la cuenta de reparto     manda su posición (el celular lo hace solo, con la app abierta)
  POST /mapa/ruta           reparto, admin y superadmin   la mejor ruta entre los clientes con pedidos EN CAMINO

De la posición del reparto se guarda únicamente la última (se pisa, sin historial) y no se muestra si es vieja
(`db.POSICION_REPARTO_MAX_MINUTOS`). Los admin ven al reparto pero no mandan su propia posición.

La ruta no se guarda: se calcula al pedirla (movil/api/ruteo.py). Sale de la última posición del reparto (la misma
para quien la pida) y, si no hay una reciente, arranca por la parada que más convenga."""
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from .. import config, db, deps, ruteo
from ..schemas import ClienteMapa, Confirmacion, PosicionIn, PosicionReparto, RutaRespuesta

router = APIRouter(prefix="/mapa", tags=["mapa"])

# Pedir dos veces seguidas la misma ruta (un doble toque, dos personas mirando lo mismo) no vuelve a consultar al
# servidor de rutas. Se guarda lo calculado, no la respuesta: la posición del reparto y su antigüedad se leen siempre
# de la base. Si cambia un pedido en camino, la clave cambia y se recalcula.
_CACHE_SEGUNDOS = 30
_cache = {}


@router.get("/clientes", response_model=List[ClienteMapa])
def clientes(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    return db.clientes_con_ubicacion(con)


@router.get("/reparto", response_model=List[PosicionReparto])
def reparto(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    return db.posiciones_reparto(con)


def _clientes_en_camino(con):
    """Los clientes con algún pedido en camino, uno por cliente (con todos sus pedidos), en el orden de la lista."""
    por_cliente = {}
    for p in db.pedidos_para_gestion(con):
        if p["estado"] != "en camino":
            continue
        c = por_cliente.setdefault(p["id_cliente"], {
            "id_cliente": p["id_cliente"], "cliente": p["cliente"], "direccion": p["direccion"],
            "lat": None if p["ubicacion_lat"] is None else float(p["ubicacion_lat"]),
            "lng": None if p["ubicacion_lng"] is None else float(p["ubicacion_lng"]),
            "pedidos": [],
        })
        c["pedidos"].append(p["id_pedido"])
    return list(por_cliente.values())


def _calcular(origen, paradas):
    """`ruteo.armar_ruta` con una memoria corta (ver _CACHE_SEGUNDOS). `origen` y `paradas` son tuplas (lat, lng)."""
    ahora = time.monotonic()
    for clave in [k for k, (hasta, _) in _cache.items() if hasta < ahora]:
        del _cache[clave]
    # la salida se redondea a ~100 m: el reparto se mueve y no tiene sentido recalcular por unos metros
    clave = (None if origen is None else (round(origen[0], 3), round(origen[1], 3)), tuple(paradas))
    if clave in _cache:
        return _cache[clave][1]
    resultado = ruteo.armar_ruta(list(paradas), origen, url_base=config.OSRM_URL, pausa_s=config.OSRM_PAUSA_S)
    if not resultado["aproximada"] and resultado["trazado_por_calles"]:   # una ruta de emergencia se reintenta al pedirla de nuevo
        _cache[clave] = (ahora + _CACHE_SEGUNDOS, resultado)
    return resultado


@router.post("/ruta", response_model=RutaRespuesta)
def ruta(_usuario: str = Depends(deps.reparto_actual), con=Depends(deps.conexion_actual)):
    clientes = _clientes_en_camino(con)
    con_ubicacion = [c for c in clientes if c["lat"] is not None and c["lng"] is not None]
    sin_ubicacion = [{"id_cliente": c["id_cliente"], "cliente": c["cliente"], "pedidos": c["pedidos"]}
                     for c in clientes if c["lat"] is None or c["lng"] is None]
    posiciones = db.posiciones_reparto(con)
    reparto = min(posiciones, key=lambda p: p["hace_seg"]) if posiciones else None
    origen = None if reparto is None else (float(reparto["lat"]), float(reparto["lng"]))
    try:
        r = _calcular(origen, [(c["lat"], c["lng"]) for c in con_ubicacion])
    except ruteo.DemasiadasParadas as e:
        raise HTTPException(status_code=422, detail=f"Hay {e.cantidad} clientes con pedidos en camino: la ruta admite hasta {ruteo.MAX_PARADAS}")
    paradas = []
    for numero, (indice, tramo) in enumerate(zip(r["orden"], r["tramos"]), start=1):
        c = con_ubicacion[indice]
        paradas.append({"orden": numero, "id_cliente": c["id_cliente"], "cliente": c["cliente"], "direccion": c["direccion"],
                        "lat": c["lat"], "lng": c["lng"], "pedidos": c["pedidos"],
                        "metros": tramo["metros"], "segundos": tramo["segundos"]})
    return {
        "paradas": paradas, "trazado": r["trazado"], "metros": r["metros"], "segundos": r["segundos"],
        "origen": None if reparto is None else {"lat": origen[0], "lng": origen[1], "hace_seg": reparto["hace_seg"]},
        "aproximada": r["aproximada"], "trazado_por_calles": r["trazado_por_calles"], "sin_ubicacion": sin_ubicacion,
    }


@router.post("/mi-ubicacion", response_model=Confirmacion)
def mi_ubicacion(datos: PosicionIn, usuario: str = Depends(deps.solo_reparto), con=Depends(deps.conexion_actual)):
    if datos.lat == 0 and datos.lng == 0:
        raise HTTPException(status_code=422, detail="La ubicación recibida no es válida")
    try:
        db.guardar_posicion_reparto(con, usuario, datos.lat, datos.lng, datos.precision_m)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return Confirmacion()
