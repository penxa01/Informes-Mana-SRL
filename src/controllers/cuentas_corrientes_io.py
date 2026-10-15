"""Deudores de cuentas corrientes a partir de ``ctacorr.dbf`` / ``ctaclien.dbf``.

Saldo = ``SALDO`` nativo de las facturas (FA/FC/FE) con saldo pendiente. Es el que
mantiene el sistema de gestión y ya contempla recibos, notas de crédito y
comprobantes ``CR`` aplicados. No se recalcula a mano: el script original
(FiltradoDeudasCtaCtes.py) solo descontaba RC y NC por factura, e ignoraba los
``CR``, con lo que daba por impagas facturas ya canceladas.

Solo lectura. ``calcular_deudores`` es pura (DataFrames in -> DataFrame out) para
poder re-aplicar otra ``fecha_desde`` sin volver a leer los DBF.
"""
import os
from datetime import date

import pandas as pd

from src.controllers import config, dbf_io

TC_FACTURAS = ("FA", "FC", "FE")
UMBRAL_SALDO = 0.01
DIAS_MORA = 30       # más de 30 días desde la emisión -> mora
DIAS_CRITICA = 60    # más de 60 días -> mora crítica
COLUMNAS_CTACORR = ["TC", "CLASE", "NROEST", "NC", "CUENTA", "FECHA", "TOTALL", "SALDO"]
COLUMNAS_SALIDA = ["Cuenta", "Cliente", "Saldo", "Factura más vieja"]
COLUMNAS_DETALLE = ["Emisión", "Comprobante", "Total", "Saldo"]


def _facturas_con_saldo(ctacorr, fecha_desde):
    """Filas de factura (FA/FC/FE) con saldo pendiente emitidas desde ``fecha_desde``.

    Única definición de "deuda" para la grilla y el detalle: si ambas usan esta
    función, el detalle de un cliente siempre suma lo que muestra la grilla.
    """
    tc = ctacorr["TC"].astype(str).str.strip().str.upper()
    saldo = pd.to_numeric(ctacorr["SALDO"], errors="coerce")
    mascara = (
        tc.isin(TC_FACTURAS)
        & (saldo > UMBRAL_SALDO)
        & (ctacorr["FECHA"] >= pd.Timestamp(fecha_desde))
    )
    return ctacorr.loc[mascara].assign(TC=tc[mascara], SALDO=saldo[mascara])


def calcular_deudores(ctacorr, clientes, fecha_desde):
    """Deuda pendiente por cliente desde ``fecha_desde`` (inclusive, sobre la
    fecha de emisión de la factura).

    :param ctacorr: DataFrame con ``TC``, ``CUENTA``, ``FECHA`` y ``SALDO``.
    :param clientes: DataFrame con ``CNUMERO`` y ``CNOMBRE``.
    :param fecha_desde: ``date``/``datetime``/``Timestamp``.
    :returns: DataFrame ``COLUMNAS_SALIDA`` ordenado por saldo descendente.
    """
    facturas = _facturas_con_saldo(ctacorr, fecha_desde)
    if facturas.empty:
        return pd.DataFrame(columns=COLUMNAS_SALIDA)

    por_cuenta = facturas.groupby("CUENTA").agg(
        Saldo=("SALDO", "sum"), **{"Factura más vieja": ("FECHA", "min")}
    )
    por_cuenta["Saldo"] = por_cuenta["Saldo"].round(2)

    nombres = dict(zip(clientes["CNUMERO"], clientes["CNOMBRE"].astype(str).str.strip()))
    por_cuenta["Cliente"] = [nombres.get(c, "CLIENTE DESCONOCIDO") for c in por_cuenta.index]

    return (
        por_cuenta.rename_axis("Cuenta")
        .reset_index()[COLUMNAS_SALIDA]
        .sort_values("Saldo", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def parsear_monto(txt):
    """'1.500.000,50' / '$ 2.500' / '1000' -> float. Vacío = 0. ``ValueError``
    con mensaje para el usuario si no se puede interpretar."""
    limpio = str(txt).replace("$", "").replace(" ", "")
    if not limpio:
        return 0.0
    try:
        return float(limpio.replace(".", "").replace(",", "."))
    except ValueError:
        raise ValueError(f"Monto inválido: «{str(txt).strip()}». Usá el formato 1.500.000,50")


def estado_mora(dias):
    """Estado de un cliente según la antigüedad (en días desde la emisión) de su
    factura más vieja con saldo. No hay plazo de pago en los datos: se mide
    desde la emisión, igual que el script original (30 días)."""
    if dias > DIAS_CRITICA:
        return "Mora crítica"
    if dias > DIAS_MORA:
        return "Mora"
    return "En término"


def _dias_desde(fechas, hoy):
    return (pd.Timestamp(hoy) - fechas).dt.days


def filtrar_deudores(deudores, texto="", saldo_min=0.0, dias_min=0, hoy=None):
    """Filtros de la grilla (todos en AND).

    :param texto: subcadena del nombre o del nº de cuenta, sin distinguir mayúsculas.
    :param saldo_min: saldo pendiente mínimo (inclusive).
    :param dias_min: antigüedad mínima, **estricta** ("mayor a 30 días").
    """
    hoy = hoy or date.today()
    mascara = deudores["Saldo"] >= saldo_min
    texto = (texto or "").strip().lower()
    if texto:
        mascara &= (
            deudores["Cliente"].str.lower().str.contains(texto, regex=False)
            | deudores["Cuenta"].astype(str).str.contains(texto, regex=False)
        )
    if dias_min:
        mascara &= _dias_desde(deudores["Factura más vieja"], hoy) > dias_min
    return deudores[mascara].reset_index(drop=True)


def resumen_cartera(ctacorr, deudores, fecha_desde, hoy=None):
    """KPIs del panel. La mora se mide **por factura** (no por cliente): un
    cliente con una factura de 90 días y otra de 5 aporta a la mora solo la
    de 90."""
    hoy = hoy or date.today()
    facturas = _facturas_con_saldo(ctacorr, fecha_desde)
    edad = _dias_desde(facturas["FECHA"], hoy)
    saldo_total = round(float(deudores["Saldo"].sum()), 2)
    mora = round(float(facturas.loc[edad > DIAS_MORA, "SALDO"].sum()), 2)
    critica = round(float(facturas.loc[edad > DIAS_CRITICA, "SALDO"].sum()), 2)

    def pct(parte):
        return round(parte * 100 / saldo_total, 2) if saldo_total else 0.0

    vieja = deudores.loc[deudores["Factura más vieja"].idxmin()] if len(deudores) else None
    return {
        "saldo_total": saldo_total,
        "clientes": len(deudores),
        "mora": mora,
        "pct_mora": pct(mora),
        "critica": critica,
        "pct_critica": pct(critica),
        "mas_antigua_fecha": vieja["Factura más vieja"] if vieja is not None else None,
        "mas_antigua_cliente": vieja["Cliente"] if vieja is not None else None,
    }


def detalle_facturas(ctacorr, cuenta, fecha_desde):
    """Facturas con saldo de un cliente, la más vieja primero.

    Una fila por comprobante del DBF, **sin agrupar**: si el sistema tiene un
    registro duplicado (misma factura dos veces) se ve, en vez de esconderse.
    """
    f = _facturas_con_saldo(ctacorr, fecha_desde)
    f = f[f["CUENTA"] == cuenta]
    if f.empty:
        return pd.DataFrame(columns=COLUMNAS_DETALLE)

    nro_est = pd.to_numeric(f["NROEST"], errors="coerce").fillna(0).astype(int)
    comprobante = (
        f["TC"] + " " + f["CLASE"].astype(str).str.strip().str.upper() + " "
        + nro_est.map("{:04d}".format) + "-" + f["NC"].astype(int).map("{:08d}".format)
    )
    detalle = pd.DataFrame({
        "Emisión": f["FECHA"],
        "Comprobante": comprobante,
        "Total": f["TOTALL"].astype(float).round(2),
        "Saldo": f["SALDO"].round(2),
    })
    return detalle.sort_values(["Emisión", "Comprobante"], kind="stable").reset_index(drop=True)


def cargar_datos():
    """Lee ``ctacorr`` y ``ctaclien`` (Parquet cacheado) -> ``(ctacorr, clientes)``."""
    base = config.DBF_BASE_PATH
    cache = config.CACHE_PATH
    ctacorr = dbf_io.leer_dbf_cacheado(
        os.path.join(base, "ctacorr.dbf"), os.path.join(cache, "ctacorr.parquet"), COLUMNAS_CTACORR
    )
    clientes = dbf_io.leer_dbf_cacheado(
        os.path.join(base, "ctaclien.dbf"), os.path.join(cache, "ctaclien.parquet"), ["CNUMERO", "CNOMBRE"]
    )
    return ctacorr, clientes
