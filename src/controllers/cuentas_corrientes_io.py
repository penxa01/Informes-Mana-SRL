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
COLUMNAS_CTACORR = ["TC", "CUENTA", "FECHA", "SALDO"]
COLUMNAS_SALIDA = ["Cuenta", "Cliente", "Saldo", "Factura más vieja"]


def calcular_deudores(ctacorr, clientes, fecha_desde):
    """Deuda pendiente por cliente desde ``fecha_desde`` (inclusive, sobre la
    fecha de emisión de la factura).

    :param ctacorr: DataFrame con ``TC``, ``CUENTA``, ``FECHA`` y ``SALDO``.
    :param clientes: DataFrame con ``CNUMERO`` y ``CNOMBRE``.
    :param fecha_desde: ``date``/``datetime``/``Timestamp``.
    :returns: DataFrame ``COLUMNAS_SALIDA`` ordenado por saldo descendente.
    """
    tc = ctacorr["TC"].astype(str).str.strip().str.upper()
    saldo = pd.to_numeric(ctacorr["SALDO"], errors="coerce")
    mascara = (
        tc.isin(TC_FACTURAS)
        & (saldo > UMBRAL_SALDO)
        & (ctacorr["FECHA"] >= pd.Timestamp(fecha_desde))
    )
    facturas = ctacorr.loc[mascara, ["CUENTA", "FECHA"]].assign(SALDO=saldo[mascara])
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
