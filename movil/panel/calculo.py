"""Arma los datos del panel de control a partir de los archivos del sistema.

- Litros vendidos del MES en curso (1º a hoy) y % Premium, con la lógica del informe de Litros.
- Dinero recaudado de la SEMANA en curso: siempre desde el lunes de esa semana hasta hoy.
Cada cifra trae su comparación con el período anterior HASTA EL MISMO DÍA (mes anterior hasta el
mismo día del mes; semana anterior hasta el mismo día de la semana), para que se vea si se va arriba
o abajo sin comparar un período completo contra uno a medias.
"""
import calendar
import datetime as dt

from . import lectura, litros, recaudado


# Versión del FORMATO de lo que se calcula. El proceso del servidor la incluye en su firma: al subirla
# (porque cambió qué se calcula) se recalcula aunque los archivos del sistema no hayan cambiado.
# 2: litros por proveedor (Shell / Valvoline / Otros), para filtrar en el celular.
# 3: el recaudado trae su desglose (efectivo, transferencia, cheques, retenciones, otros).
VERSION = 3


def lunes_de(fecha):
    return fecha - dt.timedelta(days=fecha.weekday())


def periodos(hoy):
    """Los rangos (inclusive) que usa el panel para `hoy`."""
    mes_desde = hoy.replace(day=1)
    fin_mes_anterior = mes_desde - dt.timedelta(days=1)
    mes_ant_desde = fin_mes_anterior.replace(day=1)
    mes_ant_hasta = mes_ant_desde.replace(day=min(hoy.day, calendar.monthrange(mes_ant_desde.year, mes_ant_desde.month)[1]))
    sem_desde = lunes_de(hoy)
    return {
        "mes": (mes_desde, hoy),
        "mes_anterior": (mes_ant_desde, mes_ant_hasta),
        "semana": (sem_desde, hoy),
        "semana_anterior": (sem_desde - dt.timedelta(days=7), hoy - dt.timedelta(days=7)),
    }


def _rango(r):
    return {"desde": r[0].isoformat(), "hasta": r[1].isoformat()}


def _con_desglose(resumen, recibos, caja, rango):
    """Agrega el desglose por medio de pago al resumen de `ctacorr`. `diferencia` es el control
    cruzado entre las dos fuentes (`ctacorr` vs `plan_caj`): si no es 0, hay que mirar los datos."""
    d = recaudado.desglose(recibos, caja, *rango)
    d["diferencia"] = round(resumen["total"] - d["total"], 2)
    return {**resumen, "desglose": d}


def calcular(ventas, abmartic, clasificacion, ctacorr, hoy, recibos=None, caja=None):
    """Los datos del panel (un diccionario listo para guardarse como JSON). `recibos` (plan_caj) y
    `caja` (placaja) son opcionales: sin ellos el recaudado no trae desglose."""
    p = periodos(hoy)
    mes = litros.periodo(ventas, abmartic, clasificacion, *p["mes"])
    mes_ant = litros.periodo(ventas, abmartic, clasificacion, *p["mes_anterior"])
    sem = recaudado.periodo(ctacorr, *p["semana"])
    sem_ant = recaudado.periodo(ctacorr, *p["semana_anterior"])
    ant = {k: sem_ant[k] for k in ("total", "recibos")}
    if recibos is not None and caja is not None:
        sem = _con_desglose(sem, recibos, caja, p["semana"])
        ant = _con_desglose(ant, recibos, caja, p["semana_anterior"])
    return {
        "hoy": hoy.isoformat(),
        "periodos": {nombre: _rango(r) for nombre, r in p.items()},
        "litros": {
            "mes": mes,
            "mes_anterior": {k: mes_ant[k] for k in ("litros", "premium", "pct_premium", "por_proveedor")},
        },
        "recaudado": {
            "semana": sem,
            "semana_anterior": ant,
        },
    }


def calcular_desde_archivos(base_dbf, ruta_excel, hoy=None):
    """Lee los archivos del sistema y calcula el panel."""
    hoy = hoy or dt.date.today()
    rutas = lectura.archivos(base_dbf, ruta_excel)
    # El DBF no tiene índice: se lee entero y cada cálculo recorta su período.
    ventas = lectura.leer_dbf(rutas["fachist"], lectura.COLUMNAS_VENTAS)
    abmartic = lectura.leer_dbf(rutas["abmartic"], lectura.COLUMNAS_ABMARTIC)
    ctacorr = lectura.leer_dbf(rutas["ctacorr"], lectura.COLUMNAS_CTACORR)
    recibos = lectura.leer_dbf(rutas["plan_caj"], lectura.COLUMNAS_RECIBOS, tolerante=True)
    caja = lectura.leer_dbf(rutas["placaja"], lectura.COLUMNAS_CAJA, tolerante=True)
    clasificacion = lectura.leer_clasificacion(rutas["clasificacion"])
    return calcular(ventas, abmartic, clasificacion, ctacorr, hoy, recibos, caja)
