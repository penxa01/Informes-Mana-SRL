"""Actualización de la base de ventas sin reiniciar (src/controllers/ventas_io.py).

Reglas:
* Solo se recarga si cambió fachist.DBF (tamaño, fecha de modificación o nº de registros).
  Si no cambió, no se lee nada y el resultado es (None, firma): la UI no debe rehacer informes.
* Si la base no responde (red caída), el error sube: la UI conserva los datos que ya tenía.
* El intervalo del refresco automático es configurable y tolera valores absurdos.

Correr desde la raíz:  python tests/verificar_ventas_refresh.py
"""
import datetime as dt
import os
import struct
import sys
import tempfile
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers.ventas_io import (
    INTERVALO_DEFECTO_MIN, actualizar_si_cambio, firma_ventas, minutos_refresco, texto_estado_ventas,
)

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def dbf_falso(carpeta, n_reg, relleno=0, nombre="fachist.DBF"):
    """Archivo con cabecera DBF mínima: bytes 4..7 = nº de registros (little-endian)."""
    ruta = os.path.join(carpeta, nombre)
    cab = bytearray(32)
    cab[4:8] = struct.pack("<I", n_reg)
    with open(ruta, "wb") as fh:
        fh.write(bytes(cab) + b"x" * relleno)
    return ruta


print("=== firma de fachist.DBF ===")
with tempfile.TemporaryDirectory() as tmp:
    ruta = dbf_falso(tmp, 100, relleno=500)
    f1 = firma_ventas(ruta)
    check("la firma trae tamaño, fecha y nº de registros", set(f1) == {"size", "mtime", "n_reg"}, str(f1))
    check("nº de registros leído de la cabecera", f1["n_reg"] == 100)
    check("el mismo archivo da la misma firma", firma_ventas(ruta) == f1)

    dbf_falso(tmp, 101, relleno=500)                       # misma medida, otro nº de registros
    check("cambia el nº de registros -> otra firma", firma_ventas(ruta) != f1)
    dbf_falso(tmp, 100, relleno=900)                       # otro tamaño
    check("cambia el tamaño -> otra firma", firma_ventas(ruta) != f1)
    dbf_falso(tmp, 100, relleno=500)
    ahora = time.time()
    os.utime(ruta, (ahora + 120, ahora + 120))             # misma medida y registros, otra fecha
    check("cambia la fecha de modificación -> otra firma", firma_ventas(ruta) != f1)

    try:
        firma_ventas(os.path.join(tmp, "no_existe.DBF"))
        check("archivo inexistente -> OSError", False)
    except OSError:
        check("archivo inexistente -> OSError (la UI conserva lo que tenía)", True)

print("=== actualizar_si_cambio ===")
DF = pd.DataFrame({"FECHA": pd.to_datetime(["2026-01-05"]), "TC": ["FC"]})
llamadas = []


def leer():
    llamadas.append(1)
    return DF


firma_a = {"size": 10, "mtime": 1, "n_reg": 3}
firma_b = {"size": 20, "mtime": 2, "n_reg": 4}

df, firma = actualizar_si_cambio(None, firma_fn=lambda: firma_a, leer_fn=leer)
check("primera carga (sin firma previa): lee", df is DF and firma == firma_a and len(llamadas) == 1)

llamadas.clear()
df, firma = actualizar_si_cambio(firma_a, firma_fn=lambda: dict(firma_a), leer_fn=leer)
check("misma firma: NO lee y devuelve (None, firma)", df is None and firma == firma_a and not llamadas)

df, firma = actualizar_si_cambio(firma_a, firma_fn=lambda: firma_b, leer_fn=leer)
check("firma distinta: lee y devuelve la firma nueva", df is DF and firma == firma_b and len(llamadas) == 1)


def red_caida():
    raise OSError("la ruta de red no está disponible")


llamadas.clear()
try:
    actualizar_si_cambio(firma_a, firma_fn=red_caida, leer_fn=leer)
    check("red caída: el error sube", False)
except OSError:
    check("red caída: el error sube y no se lee nada", not llamadas)

print("=== texto de la barra de estado ===")
grande = pd.DataFrame({"FECHA": pd.to_datetime(["2014-02-28", "2026-10-15"] * 77_000)})
t = texto_estado_ventas(grande, dt.datetime(2026, 10, 16, 14, 7))
check("filas con separador de miles, años y hora", t == "ventas: 154.000 filas · 2014→2026 · act. 14:07", t)
check("sin columna FECHA no rompe", texto_estado_ventas(pd.DataFrame({"X": [1, 2]}), dt.datetime(2026, 1, 1, 9, 5))
      == "ventas: 2 filas · act. 09:05")
check("vacío", texto_estado_ventas(pd.DataFrame({"FECHA": pd.to_datetime([])}), dt.datetime(2026, 1, 1, 9, 5))
      == "ventas: 0 filas · act. 09:05")

print("=== intervalo del refresco automático ===")
check("por defecto 15 minutos", INTERVALO_DEFECTO_MIN == 15)
for valor, esperado in ((None, 15), ("", 15), ("5", 5), (" 30 ", 30), ("abc", 15), ("0", 15), ("-3", 15), ("2.5", 15),
                        ("1", 1), ("999", 15)):
    r = minutos_refresco(valor)
    check(f"{valor!r} -> {esperado}", r == esperado, str(r))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
