"""El panel de cada vendedor (movil/panel/vendedores.py) con datos inventados, sin leer archivos ni la base:
cartera (vencido / por vencer a 7 días / al día / a favor), clientes con el detalle de facturas, cobrado por
mes y litros. La comparación contra el panel general y el escritorio con datos reales está en
tests/verificar_panel_paridad.py.

Correr desde la raíz:  python movil/tests/verificar_panel_vendedores.py
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from movil.panel import calculo, lectura, litros, recaudado, vendedores

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


D = dt.date
HOY = D(2026, 10, 23)

print("=== meses ===")
m = vendedores.meses(HOY)
check("12 meses: el en curso llega hasta hoy y el último es noviembre del año anterior",
      len(m) == 12 and m[0] == ("2026-10", D(2026, 10, 1), HOY) and m[-1][0] == "2025-11", m[:2] + m[-1:])
check("un mes cerrado llega a su último día", m[1] == ("2026-09", D(2026, 9, 1), D(2026, 9, 30)), m[1])
m2 = vendedores.meses(D(2026, 1, 15), 3)
check("cruza el cambio de año", [x[0] for x in m2] == ["2026-01", "2025-12", "2025-11"], m2)
check("febrero tiene 28 días en 2026", vendedores.meses(D(2026, 3, 10), 2)[1][2] == D(2026, 2, 28))

print("=== cartera ===")
clientes = pd.DataFrame([
    (10, "ALFA SRL", 1, False),
    (11, "BETA SA", 1, False),          # sin deuda: se puede consultar
    (12, "GAMA", 1, True),              # inactivo y sin deuda: no se lista
    (13, "DELTA", 4, False),            # saldo a favor
    (20, "OMEGA", 4, False),
    (30, "SIN VENDEDOR", None, False),
], columns=["CNUMERO", "CNOMBRE", "VENDEDOR", "INACTIVO"])
COLS = ["TC", "FECHA", "TOTALL", "NROEST", "NC", "CLASE", "CUENTA", "SALDO", "FECHAVTO"]
ctacorr = pd.DataFrame([
    ("FC", D(2026, 9, 10), 5000.0, "0003", 123, "B", 10, 1000.0, D(2026, 10, 10)),    # venció hace 13 días
    ("FC", D(2026, 9, 23), 900.0, "0003", 124, "B", 10, 200.0, D(2026, 10, 23)),      # vence hoy: por vencer
    ("FC", D(2026, 9, 30), 900.0, "0003", 125, "B", 10, 300.0, D(2026, 10, 30)),      # vence en 7 días justo: por vencer
    ("FC", D(2026, 10, 1), 900.0, "0003", 126, "B", 10, 400.0, D(2026, 10, 31)),      # vence en 8 días: al día
    ("FC", D(2026, 8, 1), 900.0, "0003", 127, "B", 10, 0.0, D(2026, 8, 31)),          # pagada
    ("FC", D(2026, 8, 2), 900.0, "0003", 128, "B", 10, 0.005, D(2026, 9, 1)),         # resto de redondeo: no cuenta
    ("RC", D(2026, 9, 1), -50.0, "0003", 9, "", 10, 5000.0, None),                    # un recibo no es una factura aunque traiga SALDO
    ("FE", D(2026, 8, 20), 800.0, "0003", 130, "A", 20, 700.0, None),                 # sin vencimiento: emisión + 30 días = vencida
    ("FC", D(2026, 7, 1), 100.0, "0003", 131, "A", 13, 0.0, D(2026, 7, 31)),
    ("RC", D(2026, 8, 1), -350.0, "0003", 10, "", 13, 0.0, None),                     # DELTA pagó de más: saldo contable -250
    ("FC", D(2026, 10, 1), 999.0, "0003", 132, "A", 30, 999.0, D(2026, 10, 1)),       # cliente sin vendedor: no es de nadie
    ("FC", D(2026, 10, 1), 999.0, "0003", 133, "A", 99, 999.0, D(2026, 10, 1)),       # cuenta que ya no está en ctaclien
], columns=COLS)
c = vendedores.cartera(ctacorr, clientes, HOY)
check("solo hay datos de los vendedores 1 y 4 (el cliente sin vendedor no es de nadie)", sorted(c) == [1, 4], sorted(c))
v1 = c[1]["cartera"]
check("vendedor 1: vencido 1000, por vencer 500 (hoy y +7 días), al día 400, en calle 1900",
      (v1["vencido"], v1["por_vencer"], v1["al_dia"], v1["en_calle"]) == (1000.0, 500.0, 400.0, 1900.0), v1)
check("en calle = vencido + por vencer + al día", v1["vencido"] + v1["por_vencer"] + v1["al_dia"] == v1["en_calle"])
check("% vencido sobre lo que está en calle", v1["pct_vencido"] == 52.6, v1["pct_vencido"])
check("4 facturas con saldo (la pagada, el resto de 0,005 y el recibo no cuentan), de 1 cliente", (v1["facturas"], v1["clientes_con_deuda"]) == (4, 1), v1)
check("vendedor 1 no tiene saldo a favor", v1["a_favor"] == 0.0)
v4 = c[4]["cartera"]
check("vendedor 4: la factura sin vencimiento se considera de 30 días desde la emisión (vencida)",
      (v4["vencido"], v4["por_vencer"], v4["al_dia"], v4["en_calle"]) == (700.0, 0.0, 0.0, 700.0), v4)
check("vendedor 4: saldo a favor = el saldo contable negativo de DELTA (250), aparte de lo que está en calle",
      (v4["a_favor"], v4["en_calle"]) == (250.0, 700.0), v4)

cl1 = c[1]["clientes"]
check("clientes del vendedor 1: el que debe primero, después el que no debe; el inactivo sin deuda no se lista",
      [x["cuenta"] for x in cl1] == [10, 11], [x["cuenta"] for x in cl1])
alfa = cl1[0]
check("ALFA: saldo 1900 y vencido 1000", (alfa["nombre"], alfa["saldo"], alfa["vencido"]) == ("ALFA SRL", 1900.0, 1000.0), alfa)
check("sus facturas, la más vieja primero, con comprobante, fechas, total, saldo y días de atraso",
      alfa["facturas"][0] == {"comprobante": "FC B 0003-00000123", "emision": "2026-09-10", "vencimiento": "2026-10-10",
                              "total": 5000.0, "saldo": 1000.0, "dias_vencida": 13}, alfa["facturas"][0])
check("las facturas no vencidas tienen 0 días de atraso",
      [f["dias_vencida"] for f in alfa["facturas"]] == [13, 0, 0, 0], [f["dias_vencida"] for f in alfa["facturas"]])
check("el saldo del cliente es la suma de sus facturas", alfa["saldo"] == sum(f["saldo"] for f in alfa["facturas"]))
check("BETA no debe nada: saldo 0 y sin facturas", cl1[1] == {"cuenta": 11, "nombre": "BETA SA", "saldo": 0.0, "vencido": 0.0, "facturas": []}, cl1[1])
cl4 = c[4]["clientes"]
check("vendedor 4: el que debe, después el que tiene saldo a favor (en negativo)",
      [(x["cuenta"], x["saldo"]) for x in cl4] == [(20, 700.0), (13, -250.0)], [(x["cuenta"], x["saldo"]) for x in cl4])

print("=== cobrado por mes ===")
RC = ["TC", "NC", "FECHA", "TOTALL", "CHEQUES", "BANCO", "RETENCION", "VENDEDOR"]
recibos = pd.DataFrame([
    ("RC", 1, D(2026, 10, 5), 1000.0, 0.0, 0.0, 0.0, 1),     # vendedor 1: 600 en efectivo y 400 por transferencia (según placaja)
    ("RC", 2, D(2026, 9, 15), 500.0, 500.0, 0.0, 0.0, 4),    # vendedor 4: cheques, mes anterior
    ("RC", 3, D(2026, 10, 7), 300.0, 0.0, 300.0, 0.0, 4),    # vendedor 4: transferencia por el banco
    ("FC", 4, D(2026, 10, 8), 9999.0, 0.0, 0.0, 0.0, 1),     # una factura no es un cobro
    ("RC", 5, D(2024, 1, 5), 777.0, 0.0, 0.0, 0.0, 1),       # fuera de los 12 meses
], columns=RC)
caja = pd.DataFrame([
    ("CAJA", D(2026, 10, 5), "I", "RECIBO DE CLIENTES", 600.0, 1),
    ("TRANSF", D(2026, 10, 5), "I", "RECIBO DE CLIENTES", 400.0, 1),
], columns=lectura.COLUMNAS_CAJA)
cobr = vendedores.cobrado(recibos, caja, [1, 4], HOY)
o1, s1 = cobr[1]["2026-10"], cobr[1]["2026-09"]
check("vendedor 1, octubre: 1000 en 1 recibo, 600 efectivo y 400 transferencia",
      (o1["total"], o1["recibos"], o1["efectivo"], o1["transferencia"], o1["cheques"], o1["otros"]) == (1000.0, 1, 600.0, 400.0, 0.0, 0.0), o1)
check("octubre va de 1/10 a hoy", (o1["desde"], o1["hasta"]) == ("2026-10-01", "2026-10-23"), o1)
check("vendedor 1, septiembre: nada", (s1["total"], s1["recibos"]) == (0.0, 0))
check("vendedor 4, septiembre: 500 en cheques", (cobr[4]["2026-09"]["total"], cobr[4]["2026-09"]["cheques"]) == (500.0, 500.0), cobr[4]["2026-09"])
check("vendedor 4, octubre: 300 por transferencia del banco", (cobr[4]["2026-10"]["total"], cobr[4]["2026-10"]["transferencia"]) == (300.0, 300.0), cobr[4]["2026-10"])
check("cada vendedor trae los 12 meses", all(len(cobr[v]) == 12 for v in (1, 4)))
check("los recibos de otro vendedor y los de hace años no se mezclan", cobr[1]["2025-11"]["total"] == 0.0 and sum(x["total"] for x in cobr[1].values()) == 1000.0)
suma_octubre = sum(cobr[v]["2026-10"]["total"] for v in (1, 4))
general = recaudado.desglose(recibos, caja, D(2026, 10, 1), HOY)
check("la suma de los vendedores = el desglose general del mes", abs(suma_octubre - general["total"]) < 0.01, f"{suma_octubre} vs {general['total']}")

print("=== litros ===")
abmartic = pd.DataFrame({"CODART": ["L100", "L200"], "CODMEDIDA": ["1 lt", "4 lts"]})
clasificacion = pd.DataFrame({"articulo": ["L100", "L200"], "Clasificacion": ["Premium", "Standard"], "Artiprov": [None, None]})
ventas = pd.DataFrame([
    (D(2026, 10, 2), "FC", "L100", 10, 1),
    (D(2026, 10, 3), "FC", "L200", 5, 4),
    (D(2026, 10, 3), "FC", "L100", 2, 4),
    (D(2026, 9, 10), "FC", "L100", 7, 1),                  # mes anterior, dentro de "hasta el mismo día"
    (D(2026, 9, 30), "FC", "L100", 100, 1),                # mes anterior, después del día 23: no cuenta
    (D(2026, 10, 3), "FC", "L100", 1, 8),                  # un vendedor que no tiene clientes: igual aparece
    (D(2020, 1, 3), "FC", "L100", 1, 77),                  # hace años: su código no aparece
], columns=["FECHA", "TC", "MODELO", "U_VENDIDAS", "VENDNUMERO"])
p = calculo.periodos(HOY)
lt = vendedores.litros_de_cada_uno(ventas, abmartic, clasificacion, p, [1, 4])
check("vendedor 1: 10 L de Shell premium este mes", (lt[1]["mes"]["litros"], lt[1]["mes"]["premium"]) == (10.0, 10.0), lt[1]["mes"])
check("vendedor 4: 5 x 4 L + 2 L = 22 L, 2 premium", (lt[4]["mes"]["litros"], lt[4]["mes"]["premium"]) == (22.0, 2.0), lt[4]["mes"])
check("el mes anterior se compara hasta el mismo día", lt[1]["mes_anterior"]["litros"] == 7.0, lt[1]["mes_anterior"])
check("traen los tres proveedores", set(lt[1]["mes"]["por_proveedor"]) == set(litros.PROVEEDORES))
total_general = litros.periodo(ventas, abmartic, clasificacion, *p["mes"])["litros"]
check("la suma de los vendedores (con el 8 incluido) = el panel general", abs(lt[1]["mes"]["litros"] + lt[4]["mes"]["litros"] + 1.0 - total_general) < 0.01,
      f"{total_general}")

print("=== todo junto ===")
todo = vendedores.calcular(ventas, abmartic, clasificacion, ctacorr, clientes, recibos, caja, HOY, p)
check("trae la fecha y los vendedores con clave de texto; los códigos viejos no aparecen",
      todo["hoy"] == "2026-10-23" and sorted(todo["vendedores"]) == ["1", "4", "8"], sorted(todo["vendedores"]))
check("trae los períodos de los litros (mes y mes anterior hasta el mismo día), como el panel general",
      todo["periodos"] == {"mes": {"desde": "2026-10-01", "hasta": "2026-10-23"}, "mes_anterior": {"desde": "2026-09-01", "hasta": "2026-09-23"}}, todo["periodos"])
check("cada vendedor trae litros, cartera, cobrado y clientes", all(set(v) == {"litros", "cartera", "cobrado", "clientes"} for v in todo["vendedores"].values()))
check("el vendedor sin clientes ni deuda trae todo en cero", todo["vendedores"]["8"]["cartera"] == vendedores._cartera_vacia() and todo["vendedores"]["8"]["clientes"] == [])
check("es JSON (se guarda en la base)", len(json.dumps(todo)) > 100)
check("calculo.calcular_todo devuelve el panel general y el de los vendedores",
      callable(calculo.calcular_todo) and calculo.calcular_todo.__code__.co_argcount == 2)

print("=== sin datos ===")
vacio = vendedores.calcular(ventas.iloc[0:0], abmartic, clasificacion, ctacorr.iloc[0:0], clientes.iloc[0:0], recibos.iloc[0:0], caja.iloc[0:0], HOY, p)
check("sin nada no falla y no hay vendedores", vacio["vendedores"] == {}, vacio)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
