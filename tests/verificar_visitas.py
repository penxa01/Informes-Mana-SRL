"""Registro de visitas (src/controllers/visitas_io.py).

Los datos se leen EN VIVO de UNA hoja de Google Sheets ("Respuestas de formulario 1", donde
cae el formulario de los vendedores) por el endpoint gviz/JSON. No se descarga ningún archivo,
no se guarda ninguna copia y no se unifican otras hojas (eso lo hace el usuario).

Quirks reales que se cubren acá:
* Las fechas vienen como ``Date(2026,9,15,9,21,17)`` con el MES CONTADO DESDE 0.
* Si el nombre de la hoja no existe Google devuelve igual la PRIMERA hoja, sin avisar:
  por eso se validan las columnas.
* Datos a mano: "Si"/"Sí", espacios de más, filas vacías, bloques pegados dos veces.

Correr desde la raíz:  python tests/verificar_visitas.py
"""
import datetime as dt
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers.visitas_io import (
    COLUMNAS, cargar_visitas, descripcion_filtros, filtrar_visitas, leer_hoja, normalizar_texto, parsear_hoja,
    rango_preset, resumen_visitas, ultimo_dia, url_hoja,
)

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def D(d, h=9, m=0, s=0, mes=10):
    return dt.datetime(2026, mes, d, h, m, s)


def celda(v):
    """Celda como la arma gviz."""
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return {"v": f"Date({v.year},{v.month - 1},{v.day},{v.hour},{v.minute},{v.second})"}
    return {"v": v}


COLS_FORM = [("Marca temporal", "datetime"), ("Vendedor", "string"), ("Nombre de Cliente", "string"),
             ("Cliente nuevo", "string"), ("Compro", "string"), ("Observacion", "string")]


def gviz(filas, cols=COLS_FORM, status="ok"):
    tabla = {"cols": [{"id": chr(65 + i), "label": lab, "type": tipo} for i, (lab, tipo) in enumerate(cols)],
             "rows": [{"c": [celda(v) for v in fila]} for fila in filas]}
    cuerpo = {"version": "0.6", "reqId": "0", "status": status, "sig": "1", "table": tabla}
    return "/*O_o*/\ngoogle.visualization.Query.setResponse(" + json.dumps(cuerpo) + ");"


FILAS = [
    [D(15, 9, 21, 17), "Jose Banco", "Gigantino ", "No", "No", "Pagó "],
    [D(16, 10, 5, 0), "Matias Baratta ", "María  Pérez", "Si", "Sí", None],
    [D(16, 10, 5, 0), "Matias Baratta", "María Pérez", "Si", "Sí", None],     # copia exacta (tras limpiar espacios)
    [None, None, None, None, None, None],                                      # fila vacía
    [D(16, 17, 0, 1), "Jose Banco", "Rojas", "No", "No", "Volvió"],
    [D(16, 9, 0, 5), "Jose Banco", "Rojas", "No", "Sí", "Compró"],             # mismo cliente y día, otra hora: legítima
    [D(17, 9, 41, 12), "Jose Banco", "Sin datos extra", None, "No", None],     # "Cliente nuevo" vacío
]

print("=== parseo de la hoja ===")
df, repetidas = parsear_hoja(gviz(FILAS))
check("columnas normalizadas", list(df.columns) == COLUMNAS, str(list(df.columns)))
check("descarta la fila vacía y la copia exacta", len(df) == 5 and repetidas == 1, f"{len(df)} filas, {repetidas} repetidas")
check("conserva las visitas repetidas el mismo día a otra hora", (df["CLIENTE"] == "Rojas").sum() == 2)
check("más reciente primero", df["FECHA"].is_monotonic_decreasing)
check("FECHA es datetime", str(df["FECHA"].dtype).startswith("datetime64"))
check("el mes de gviz (0-based) se interpreta bien: Date(2026,9,15) = 15/10/2026",
      df["FECHA"].min() == D(15, 9, 21, 17) and df["FECHA"].min().month == 10, str(df["FECHA"].min()))
check("vendedor sin espacios sobrantes", set(df["VENDEDOR"]) == {"Jose Banco", "Matias Baratta"}, str(set(df["VENDEDOR"])))
check("cliente sin espacios sobrantes ni dobles", {"María Pérez", "Gigantino"} <= set(df["CLIENTE"]))
check("'Si' y 'Sí' se unifican en 'Sí'", (df["NUEVO"] == "Sí").sum() == 1 and set(df["NUEVO"]) <= {"Sí", "No", ""})
check("COMPRO normalizado", (df["COMPRO"] == "Sí").sum() == 2 and set(df["COMPRO"]) <= {"Sí", "No", ""})
check("'Cliente nuevo' vacío queda vacío (no se inventa)", (df["NUEVO"] == "").sum() == 1)
check("observación vacía -> '' (texto, nunca None/NaN)", (df["OBSERVACION"] == "").sum() == 2 and df["OBSERVACION"].map(type).eq(str).all())
check("observación recortada", "Pagó" in set(df["OBSERVACION"]))

print("=== fechas poco comunes ===")
solo_fecha = gviz([[None, "Jose Banco", "SoloDia", "No", "No", None]], cols=[("Marca temporal", "date")] + COLS_FORM[1:])
solo_fecha = solo_fecha.replace('null', '{"v": "Date(2026,9,5)"}', 1)
t, _ = parsear_hoja(solo_fecha)
check("fecha sin hora: Date(2026,9,5) = 05/10/2026 00:00", len(t) == 1 and t["FECHA"].iloc[0] == dt.datetime(2026, 10, 5), str(t["FECHA"].tolist()))

texto = gviz([["05/10/2026 10:30:00", "Jose Banco", "Texto", "No", "No", None], ["no es fecha", "Jose Banco", "Basura", "No", "No", None]],
             cols=[("Marca temporal", "string")] + COLS_FORM[1:])
t, _ = parsear_hoja(texto)
check("fecha escrita como texto (dd/mm/aaaa) se interpreta; la ilegible se descarta",
      list(t["CLIENTE"]) == ["Texto"] and t["FECHA"].iloc[0] == dt.datetime(2026, 10, 5, 10, 30), str(t.to_dict("list")))

print("=== validaciones de la respuesta ===")


def falla(texto, fragmento):
    try:
        parsear_hoja(texto)
        return False, "no falló"
    except ValueError as e:
        return fragmento in str(e).lower(), str(e)


ok, msg = falla("<!DOCTYPE html><html><body>Iniciar sesión</body></html>", "público")
check("HTML de login (planilla privada) -> ValueError que lo explica", ok, msg)
ok, msg = falla("", "vacía")
check("respuesta vacía", ok, msg)
error_google = ('/*O_o*/\ngoogle.visualization.Query.setResponse({"version":"0.6","status":"error",'
                '"errors":[{"reason":"access_denied","message":"sin permiso"}]});')
ok, msg = falla(error_google, "acceso")
check("status error de Google -> ValueError con el motivo", ok and "sin permiso" in msg, msg)
ok, msg = falla("/*O_o*/\ngoogle.visualization.Query.setResponse({truncado", "respuesta")
check("JSON cortado -> ValueError", ok, msg)
ok, msg = falla(gviz([["a", "b"]], cols=[("x", "string"), ("y", "string")]), "columnas")
check("hoja equivocada (columnas que no son de visitas) -> ValueError que lo explica", ok, msg)
ok, msg = falla(gviz([[D(1), "Jose Banco", "Rojas"]], cols=COLS_FORM[:3]), "")
check("con solo Fecha/Vendedor/Cliente alcanza (lo demás es opcional)", not ok and "no falló" in msg, msg)
mini, _ = parsear_hoja(gviz([[D(1), "Jose Banco", "Rojas"]], cols=COLS_FORM[:3]))
check("columnas opcionales ausentes quedan vacías", mini[["NUEVO", "COMPRO", "OBSERVACION"]].eq("").all(axis=None))

print("=== búsqueda sin acentos ni mayúsculas ===")
check("normalizar_texto", normalizar_texto("  María   PÉREZ ") == "maria perez", repr(normalizar_texto("  María   PÉREZ ")))
check("normalizar_texto(None)", normalizar_texto(None) == "")

print("=== filtros ===")
cl = lambda d_: sorted(d_["CLIENTE"])
check("sin filtros devuelve todo", len(filtrar_visitas(df)) == 5)
check("cliente: contiene, sin acentos ni mayúsculas", cl(filtrar_visitas(df, texto="maria")) == ["María Pérez"])
check("cliente: espacios alrededor", cl(filtrar_visitas(df, texto="  roja ")) == ["Rojas", "Rojas"])
check("cliente: sin coincidencias -> vacío con columnas",
      filtrar_visitas(df, texto="zzz").empty and list(filtrar_visitas(df, texto="zzz").columns) == COLUMNAS)
check("vendedor", set(filtrar_visitas(df, vendedor="Matias Baratta")["VENDEDOR"]) == {"Matias Baratta"})
check("un día: desde == hasta, incluye todo el día (hasta las 23:59:59)",
      len(filtrar_visitas(df, desde=dt.date(2026, 10, 16), hasta=dt.date(2026, 10, 16))) == 3)
check("rango inclusivo en ambos extremos", len(filtrar_visitas(df, desde=dt.date(2026, 10, 15), hasta=dt.date(2026, 10, 16))) == 4)
check("solo desde", len(filtrar_visitas(df, desde=dt.date(2026, 10, 17))) == 1)
check("solo hasta", len(filtrar_visitas(df, hasta=dt.date(2026, 10, 15))) == 1)
check("combinados (AND)", cl(filtrar_visitas(df, texto="roja", vendedor="Jose Banco", desde=dt.date(2026, 10, 16),
                                             hasta=dt.date(2026, 10, 16))) == ["Rojas", "Rojas"])
check("no modifica el original", len(df) == 5)

print("=== resumen y último día ===")
r = resumen_visitas(df)
check("visitas / compraron / nuevos", (r["visitas"], r["compraron"], r["nuevos"]) == (5, 2, 1), str(r))
check("% de compra", r["pct_compra"] == round(2 * 100 / 5, 1), str(r["pct_compra"]))
check("clientes distintos (Rojas cuenta una vez)", r["clientes"] == 4, str(r["clientes"]))
vacio = resumen_visitas(filtrar_visitas(df, texto="zzz"))
check("resumen vacío: ceros, sin división por cero",
      vacio == {"visitas": 0, "compraron": 0, "pct_compra": 0.0, "nuevos": 0, "clientes": 0}, str(vacio))
check("último día con visitas", ultimo_dia(df) == dt.date(2026, 10, 17), str(ultimo_dia(df)))
check("último día de un df vacío -> None", ultimo_dia(filtrar_visitas(df, texto="zzz")) is None)
check("último día con tope", ultimo_dia(df, hasta=dt.date(2026, 10, 16)) == dt.date(2026, 10, 16))

print("=== atajos de fecha ===")
HOY = dt.date(2026, 10, 17)
for nombre, esperado in (("hoy", (HOY, HOY)), ("ayer", (dt.date(2026, 10, 16),) * 2),
                         ("7dias", (dt.date(2026, 10, 11), HOY)), ("mes", (dt.date(2026, 10, 1), HOY))):
    check(f"atajo '{nombre}'", rango_preset(nombre, HOY) == esperado, str(rango_preset(nombre, HOY)))
check("'7dias' cruza de mes", rango_preset("7dias", dt.date(2026, 11, 3)) == (dt.date(2026, 10, 28), dt.date(2026, 11, 3)))
check("'ayer' el 1° del mes", rango_preset("ayer", dt.date(2026, 11, 1)) == (dt.date(2026, 10, 31),) * 2)
try:
    rango_preset("siempre", HOY)
    check("atajo desconocido -> ValueError", False)
except ValueError:
    check("atajo desconocido -> ValueError", True)

print("=== resumen de filtros (se ve con el panel oculto) ===")
f = lambda *a, **k: descripcion_filtros(*a, hoy=HOY, **k)
check("hoy", f(HOY, HOY) == "Hoy", f(HOY, HOY))
check("ayer", f(dt.date(2026, 10, 16), dt.date(2026, 10, 16)) == "Ayer")
check("otro día", f(dt.date(2026, 10, 5), dt.date(2026, 10, 5)) == "05/10/2026")
check("rango", f(dt.date(2026, 10, 1), HOY) == "01/10/2026 – 17/10/2026")
check("sin fechas", f(None, None) == "Todas las fechas")
check("solo desde / solo hasta", f(dt.date(2026, 10, 1), None) == "Desde 01/10/2026" and f(None, HOY) == "Hasta 17/10/2026")
check("con vendedor y cliente", f(HOY, HOY, vendedor="Jose Banco", texto="  gil ") == "Hoy · Jose Banco · cliente «gil»")
check("cliente en blanco no cuenta", f(HOY, HOY, texto="   ") == "Hoy")

print("=== lectura en vivo (sin archivos) ===")
url = url_hoja("ABC123", "Respuestas de formulario 1")
check("URL gviz con la hoja codificada, JSON y una fila de encabezado",
      url.startswith("https://docs.google.com/spreadsheets/d/ABC123/gviz/tq?")
      and "tqx=out:json" in url and "headers=1" in url and "sheet=Respuestas%20de%20formulario%201" in url, url)


class RespuestaFalsa:
    def __init__(self, cuerpo): self._c = cuerpo.encode("utf-8")
    def read(self): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False


pedidos = []


def abrir_ok(req, timeout=None):
    pedidos.append((getattr(req, "full_url", req), timeout))
    return RespuestaFalsa(gviz(FILAS))


texto_leido = leer_hoja("ABC123", "Hoja", abrir=abrir_ok)
check("leer_hoja devuelve el texto y usa timeout", "setResponse" in texto_leido and pedidos[0][1] is not None, str(pedidos[0][1]))


def sin_red(req, timeout=None):
    raise OSError("sin conexión")


try:
    leer_hoja("ABC123", "Hoja", abrir=sin_red)
    check("sin red -> OSError", False)
except OSError:
    check("sin red -> OSError (la pantalla conserva lo que ya tenía)", True)

antes = set(os.listdir(os.getcwd()))
d2, info = cargar_visitas("ABC123", "Hoja", abrir=abrir_ok, ahora=lambda: dt.datetime(2026, 10, 17, 11, 30))
check("cargar_visitas devuelve datos e info", len(d2) == 5 and info["repetidas"] == 1, str(info))
check("info trae la hora de la lectura", info["actualizado"] == dt.datetime(2026, 10, 17, 11, 30))
check("no escribe nada en disco (ni copias ni caché)", set(os.listdir(os.getcwd())) == antes)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
