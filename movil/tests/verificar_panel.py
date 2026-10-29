"""Cálculo del panel (movil/panel/): litros, % premium y recaudado, con datos inventados (sin leer
archivos ni la base). La comparación contra el escritorio con datos reales está en
tests/verificar_panel_paridad.py.

Correr desde la raíz:  python movil/tests/verificar_panel.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from movil.panel import calculo, litros, recaudado

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


D = dt.date
abmartic = pd.DataFrame({
    "CODART": ["A1", "L100", "L200", "01VA133"],
    "CODMEDIDA": ["5 lts", "1 lt", "4 lts", "1 lt"],
})
clasificacion = pd.DataFrame({
    "articulo": ["L100", "L200"], "Clasificacion": ["Premium", "Standard"], "Artiprov": [None, None],
})
ventas = pd.DataFrame([
    (D(2026, 10, 2), "FC", "L100", 10),
    (D(2026, 10, 2), "FC", "L200", 5),
    (D(2026, 10, 3), "NC", "L100", -2),        # una nota de crédito resta
    (D(2026, 10, 3), "FC", "01VA133", 4),
    (D(2026, 10, 3), "FC", "A1", 1),
    (D(2026, 10, 3), "PR", "L100", 100),       # tipo de comprobante que no es venta: no cuenta
    (D(2026, 10, 3), "FC", "NOEXISTE", 50),    # artículo ausente en abmartic: se descarta, como en el escritorio
    (D(2026, 9, 10), "FC", "L100", 99),        # mes anterior, dentro de "hasta el mismo día"
    (D(2026, 9, 30), "FC", "L100", 7),         # mes anterior pero DESPUÉS del día 23: no cuenta en la comparación
], columns=["FECHA", "TC", "MODELO", "U_VENDIDAS"])

print("=== litros ===")
r = litros.periodo(ventas, abmartic, clasificacion, D(2026, 10, 1), D(2026, 10, 23))
check("litros totales (10-2 de L100, 5x4 de L200, 4 valvoline, 5 de A1) = 37", r["litros"] == 37.0, r["litros"])
check("litros premium = 8 (solo L100, neto de la NC)", r["premium"] == 8.0, r["premium"])
check("% premium = 21,6", r["pct_premium"] == 21.6, r["pct_premium"])
ceros = {"litros": 0.0, "premium": 0.0}
check("serie por día: litros y premium de cada día",
      [(d["fecha"], d["litros"], d["premium"]) for d in r["por_dia"]] == [("2026-10-02", 30.0, 10.0), ("2026-10-03", 7.0, -2.0)], r["por_dia"])
check("cada día trae su desglose por proveedor",
      r["por_dia"][0]["proveedores"] == {"SHELL": {"litros": 30.0, "premium": 10.0}, "VALVOLINE": ceros, "OTROS": ceros}
      and r["por_dia"][1]["proveedores"] == {"SHELL": {"litros": -2.0, "premium": -2.0},
                                             "VALVOLINE": {"litros": 4.0, "premium": 0.0}, "OTROS": {"litros": 5.0, "premium": 0.0}},
      r["por_dia"])
check("el mes por proveedor: Shell 28 L (8 premium), Valvoline 4 L, Otros 5 L",
      r["por_proveedor"] == {"SHELL": {"litros": 28.0, "premium": 8.0}, "VALVOLINE": {"litros": 4.0, "premium": 0.0},
                             "OTROS": {"litros": 5.0, "premium": 0.0}}, r["por_proveedor"])
check("los tres proveedores suman el total del mes", sum(v["litros"] for v in r["por_proveedor"].values()) == r["litros"])
check("el premium solo existe en Shell", r["por_proveedor"]["VALVOLINE"]["premium"] == 0 and r["por_proveedor"]["OTROS"]["premium"] == 0)
vacio = litros.periodo(ventas, abmartic, clasificacion, D(2026, 11, 1), D(2026, 11, 5))
check("un período sin ventas da ceros, no falla", (vacio["litros"], vacio["pct_premium"], vacio["por_dia"]) == (0.0, 0.0, []), vacio)
check("y con los tres proveedores en cero", vacio["por_proveedor"] == {"SHELL": ceros, "VALVOLINE": ceros, "OTROS": ceros}, vacio)
check("conversión de medidas: 1 gl = 3,785 y desconocido sin número = 0",
      litros.codmedida_a_litros("1 GL") == 3.785 and litros.codmedida_a_litros("caja") == 0.0)
check("proveedor: L... = SHELL, 01VA133 = VALVOLINE, otro = OTROS",
      [litros.clasificar_proveedor(s) for s in ("L100", "01VA133", "A1")] == ["SHELL", "VALVOLINE", "OTROS"])

print("=== recaudado ===")
ctacorr = pd.DataFrame([
    # semana del lunes 19 al viernes 23 de octubre de 2026
    ("RC", D(2026, 10, 19), -1000.0, "00001", "10"),
    ("RC", D(2026, 10, 19), -500.0, "00001", "10"),     # mismo recibo, otro medio de pago
    ("rc ", D(2026, 10, 21), -2000.0, "00001", "11"),   # el tipo viene con minúsculas/espacios
    ("FC", D(2026, 10, 21), 99999.0, "00001", "500"),   # una factura no es recaudación
    ("RC", D(2026, 10, 18), -777.0, "00001", "9"),      # domingo anterior: otra semana
    ("RC", D(2026, 10, 24), -888.0, "00001", "12"),     # sábado: todavía no pasó
    # semana anterior, hasta el mismo día (viernes 16)
    ("RC", D(2026, 10, 12), -300.0, "00001", "5"),
    ("RC", D(2026, 10, 16), -200.0, "00001", "6"),
    ("RC", D(2026, 10, 17), -9999.0, "00001", "7"),     # sábado de la semana anterior: después del "mismo día"
], columns=["TC", "FECHA", "TOTALL", "NROEST", "NC"])
r = recaudado.periodo(ctacorr, D(2026, 10, 19), D(2026, 10, 23))
check("recaudado de la semana = 3500 (los importes negativos se suman en positivo)", r["total"] == 3500.0, r["total"])
check("cuenta 2 recibos (uno tiene dos renglones)", r["recibos"] == 2, r["recibos"])
check("serie por día", r["por_dia"] == [{"fecha": "2026-10-19", "monto": 1500.0}, {"fecha": "2026-10-21", "monto": 2000.0}], r["por_dia"])
check("sin recibos -> 0", recaudado.periodo(ctacorr, D(2026, 1, 1), D(2026, 1, 7))["total"] == 0.0)

print("=== desglose por medio de pago ===")
recibos = pd.DataFrame([
    ("RC", "     10", D(2026, 10, 19), 1500.0, 0.0, 0.0, 0.0),       # todo "efectivo": mitad en caja, mitad transferencia
    ("RC", "     11", D(2026, 10, 21), 2000.0, 1200.0, 300.0, 100.0),  # cheques + banco + retención + 400 de tarjeta
    ("FC", "     10", D(2026, 10, 20), 8888.0, 0.0, 0.0, 0.0),       # una factura no es un recibo
    ("RC", "     12", D(2026, 10, 24), 5555.0, 0.0, 0.0, 0.0),       # fuera de la semana
    ("RC", "      5", D(2026, 10, 12), 300.0, 0.0, 0.0, 0.0),        # semana anterior
    ("RC", "      6", D(2026, 10, 16), 200.0, 200.0, 0.0, 0.0),
    ("RC", "      7", None, 99.0, 0.0, 0.0, 0.0),                    # fecha vacía (bytes nulos en el DBF): se ignora
], columns=["TC", "NC", "FECHA", "TOTALL", "CHEQUES", "BANCO", "RETENCION"])
caja = pd.DataFrame([
    ("CAJA", D(2026, 10, 19), "I", "RECIBO DE CLIENTES", 1000.0, 10.0),
    ("TRANSF", D(2026, 10, 19), "I", "RECIBO DE CLIENTES", 500.0, 10.0),
    ("CAJA", D(2026, 10, 19), "I", "FACTURA CLIENTES", 9999.0, 10.0),   # misma numeración, pero es una venta de contado
    ("CAJA", D(2026, 10, 19), "E", "RECIBO DE CLIENTES", -50.0, 10.0),  # un egreso no es cobro
    ("CAJA", D(2026, 9, 1), "I", "RECIBO DE CLIENTES", 777.0, 10.0),    # mismo número en un recibo viejo: otro período
    ("CAJA", D(2026, 10, 12), "I", "RECIBO DE CLIENTES", 300.0, 5.0),
    ("CAJA", None, "I", "RECIBO DE CLIENTES", None, None),              # fila vacía
], columns=["CAJA", "FECHA", "TM", "DETALLE", "IMPORTE", "NCASOCIADO"])
d = recaudado.desglose(recibos, caja, D(2026, 10, 19), D(2026, 10, 23))
check("total de la semana = 3500 (de plan_caj)", d["total"] == 3500.0 and d["recibos"] == 2, d)
check("efectivo = lo que placaja marca CAJA (1000)", d["efectivo"] == 1000.0, d["efectivo"])
check("transferencia = TRANSF de placaja + BANCO (500 + 300)", d["transferencia"] == 800.0, d["transferencia"])
check("cheques 1200, retenciones 100", (d["cheques"], d["retenciones"]) == (1200.0, 100.0), d)
check("otros = lo que queda (400 de tarjeta), visible y aparte", d["otros"] == 400.0, d["otros"])
check("los cinco medios suman el total",
      round(d["efectivo"] + d["transferencia"] + d["cheques"] + d["retenciones"] + d["otros"], 2) == d["total"])
repetidos = pd.concat([recibos, pd.DataFrame([("RC", "     10", D(2026, 10, 20), 600.0, 0.0, 0.0, 0.0)], columns=recibos.columns)], ignore_index=True)
dr = recaudado.desglose(repetidos, caja, D(2026, 10, 19), D(2026, 10, 23))
check("un número de recibo repetido en el período no cuenta dos veces el cobro (el resto va a otros)",
      dr["efectivo"] == 1000.0 and dr["transferencia"] == 800.0 and dr["otros"] == 1000.0 and dr["total"] == 4100.0, dr)
vacio_d = recaudado.desglose(recibos, caja, D(2026, 1, 1), D(2026, 1, 7))
check("período sin recibos: todo en cero, no falla", set(vacio_d.values()) == {0.0, 0}, vacio_d)
check("sin filas en placaja el efectivo no se inventa: queda en otros",
      recaudado.desglose(recibos, caja.iloc[0:0], D(2026, 10, 19), D(2026, 10, 23))["otros"] == 2000.0 - 1200.0 - 300.0 - 100.0 + 1500.0)

print("=== períodos ===")
p = calculo.periodos(D(2026, 10, 23))
check("la semana arranca el lunes", p["semana"] == (D(2026, 10, 19), D(2026, 10, 23)), p["semana"])
check("semana anterior: del lunes anterior hasta el mismo día de la semana", p["semana_anterior"] == (D(2026, 10, 12), D(2026, 10, 16)))
check("mes anterior hasta el mismo día del mes", p["mes_anterior"] == (D(2026, 9, 1), D(2026, 9, 23)))
check("un lunes la semana es de un solo día", calculo.periodos(D(2026, 10, 19))["semana"] == (D(2026, 10, 19), D(2026, 10, 19)))
check("31 de marzo: el mes anterior se corta en el 28 (febrero)", calculo.periodos(D(2026, 3, 31))["mes_anterior"] == (D(2026, 2, 1), D(2026, 2, 28)))
check("31 de marzo de un año bisiesto: hasta el 29", calculo.periodos(D(2024, 3, 31))["mes_anterior"] == (D(2024, 2, 1), D(2024, 2, 29)))
check("enero: el mes anterior es diciembre del año anterior", calculo.periodos(D(2026, 1, 15))["mes_anterior"] == (D(2025, 12, 1), D(2025, 12, 15)))

print("=== panel completo ===")
panel = calculo.calcular(ventas, abmartic, clasificacion, ctacorr, D(2026, 10, 23))
check("trae litros del mes con su comparación", panel["litros"]["mes"]["litros"] == 37.0 and "mes_anterior" in panel["litros"])
check("la comparación del mes anterior también viene por proveedor",
      panel["litros"]["mes_anterior"]["por_proveedor"]["SHELL"]["litros"] == 99.0, panel["litros"]["mes_anterior"])
check("el formato del cálculo tiene versión (para recalcular cuando cambia)", isinstance(calculo.VERSION, int) and calculo.VERSION >= 2)
check("la comparación del mes anterior llega hasta el mismo día (el 23): cuenta los 99 L del 10/9 y no los 7 del 30/9",
      panel["litros"]["mes_anterior"]["litros"] == 99.0, panel["litros"]["mes_anterior"])
check("trae lo recaudado de la semana y la anterior", panel["recaudado"]["semana"]["total"] == 3500.0 and panel["recaudado"]["semana_anterior"]["total"] == 500.0,
      (panel["recaudado"]["semana"]["total"], panel["recaudado"]["semana_anterior"]))
check("sin plan_caj/placaja el panel sigue andando y no trae desglose", "desglose" not in panel["recaudado"]["semana"])
panel = calculo.calcular(ventas, abmartic, clasificacion, ctacorr, D(2026, 10, 23), recibos, caja)
sem = panel["recaudado"]["semana"]
check("con plan_caj y placaja la semana trae su desglose, sin tocar el total de ctacorr",
      sem["total"] == 3500.0 and sem["desglose"]["efectivo"] == 1000.0 and sem["desglose"]["transferencia"] == 800.0, sem)
check("control cruzado ctacorr vs plan_caj: diferencia 0 cuando coinciden", sem["desglose"]["diferencia"] == 0.0, sem["desglose"])
ant = panel["recaudado"]["semana_anterior"]
check("la semana anterior (hasta el mismo día) también: 300 en efectivo y 200 en cheques",
      ant["total"] == 500.0 and ant["desglose"]["efectivo"] == 300.0 and ant["desglose"]["cheques"] == 200.0 and ant["desglose"]["diferencia"] == 0.0, ant)
panel_roto = calculo.calcular(ventas, abmartic, clasificacion, ctacorr, D(2026, 10, 23), recibos.iloc[1:], caja)
check("si plan_caj no coincide con ctacorr la diferencia se ve (no se tapa)", panel_roto["recaudado"]["semana"]["desglose"]["diferencia"] == 1500.0,
      panel_roto["recaudado"]["semana"]["desglose"])
check("la versión del formato subió (para que el servidor recalcule solo)", calculo.VERSION >= 3)
import json
check("todo es serializable a JSON", bool(json.dumps(panel)))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
