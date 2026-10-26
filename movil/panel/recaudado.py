"""Dinero recaudado según los recibos cargados en el sistema (`ctacorr`, tipo `RC`).

Cada línea de un recibo es un renglón de `ctacorr` con importe NEGATIVO (el recibo baja el saldo
del cliente); lo recaudado es ese importe con el signo cambiado. Un mismo recibo puede tener varios
renglones (medios de pago): se suman todos y los recibos se cuentan por número.
"""
import pandas as pd


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
