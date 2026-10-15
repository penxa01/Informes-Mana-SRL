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

from src.controllers.cuentas_corrientes_io import COLUMNAS_SALIDA, calcular_deudores

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

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
