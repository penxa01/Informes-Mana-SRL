"""Regresión del parseo de fechas de los filtros (src/ui/fechas.py).

Bug original en `PaginaMargen._parse_fecha` (y el mismo patrón en
`PaginaLitros._rango_extremo`): `"01/07/".split("/")` -> ['01','07',''] ->
int('') -> "invalid literal for int() with base 10: ''" filtrado crudo al
QMessageBox. Ahora ambos delegan en `parsear_fecha`, tolerante.

Correr desde la raíz:  python tests/verificar_margen_fecha.py
"""
import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.fechas import parsear_fecha

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


anio = dt.date.today().year

print("=== válidas / tolerables (no deben tirar ValueError) ===")
esperado = {
    "01/07": dt.date(anio, 7, 1),
    "01/07/": dt.date(anio, 7, 1),        # la barra de más: el bug reportado
    "/01/07": dt.date(anio, 7, 1),
    "01//07": dt.date(anio, 7, 1),
    " 1 / 7 ": dt.date(anio, 7, 1),
    "1/7": dt.date(anio, 7, 1),
    "01-07": dt.date(anio, 7, 1),
    "01.07": dt.date(anio, 7, 1),
    "30/07": dt.date(anio, 7, 30),
    "01/07/25": dt.date(2025, 7, 1),
    "01/07/2025": dt.date(2025, 7, 1),
}
for txt, fecha in esperado.items():
    try:
        r = parsear_fecha(txt, fin=False)
        check(f"{txt!r} -> {fecha}", r.date() == fecha, f"got {r.date()}")
    except ValueError as e:
        check(f"{txt!r} parsea sin error", False, str(e))

print("=== hora según 'fin' ===")
check("fin=False -> 00:00:00", parsear_fecha("01/07", fin=False).time() == dt.time(0, 0, 0))
check("fin=True  -> 23:59:59", parsear_fecha("01/07", fin=True).time() == dt.time(23, 59, 59))

print("=== inválidas (ValueError con mensaje claro, sin 'int()') ===")
for txt in ["", "abc", "01/foo", "13/45", "99/99/99", "1/2/3/4"]:
    try:
        r = parsear_fecha(txt, fin=False)
        check(f"{txt!r} rechazada", False, f"parseó a {r}")
    except ValueError as e:
        msg = str(e)
        check(f"{txt!r} -> mensaje claro", "Fecha inválida" in msg and "int()" not in msg, msg)

print("=== las páginas delegan en parsear_fecha (no reimplementan el split) ===")
from src.ui.paginas import margen as _m, litros as _l
check("margen.py importa parsear_fecha", "parsear_fecha" in dir(_m))
check("litros.py importa parsear_fecha", "parsear_fecha" in dir(_l))
src_margen = inspect.getsource(_m.PaginaMargen._parse_fecha)
check("PaginaMargen._parse_fecha delega", "parsear_fecha" in src_margen and 'split("/")' not in src_margen)
src_litros = inspect.getsource(_l.PaginaLitros._rango_extremo)
check("PaginaLitros._rango_extremo delega", "parsear_fecha" in src_litros and 'split("/")' not in src_litros)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
