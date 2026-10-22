"""Lógica de deudores de Cuentas Corrientes (src/controllers/cuentas_corrientes_io.py).

Reglas que se fijan acá:
* Saldo = SALDO nativo de ctacorr de las facturas (FA/FC/FE) con saldo > 0,01.
  NO se recalcula con recibos/NC: el script original ignoraba los `CR` aplicados
  a una factura y la daba por impaga (p. ej. FE A-3-94 de la cuenta 482).
* `fecha_desde` filtra por la fecha de emisión de la factura (inclusive).
* Fecha "más vieja" = la factura más antigua CON saldo, no la más antigua a secas.

Correr desde la raíz:  python tests/verificar_cuentas_corrientes.py
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers.cuentas_corrientes_io import (
    COLUMNAS_CLAVE, COLUMNAS_DETALLE, COLUMNAS_SALIDA, calcular_deudores, detalle_facturas,
    descripcion_filtros, estado_mora, filtrar_deudores, parsear_monto, resumen_cartera, saldos_a_favor,
)

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def ctacorr(*filas):
    return pd.DataFrame(filas, columns=["TC", "CUENTA", "FECHA", "SALDO"]).assign(
        FECHA=lambda d: pd.to_datetime(d["FECHA"])
    )


clientes = pd.DataFrame({"CNUMERO": [1, 2, 3], "CNOMBRE": ["  DREAM SRL ", "ECO MINERA SA", "SIN MOVS"]})
DESDE = dt.date(2024, 1, 1)

print("=== solo facturas cuentan (FA/FC/FE); RC/NC/CR/ND se ignoran ===")
df = ctacorr(
    ("FC", 1, "2024-03-01", 100.0),
    ("FA", 1, "2024-04-01", 50.0),
    ("FE", 1, "2024-05-01", 25.0),
    ("RC", 1, "2024-06-01", -500.0),
    ("NC", 1, "2024-06-01", -500.0),
    ("CR", 1, "2024-06-01", -500.0),
    ("ND", 1, "2024-06-01", 999.0),
)
r = calcular_deudores(df, clientes, DESDE)
check("una fila para la cuenta 1", len(r) == 1)
check("suma solo FA+FC+FE = 175", r.iloc[0]["Saldo"] == 175.0, f"got {r.iloc[0]['Saldo']}")

print("=== facturas sin saldo no cuentan ===")
df = ctacorr(("FC", 1, "2024-01-10", 0.0), ("FC", 1, "2024-02-10", 0.01), ("FC", 1, "2024-03-10", 40.0))
r = calcular_deudores(df, clientes, DESDE)
check("ignora SALDO <= 0,01", r.iloc[0]["Saldo"] == 40.0, f"got {r.iloc[0]['Saldo']}")
check("la fecha más vieja es la de la factura CON saldo",
      r.iloc[0]["Factura más vieja"] == pd.Timestamp("2024-03-10"), f"got {r.iloc[0]['Factura más vieja']}")

print("=== cuenta sin ninguna factura con saldo no aparece ===")
df = ctacorr(("FC", 1, "2024-01-10", 0.0), ("FC", 2, "2024-01-10", 10.0))
r = calcular_deudores(df, clientes, DESDE)
check("solo la cuenta 2", list(r["Cuenta"]) == [2], f"got {list(r['Cuenta'])}")

print("=== fecha_desde: inclusive y excluye lo anterior ===")
df = ctacorr(
    ("FC", 1, "2023-12-31", 10.0),
    ("FC", 1, "2024-01-01", 20.0),
    ("FC", 1, "2024-06-01", 30.0),
)
r = calcular_deudores(df, clientes, dt.date(2024, 1, 1))
check("excluye 31/12/2023, incluye 01/01/2024", r.iloc[0]["Saldo"] == 50.0, f"got {r.iloc[0]['Saldo']}")
check("fecha más vieja = 01/01/2024", r.iloc[0]["Factura más vieja"] == pd.Timestamp("2024-01-01"))
r = calcular_deudores(df, clientes, dt.date(2023, 1, 1))
check("con corte anterior entra la de 2023", r.iloc[0]["Saldo"] == 60.0 and
      r.iloc[0]["Factura más vieja"] == pd.Timestamp("2023-12-31"))
r = calcular_deudores(df, clientes, dt.date(2025, 1, 1))
check("corte posterior a todo -> vacío", r.empty)

print("=== nombres ===")
df = ctacorr(("FC", 1, "2024-02-01", 10.0), ("FC", 99, "2024-02-01", 10.0))
r = calcular_deudores(df, clientes, DESDE).set_index("Cuenta")
check("nombre sin espacios sobrantes", r.loc[1, "Cliente"] == "DREAM SRL", repr(r.loc[1, "Cliente"]))
check("cuenta inexistente -> CLIENTE DESCONOCIDO", r.loc[99, "Cliente"] == "CLIENTE DESCONOCIDO")

print("=== tolerancia de datos sucios ===")
df = ctacorr((" fc ", 1, "2024-02-01", 10.0), ("FC", 1, "2024-03-01", None))
r = calcular_deudores(df, clientes, DESDE)
check("TC con espacios/minúsculas se normaliza", len(r) == 1 and r.iloc[0]["Saldo"] == 10.0)

print("=== forma de la salida ===")
check("columnas esperadas", list(r.columns) == COLUMNAS_SALIDA, str(list(r.columns)))
vacio = calcular_deudores(ctacorr(), clientes, DESDE)
check("vacío conserva columnas", vacio.empty and list(vacio.columns) == COLUMNAS_SALIDA)
df = ctacorr(("FC", 1, "2024-02-01", 10.0), ("FC", 2, "2024-02-01", 90.0), ("FC", 3, "2024-02-01", 50.0))
r = calcular_deudores(df, clientes, DESDE)
check("ordenado por saldo desc", list(r["Cuenta"]) == [2, 3, 1], str(list(r["Cuenta"])))
check("Saldo redondeado a 2 decimales",
      calcular_deudores(ctacorr(("FC", 1, "2024-02-01", 0.1), ("FC", 1, "2024-02-02", 0.2)), clientes, DESDE)
      .iloc[0]["Saldo"] == 0.3)

print("=== detalle de facturas de un cliente ===")


def comprobantes(*filas):
    return pd.DataFrame(
        filas, columns=["TC", "CLASE", "NROEST", "NC", "CUENTA", "FECHA", "TOTALL", "SALDO"]
    ).assign(FECHA=lambda d: pd.to_datetime(d["FECHA"]))


cc = comprobantes(
    ("FC", "A", "00003", 8808, 1, "2024-03-01", 500.0, 300.0),
    ("FE", "B", "00004", 12, 1, "2024-02-01", 200.0, 200.0),
    ("FC", "A", "00003", 9, 1, "2024-04-01", 100.0, 0.0),       # saldada
    ("RC", "X", "00001", 77, 1, "2024-05-01", -50.0, -50.0),    # no es factura
    ("FC", "A", "00003", 5, 1, "2023-06-01", 80.0, 80.0),       # anterior al corte
    ("FC", "A", "00003", 6, 2, "2024-03-05", 999.0, 999.0),     # otro cliente
)
d = detalle_facturas(cc, 1, DESDE)
check("columnas del detalle (visibles + clave)",
      list(d.columns) == COLUMNAS_DETALLE + COLUMNAS_CLAVE, str(list(d.columns)))
check("clave de la factura para reclamarla",
      list(d.iloc[0][COLUMNAS_CLAVE]) == ["FE", "B", 4, 12], str(list(d.iloc[0][COLUMNAS_CLAVE])))
check("solo facturas con saldo, del cliente y desde la fecha", len(d) == 2, f"got {len(d)}")
check("más vieja primero", list(d["Emisión"]) == [pd.Timestamp("2024-02-01"), pd.Timestamp("2024-03-01")])
check("formato del comprobante", list(d["Comprobante"]) == ["FE B 0004-00000012", "FC A 0003-00008808"],
      str(list(d["Comprobante"])))
check("total y saldo por factura", list(d["Total"]) == [200.0, 500.0] and list(d["Saldo"]) == [200.0, 300.0])

print("=== el detalle suma exactamente lo que muestra la grilla ===")
grilla = calcular_deudores(cc, clientes, DESDE).set_index("Cuenta")
check("sum(detalle) == saldo de la grilla", d["Saldo"].sum() == grilla.loc[1, "Saldo"],
      f"{d['Saldo'].sum()} vs {grilla.loc[1, 'Saldo']}")
grilla_f = calcular_deudores(cc, clientes, dt.date(2023, 1, 1)).set_index("Cuenta")
d_f = detalle_facturas(cc, 1, dt.date(2023, 1, 1))
check("idem con otra fecha de corte", d_f["Saldo"].sum() == grilla_f.loc[1, "Saldo"])

print("=== una fila por comprobante: no se agrupan duplicados del sistema ===")
dup = comprobantes(
    ("FC", "A", "00003", 8808, 1, "2026-02-23", 6007190.01, 6007190.01),
    ("FC", "A", "00003", 8808, 1, "2026-02-23", 6007190.01, 6007190.01),
)
check("las dos filas idénticas se ven", len(detalle_facturas(dup, 1, DESDE)) == 2)
mismo_nro = comprobantes(
    ("FC", "A", "00003", 9127, 1, "2026-04-20", 100.0, 40.0),
    ("FC", "A", "00003", 9127, 2, "2026-04-20", 70.0, 70.0),
)
check("mismo número en dos cuentas no se mezcla",
      list(detalle_facturas(mismo_nro, 2, DESDE)["Saldo"]) == [70.0])

print("=== bordes ===")
TODAS = COLUMNAS_DETALLE + COLUMNAS_CLAVE
check("cuenta inexistente -> vacío con columnas",
      detalle_facturas(cc, 999, DESDE).empty and list(detalle_facturas(cc, 999, DESDE).columns) == TODAS)
check("sin filas -> vacío con columnas", list(detalle_facturas(comprobantes(), 1, DESDE).columns) == TODAS)

print("=== estado de mora según antigüedad de la factura más vieja ===")
for dias, esperado in ((0, "En término"), (30, "En término"), (31, "Mora"), (60, "Mora"),
                       (61, "Mora crítica"), (400, "Mora crítica"), (-5, "En término")):
    check(f"{dias} días -> {esperado}", estado_mora(dias) == esperado, f"got {estado_mora(dias)}")

print("=== monto escrito a mano (saldo mínimo) ===")
for txt, esperado in (("", 0.0), ("   ", 0.0), ("1000", 1000.0), ("1.500.000", 1_500_000.0),
                      ("1.500,50", 1500.5), ("1500,5", 1500.5), ("$ 2.500", 2500.0), (" $2.500,00 ", 2500.0)):
    check(f"{txt!r} -> {esperado}", parsear_monto(txt) == esperado, f"got {parsear_monto(txt)}")
for txt in ("abc", "12,3,4", "1..2x"):
    try:
        parsear_monto(txt)
        check(f"{txt!r} rechazado", False)
    except ValueError as e:
        check(f"{txt!r} -> ValueError claro", "Monto inválido" in str(e), str(e))

print("=== filtros de la grilla ===")
HOY = dt.date(2026, 8, 1)
deu = pd.DataFrame({
    "Cuenta": [1, 2, 3, 4],
    "Cliente": ["DREAM SRL", "ECO MINERA SA", "Agropecuaria Los Manantiales", "SHERPA SAS"],
    "Saldo": [5_000_000.0, 900_000.0, 150_000.0, 40_000.0],
    "Factura más vieja": pd.to_datetime(["2026-07-25", "2026-06-20", "2026-03-01", "2025-01-10"]),
})   # antigüedades al 01/08/2026: 7, 42, 153, 568 días
cuentas = lambda d: list(d["Cuenta"])
check("sin filtros devuelve todo", cuentas(filtrar_deudores(deu, hoy=HOY)) == [1, 2, 3, 4])
check("texto: contiene, sin distinguir mayúsculas", cuentas(filtrar_deudores(deu, texto="eco min", hoy=HOY)) == [2])
check("texto: también por nº de cuenta", cuentas(filtrar_deudores(deu, texto="3", hoy=HOY)) == [3])
check("texto con espacios alrededor", cuentas(filtrar_deudores(deu, texto="  dream ", hoy=HOY)) == [1])
check("saldo mínimo inclusive", cuentas(filtrar_deudores(deu, saldo_min=900_000, hoy=HOY)) == [1, 2])
check("antigüedad > 30 días", cuentas(filtrar_deudores(deu, dias_min=30, hoy=HOY)) == [2, 3, 4])
check("antigüedad > 90 días", cuentas(filtrar_deudores(deu, dias_min=90, hoy=HOY)) == [3, 4])
check("filtros combinados (AND)", cuentas(filtrar_deudores(deu, saldo_min=100_000, dias_min=30, hoy=HOY)) == [2, 3])
check("sin coincidencias -> vacío con columnas",
      filtrar_deudores(deu, texto="zzz", hoy=HOY).empty and
      list(filtrar_deudores(deu, texto="zzz", hoy=HOY).columns) == list(deu.columns))
check("no modifica el DataFrame original", len(deu) == 4)

print("=== descripción de los filtros (se ve con el panel plegado) ===")
D = dt.date(2024, 1, 1)
check("sin filtros: solo la fecha", descripcion_filtros(D) == "Desde 01/01/2024", descripcion_filtros(D))
check("texto en blanco no cuenta", descripcion_filtros(D, texto="   ") == "Desde 01/01/2024")
check("saldo 0 y antigüedad 0 no cuentan", descripcion_filtros(D, saldo_min=0.0, dias_min=0) == "Desde 01/01/2024")
check("filtro de cliente", descripcion_filtros(D, texto="dream") == "Desde 01/01/2024 · filtros: cliente")
check("filtro de saldo", descripcion_filtros(D, saldo_min=1000) == "Desde 01/01/2024 · filtros: saldo mínimo")
check("filtro de antigüedad", descripcion_filtros(D, dias_min=60) == "Desde 01/01/2024 · filtros: antigüedad")
check("los tres, en orden fijo",
      descripcion_filtros(dt.date(2025, 3, 7), texto="x", saldo_min=1, dias_min=30)
      == "Desde 07/03/2025 · filtros: cliente, saldo mínimo, antigüedad")

print("=== resumen de cartera (KPIs) ===")
cc = comprobantes(
    ("FC", "A", "00003", 1, 1, "2026-07-25", 100.0, 100.0),    # 7 días   -> al día
    ("FC", "A", "00003", 2, 1, "2026-06-20", 200.0, 200.0),    # 42 días  -> mora
    ("FC", "A", "00003", 3, 2, "2026-03-01", 300.0, 300.0),    # 153 días -> crítica
    ("FC", "A", "00003", 4, 2, "2026-07-30", 400.0, 0.0),      # saldada
)
deu2 = calcular_deudores(cc, clientes, DESDE)
r = resumen_cartera(cc, deu2, DESDE, hoy=HOY)
check("saldo total = 600", r["saldo_total"] == 600.0, str(r["saldo_total"]))
check("2 clientes", r["clientes"] == 2)
check("mora (>30 d) a nivel factura = 500", r["mora"] == 500.0, str(r["mora"]))
check("crítica (>60 d) a nivel factura = 300", r["critica"] == 300.0, str(r["critica"]))
check("% crítica = 50", r["pct_critica"] == 50.0, str(r["pct_critica"]))
check("% mora = 83.33", abs(r["pct_mora"] - 83.33) < 0.01, str(r["pct_mora"]))
check("factura más antigua con saldo", r["mas_antigua_fecha"] == pd.Timestamp("2026-03-01") and
      r["mas_antigua_cliente"] == "ECO MINERA SA", f"{r['mas_antigua_fecha']} {r['mas_antigua_cliente']}")
vacio_r = resumen_cartera(comprobantes(), calcular_deudores(comprobantes(), clientes, DESDE), DESDE, hoy=HOY)
check("cartera vacía: ceros y sin división por cero",
      vacio_r["saldo_total"] == 0 and vacio_r["clientes"] == 0 and vacio_r["pct_critica"] == 0
      and vacio_r["mas_antigua_fecha"] is None and vacio_r["mas_antigua_cliente"] is None)

print("=== cuentas con saldo negativo (a favor del cliente): cuentan en el total, NO se listan ===")
# saldo contable de una cuenta = suma de TOTALL de todos sus movimientos (facturas +, recibos/NC -)
cn = comprobantes(
    ("FC", "A", "00003", 1, 1, "2026-03-01", 1000.0, 0.0),       # cuenta 1: debía 1000, pagó 1500 -> -500
    ("RC", "X", "00001", 10, 1, "2026-03-05", -1500.0, -500.0),
    ("FC", "A", "00003", 2, 2, "2026-07-25", 5000.0, 5000.0),    # cuenta 2: debe 5000 (positiva)
    ("FC", "A", "00003", 3, 3, "2026-03-01", 800.0, 0.0),        # cuenta 3: saldo cero
    ("RC", "X", "00001", 11, 3, "2026-03-02", -800.0, None),
    ("nc ", "A", "00003", 5, 4, "2026-04-01", -200.0, -200.0),   # cuenta 4: solo una NC sin aplicar -> -200 (TC con espacio/minúscula)
    ("FC", "A", "00003", 4, 5, "2026-07-30", 100.0, 100.0),      # cuenta 5: factura pendiente 100 + pago a cuenta 400 -> -300
    ("RC", "X", "00001", 12, 5, "2026-08-01", -400.0, None),     #   (ya figura en el panel por su factura pendiente)
    ("FC", "A", "00003", 6, 7, "2026-03-01", 1000.0, 1000.0),    # cuenta 7: vieja (153 días) -> mora crítica
    ("XX", "A", "00003", 7, 8, "2026-03-01", -999.0, -999.0),    # tipo de comprobante que no es contable: se ignora
)
dn = calcular_deudores(cn, clientes, DESDE)
check("el panel lista solo las cuentas con factura pendiente", sorted(dn["Cuenta"]) == [2, 5, 7], str(sorted(dn["Cuenta"])))
af = saldos_a_favor(cn, dn)
check("detecta las cuentas con saldo contable negativo que NO están en el panel", sorted(af.index) == [1, 4], str(sorted(af.index)))
check("sus importes (negativos)", af.loc[1] == -500.0 and af.loc[4] == -200.0, str(af.to_dict()))
check("una cuenta del panel no se descuenta dos veces (la 5 ya está por su factura)", 5 not in af.index)
check("cuentas en cero o con otros tipos de comprobante no cuentan", 3 not in af.index and 8 not in af.index)
check("sin movimientos -> vacío", saldos_a_favor(comprobantes(), calcular_deudores(comprobantes(), clientes, DESDE)).empty)

rn = resumen_cartera(cn, dn, DESDE, hoy=HOY)
check("saldo bruto = lo que muestra la tabla (5000+100+1000)", rn["saldo_bruto"] == 6100.0, str(rn["saldo_bruto"]))
check("a favor = -700 en 2 cuentas", rn["a_favor"] == -700.0 and rn["cuentas_a_favor"] == 2, f"{rn['a_favor']} / {rn['cuentas_a_favor']}")
check("SALDO TOTAL = bruto + saldos a favor = 5400", rn["saldo_total"] == 5400.0, str(rn["saldo_total"]))
check("la mora se mide contra la cartera BRUTA (no contra el neto)", rn["pct_critica"] == round(1000 * 100 / 6100, 2), str(rn["pct_critica"]))
check("la tabla no cambia: los saldos a favor no aparecen", len(dn) == 3 and (dn["Saldo"] > 0).all())
sin_negativos = resumen_cartera(cc, deu2, DESDE, hoy=HOY)
check("sin cuentas a favor el total no cambia", sin_negativos["a_favor"] == 0 and sin_negativos["cuentas_a_favor"] == 0
      and sin_negativos["saldo_total"] == sin_negativos["saldo_bruto"] == 600.0)
check("cartera vacía: ceros", vacio_r["a_favor"] == 0 and vacio_r["cuentas_a_favor"] == 0 and vacio_r["saldo_bruto"] == 0)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
