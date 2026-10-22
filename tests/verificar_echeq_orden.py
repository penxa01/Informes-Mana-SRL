"""Regresión: ordenar la tabla de E-Cheques por el encabezado.

Bug: con `setSortingEnabled(True)` y `QTableWidgetItem` común, Qt compara el
texto visible → "31/05/2026" < "03/12/2025" como string (ordena por el día).
Ahora cada celda lleva una clave tipada en UserRole (fecha/número/texto real).

Correr desde la raíz:  python tests/verificar_echeq_orden.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.Views.Echeq.EcheqDBF import EcheqWindow, echeq_io

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


app = widget.QApplication([])

df = pd.DataFrame({c: "" for c in echeq_io.COLUMNAS}, index=range(5))
df["Nro de Cheque"] = ["805", "90031258", "77", "1200", "9"]
df["Echeq id"] = ["RPQ2", "GOW9", "AAA1", "ZZZ9", "MMM5"]
df["Pagador Nombre Apellido/Razón Social"] = ["Zeta SA", "alfa srl", "Mtz", "beta", "Omega"]
df["Monto"] = ["$ 1.540.306,00", "$ 90.000,00", "$ 2.000.000,00", "$ 425.000,00", "$ 12,50"]
df["Fecha de Pago"] = ["31/05/2026", "03/12/2025", "01/01/2026", "15/07/2025", "28/02/2026"]
df["Fecha de Emisión"] = ["24/02/2026", "09/03/2026", "31/12/2025", "15/01/2025", "05/05/2026"]
df["Estado"] = ["Activo", "Rechazado", "Activo", "Emitido Pendiente", "Activo"]

w = EcheqWindow()
w.df = df
w.mostrar_en_tabla(df)
app.processEvents()
t = w.tabla_echeq


def col(nombre):
    return (["#"] + w.campos_tabla).index(nombre)


def valores(c):
    return [t.item(r, c).text() for r in range(t.rowCount())]


def ordenar(nombre, asc=True):
    c = col(nombre)
    t.sortItems(c, core.Qt.AscendingOrder if asc else core.Qt.DescendingOrder)
    app.processEvents()
    return valores(c)


print("=== Fecha de Emisión ===")
asc = ordenar("Fecha de Emisión", asc=True)
print("   asc:", asc)
esperado = ["15/01/2025", "31/12/2025", "24/02/2026", "09/03/2026", "05/05/2026"]
check("Fecha de Emisión ASC cronológica", asc == esperado, f"{asc}")
desc = ordenar("Fecha de Emisión", asc=False)
check("Fecha de Emisión DESC = reverso", desc == esperado[::-1], f"{desc}")
check("etiqueta 'Orden:' actualizada", "Fecha de Emisión" in w._orden_lbl.text() and "DESC" in w._orden_lbl.text(), w._orden_lbl.text())

print("=== Fecha de Pago ===")
asc = ordenar("Fecha de Pago", asc=True)
esperado_p = ["15/07/2025", "03/12/2025", "01/01/2026", "28/02/2026", "31/05/2026"]
check("Fecha de Pago ASC cronológica", asc == esperado_p, f"{asc}")

print("=== Monto (numérico, no string) ===")
asc = ordenar("Monto", asc=True)
montos_val = [float(v.replace("$", "").replace(".", "").replace(",", ".").strip()) for v in asc]
check("Monto ASC creciente", montos_val == sorted(montos_val), f"{montos_val}")
check("Monto más chico primero", montos_val[0] == 12.5, str(montos_val[0]))

print("=== Nro de Cheque (numérico) ===")
asc = ordenar("Nro de Cheque", asc=True)
check("Nro de Cheque ASC numérico", asc == ["9", "77", "805", "1200", "90031258"], f"{asc}")

print("=== Pagador (texto, case-insensitive) ===")
asc = ordenar("Pagador Nombre Apellido/Razón Social", asc=True)
check("Pagador ASC alfabético sin importar mayúsculas",
      asc == ["alfa srl", "beta", "Mtz", "Omega", "Zeta SA"], f"{asc}")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
