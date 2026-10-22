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
# Comprobantes que mueven el saldo contable de una cuenta (los mismos del script original):
# deudas (FA CH FC ND FE BE), saldo inicial (SI) y créditos (RC NC CR CC, con TOTALL negativo).
TC_CONTABLES = ("FA", "CH", "FC", "ND", "FE", "BE", "SI", "RC", "NC", "CR", "CC")
UMBRAL_SALDO = 0.01
DIAS_MORA = 30       # más de 30 días desde la emisión -> mora
DIAS_CRITICA = 60    # más de 60 días -> mora crítica
COLUMNAS_CTACORR = ["TC", "CLASE", "NROEST", "NC", "CUENTA", "FECHA", "TOTALL", "SALDO"]
COLUMNAS_SALIDA = ["Cuenta", "Cliente", "Saldo", "Factura más vieja"]
COLUMNAS_DETALLE = ["Emisión", "Comprobante", "Total", "Saldo"]
COLUMNAS_CLAVE = ["TC", "Clase", "NroEst", "NC"]   # identifican la factura (p. ej. para reclamarla)


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


def descripcion_filtros(fecha_desde, texto="", saldo_min=0.0, dias_min=0):
    """Una línea con lo que está aplicado, para mostrar con el panel de filtros plegado:
    ``Desde 01/01/2024 · filtros: cliente, saldo mínimo``."""
    activos = [nombre for nombre, activo in (
        ("cliente", bool((texto or "").strip())),
        ("saldo mínimo", bool(saldo_min)),
        ("antigüedad", bool(dias_min)),
    ) if activo]
    linea = f"Desde {fecha_desde.strftime('%d/%m/%Y')}"
    return linea + (f" · filtros: {', '.join(activos)}" if activos else "")


def saldos_a_favor(ctacorr, deudores):
    """Cuentas con **saldo contable negativo** (el cliente tiene crédito a su favor) que
    NO figuran en ``deudores``. Devuelve una ``Series`` cuenta -> saldo (negativo).

    El saldo contable de una cuenta es la suma de ``TOTALL`` de todos sus movimientos
    (facturas y notas de débito suman; recibos y notas de crédito restan), de toda la
    historia: es un estado actual, no depende de ``fecha_desde``. No son deuda a cobrar,
    por eso no van en la tabla, pero bajan el total neto.

    Las cuentas que ya están en ``deudores`` (tienen factura pendiente) se excluyen: ya
    cuentan por esa factura y descontarlas de nuevo sería contar dos veces.
    """
    tc = ctacorr["TC"].astype(str).str.strip().str.upper()
    movimientos = ctacorr.loc[tc.isin(TC_CONTABLES)]
    saldo_cuenta = pd.to_numeric(movimientos["TOTALL"], errors="coerce").groupby(movimientos["CUENTA"]).sum()
    negativas = saldo_cuenta[saldo_cuenta < -UMBRAL_SALDO]
    return negativas[~negativas.index.isin(deudores["Cuenta"])].sort_values()


def resumen_cartera(ctacorr, deudores, fecha_desde, hoy=None):
    """KPIs del panel. La mora se mide **por factura** (no por cliente): un
    cliente con una factura de 90 días y otra de 5 aporta a la mora solo la
    de 90.

    ``saldo_total`` es el **neto**: lo que debe la cartera (``saldo_bruto``, lo que
    suma la tabla) menos los saldos a favor de cuentas que no se listan (``a_favor``).
    Los porcentajes de mora se calculan contra el bruto: mora y cartera son de facturas.
    """
    hoy = hoy or date.today()
    facturas = _facturas_con_saldo(ctacorr, fecha_desde)
    edad = _dias_desde(facturas["FECHA"], hoy)
    saldo_bruto = round(float(deudores["Saldo"].sum()), 2)
    a_favor = saldos_a_favor(ctacorr, deudores)
    total_a_favor = round(float(a_favor.sum()), 2)
    mora = round(float(facturas.loc[edad > DIAS_MORA, "SALDO"].sum()), 2)
    critica = round(float(facturas.loc[edad > DIAS_CRITICA, "SALDO"].sum()), 2)

    def pct(parte):
        return round(parte * 100 / saldo_bruto, 2) if saldo_bruto else 0.0

    vieja = deudores.loc[deudores["Factura más vieja"].idxmin()] if len(deudores) else None
    return {
        "saldo_total": round(saldo_bruto + total_a_favor, 2),
        "saldo_bruto": saldo_bruto,
        "a_favor": total_a_favor,
        "cuentas_a_favor": len(a_favor),
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
        return pd.DataFrame(columns=COLUMNAS_DETALLE + COLUMNAS_CLAVE)

    nro_est = pd.to_numeric(f["NROEST"], errors="coerce").fillna(0).astype(int)
    clase = f["CLASE"].astype(str).str.strip().str.upper()
    nc = f["NC"].astype(int)
    detalle = pd.DataFrame({
        "Emisión": f["FECHA"],
        "Comprobante": f["TC"] + " " + clase + " " + nro_est.map("{:04d}".format) + "-" + nc.map("{:08d}".format),
        "Total": f["TOTALL"].astype(float).round(2),
        "Saldo": f["SALDO"].round(2),
        "TC": f["TC"],
        "Clase": clase,
        "NroEst": nro_est,
        "NC": nc,
    })
    return detalle.sort_values(["Emisión", "Comprobante"], kind="stable").reset_index(drop=True)


def opciones_clientes(clientes):
    """Todos los clientes de ctaclien para elegir en un combo: ``[(etiqueta, cuenta)]``.

    La etiqueta lleva el nº de cuenta ("ALFA SRL (10)"): en ctaclien hay nombres
    repetidos y sin eso el combo no podría distinguirlos. Orden alfabético.
    """
    filas = []
    for cuenta, nombre in zip(clientes["CNUMERO"], clientes["CNOMBRE"]):
        nombre = "" if nombre is None or pd.isna(nombre) else str(nombre).strip()
        nombre = nombre or "SIN NOMBRE"
        filas.append((nombre.lower(), int(cuenta), f"{nombre} ({int(cuenta)})"))
    filas.sort()
    return [(etiqueta, cuenta) for _, cuenta, etiqueta in filas]


def datos_cliente(clientes, cuenta):
    """Teléfono y código de vendedor de un cliente según ``ctaclien``.

    :returns: ``{"telefono": str, "vendedor_codigo": int | None}``. Teléfono
        vacío (``""``) si el cliente no existe o no tiene dato: la UI lo pide a mano.
    """
    vacio = {"telefono": "", "vendedor_codigo": None}
    fila = clientes[clientes["CNUMERO"] == cuenta]
    if fila.empty:
        return vacio
    fila = fila.iloc[0]

    telefono = fila.get("TELEFONO")
    telefono = "" if telefono is None or pd.isna(telefono) else str(telefono).strip()

    try:
        vendedor = int(float(str(fila.get("VENDEDOR")).strip()))
    except (TypeError, ValueError):
        vendedor = None
    return {"telefono": telefono, "vendedor_codigo": vendedor}


def cargar_datos():
    """Lee ``ctacorr`` y ``ctaclien`` (Parquet cacheado) -> ``(ctacorr, clientes)``."""
    base = config.DBF_BASE_PATH
    cache = config.CACHE_PATH
    ctacorr = dbf_io.leer_dbf_cacheado(
        os.path.join(base, "ctacorr.dbf"), os.path.join(cache, "ctacorr.parquet"), COLUMNAS_CTACORR
    )
    clientes = dbf_io.leer_dbf_cacheado(
        os.path.join(base, "ctaclien.dbf"), os.path.join(cache, "ctaclien.parquet"),
        ["CNUMERO", "CNOMBRE", "TELEFONO", "VENDEDOR"],
    )
    return ctacorr, clientes
