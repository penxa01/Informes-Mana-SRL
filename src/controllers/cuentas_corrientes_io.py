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

import pandas as pd

from src.controllers import config, dbf_io

TC_FACTURAS = ("FA", "FC", "FE")
UMBRAL_SALDO = 0.01
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
