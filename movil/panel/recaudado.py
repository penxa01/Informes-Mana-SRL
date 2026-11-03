"""Dinero recaudado según los recibos cargados en el sistema (`ctacorr`, tipo `RC`).

Cada línea de un recibo es un renglón de `ctacorr` con importe NEGATIVO (el recibo baja el saldo
del cliente); lo recaudado es ese importe con el signo cambiado. Un mismo recibo puede tener varios
renglones (medios de pago): se suman todos y los recibos se cuentan por número.
"""
import pandas as pd


def _numero(serie):
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def desglose(recibos, caja, desde, hasta):
    """Cómo se pagó lo recaudado entre `desde` y `hasta` (inclusive): efectivo, transferencia,
    cheques, retenciones y otros. Siempre suman el total, que sale de `plan_caj.TOTALL`.

    `recibos` es `plan_caj.DBF` (un renglón por comprobante, con una columna por medio de pago) y
    `caja` es `placaja.DBF` (movimientos de caja). Reglas, verificadas con los datos reales:
      - `plan_caj.EFECTIVO` mezcla efectivo y transferencias: `placaja` las separa con su campo `CAJA`
        (`CAJA` = efectivo, `TRANSF` = transferencia), ligando por número de recibo (`NCASOCIADO`).
      - Transferencia = las de `placaja` + `plan_caj.BANCO` (que también es una transferencia).
      - Cheques = `plan_caj.CHEQUES`. Retenciones = `plan_caj.RETENCION`.
      - Otros = lo que queda hasta el total (tarjetas, o un recibo que no se pudo ligar): se muestra
        aparte en vez de repartirlo, para que una diferencia nunca quede escondida.
    El cruce se hace solo dentro del período: los números de recibo viejos (2018-2022) se repiten.
    """
    inicio, fin = pd.Timestamp(desde), pd.Timestamp(hasta)
    tc = recibos["TC"].astype(str).str.strip().str.upper()
    fechas = pd.to_datetime(recibos["FECHA"], errors="coerce")
    rc = recibos.loc[(tc == "RC") & (fechas >= inicio) & (fechas <= fin)].copy()
    rc["nc"] = pd.to_numeric(rc["NC"].astype(str).str.strip(), errors="coerce")

    tm = caja["TM"].astype(str).str.strip().str.upper()
    fecha_caja = pd.to_datetime(caja["FECHA"], errors="coerce")
    es_recibo = caja["DETALLE"].astype(str).str.upper().str.contains("RECIBO", na=False)
    cobros = caja.loc[(tm == "I") & es_recibo & (fecha_caja >= inicio) & (fecha_caja <= fin)].copy()
    cobros["nc"] = pd.to_numeric(cobros["NCASOCIADO"], errors="coerce")
    importe = _numero(cobros["IMPORTE"])
    donde = cobros["CAJA"].astype(str).str.strip().str.upper()
    cobros["efectivo"] = importe.where(donde == "CAJA", 0.0)
    cobros["transf"] = importe.where(donde == "TRANSF", 0.0)

    rc = rc.join(cobros.groupby("nc")[["efectivo", "transf"]].sum(), on="nc")
    # Si un mismo número aparece en dos recibos del período, el cobro se le asigna a uno solo
    # (si no se contaría dos veces); el otro queda con su monto en "otros".
    repetido = rc["nc"].duplicated()
    rc.loc[repetido, ["efectivo", "transf"]] = 0.0
    rc[["efectivo", "transf"]] = rc[["efectivo", "transf"]].fillna(0.0)

    total = _numero(rc["TOTALL"])
    transferencia = rc["transf"] + _numero(rc["BANCO"])
    cheques = _numero(rc["CHEQUES"])
    retenciones = _numero(rc["RETENCION"])
    otros = total - rc["efectivo"] - transferencia - cheques - retenciones
    def redondeo(serie):
        return round(float(serie.sum()), 2) + 0.0   # + 0.0: que un resto nulo sea 0.0 y no -0.0

    return {
        "total": redondeo(total),
        "recibos": int(len(rc)),
        "efectivo": redondeo(rc["efectivo"]),
        "transferencia": redondeo(transferencia),
        "cheques": redondeo(cheques),
        "retenciones": redondeo(retenciones),
        "otros": redondeo(otros),
    }


def periodo(ctacorr, desde, hasta):
    """Recaudado entre `desde` y `hasta` (inclusive, fechas `date`): total, cantidad de recibos y
    serie por día. `ctacorr` trae ``TC``, ``FECHA``, ``TOTALL``, ``NROEST`` y ``NC``."""
    tc = ctacorr["TC"].astype(str).str.strip().str.upper()
    fechas = pd.to_datetime(ctacorr["FECHA"], errors="coerce")
    sel = (tc == "RC") & (fechas >= pd.Timestamp(desde)) & (fechas <= pd.Timestamp(hasta))
    rc = ctacorr.loc[sel].copy()
    rc["monto"] = -pd.to_numeric(rc["TOTALL"], errors="coerce").fillna(0.0)
    rc["dia"] = pd.to_datetime(rc["FECHA"]).dt.date

    por_dia = [
        {"fecha": dia.isoformat(), "monto": round(float(suma), 2)}
        for dia, suma in rc.groupby("dia")["monto"].sum().items()
    ]
    recibos = rc[["NROEST", "NC"]].astype(str).apply(lambda c: c.str.strip()).drop_duplicates().shape[0] if len(rc) else 0
    return {"total": round(float(rc["monto"].sum()), 2), "recibos": int(recibos), "por_dia": por_dia}
