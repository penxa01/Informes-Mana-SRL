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
check("serie por día: 2 días con sus litros y premium",
      r["por_dia"] == [{"fecha": "2026-10-02", "litros": 30.0, "premium": 10.0},
                       {"fecha": "2026-10-03", "litros": 7.0, "premium": -2.0}], r["por_dia"])
vacio = litros.periodo(ventas, abmartic, clasificacion, D(2026, 11, 1), D(2026, 11, 5))
check("un período sin ventas da ceros, no falla", (vacio["litros"], vacio["pct_premium"], vacio["por_dia"]) == (0.0, 0.0, []), vacio)
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
check("la comparación del mes anterior llega hasta el mismo día (el 23): cuenta los 99 L del 10/9 y no los 7 del 30/9",
      panel["litros"]["mes_anterior"]["litros"] == 99.0, panel["litros"]["mes_anterior"])
check("trae lo recaudado de la semana y la anterior", panel["recaudado"]["semana"]["total"] == 3500.0 and panel["recaudado"]["semana_anterior"]["total"] == 500.0,
      (panel["recaudado"]["semana"]["total"], panel["recaudado"]["semana_anterior"]))
import json
check("todo es serializable a JSON", bool(json.dumps(panel)))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
