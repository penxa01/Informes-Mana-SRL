"""Registro de visitas de los vendedores, leído EN VIVO de una hoja de Google Sheets.

La hoja es ``config.VISITAS_HOJA`` ("Respuestas de formulario 1": donde cae el formulario)
de la planilla ``config.VISITAS_SHEET_ID``. Se consume por el endpoint ``gviz`` en JSON:

* **No se descarga ningún archivo ni se guarda copia**: cada lectura va a la planilla y vive
  solo en memoria. Sin internet no hay datos nuevos (la pantalla conserva lo que ya leyó).
* **No se unifican otras hojas**: las hojas mensuales las integra el usuario a mano.
* La planilla tiene que estar compartida como "cualquier persona con el enlace".

Quirks de ``gviz`` que importan:

* Las fechas llegan como ``Date(2026,9,15,9,21,17)`` con el **mes contado desde 0**.
* Si el nombre de la hoja no existe, Google devuelve igual **la primera hoja**, sin avisar:
  por eso se validan las columnas.

Sin Qt: todo se puede probar.
"""
import datetime as dt
import json
import re
import unicodedata
import urllib.parse
import urllib.request

import pandas as pd

from src.controllers import config

COLUMNAS = ["FECHA", "VENDEDOR", "CLIENTE", "NUEVO", "COMPRO", "OBSERVACION"]
TIMEOUT_SEG = 25

# encabezado de la hoja (normalizado) -> columna interna
_ENCABEZADOS = {
    "marca temporal": "FECHA", "fecha": "FECHA",
    "vendedor": "VENDEDOR",
    "nombre de cliente": "CLIENTE", "nombre cliente": "CLIENTE", "cliente": "CLIENTE",
    "cliente nuevo": "NUEVO",
    "compro": "COMPRO",
    "observacion": "OBSERVACION", "observaciones": "OBSERVACION",
}
_OBLIGATORIAS = ("FECHA", "VENDEDOR", "CLIENTE")   # lo demás es opcional (queda vacío)
_RE_FECHA_GVIZ = re.compile(r"Date\((\d+),(\d+),(\d+)(?:,(\d+),(\d+),(\d+)(?:,(\d+))?)?\)")


def normalizar_texto(valor):
    """Para buscar: sin acentos, sin mayúsculas, espacios simples. ``None`` -> ``''``."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return ""
    sin_acentos = "".join(c for c in unicodedata.normalize("NFKD", str(valor)) if not unicodedata.combining(c))
    return " ".join(sin_acentos.casefold().split())


def _limpiar(valor):
    """Texto tal cual lo escribió el usuario, sin espacios de más. ``None``/NaN -> ``''``."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return ""
    return " ".join(str(valor).split())


def _si_no(valor):
    n = normalizar_texto(valor)
    if n in ("si", "s", "yes", "y", "true", "1"):
        return "Sí"
    if n in ("no", "n", "false", "0"):
        return "No"
    return ""


def _fecha(valor):
    """Valor de una celda de fecha -> ``datetime`` o ``NaT``."""
    if isinstance(valor, str):
        m = _RE_FECHA_GVIZ.fullmatch(valor.strip())
        if m:
            a, mes, d, h, mi, s, ms = (int(g) if g else 0 for g in m.groups())
            return dt.datetime(a, mes + 1, d, h, mi, s, ms * 1000)       # gviz cuenta los meses desde 0
        return pd.to_datetime(valor, dayfirst=True, errors="coerce")    # fecha escrita como texto
    return pd.NaT


# ── lectura ──────────────────────────────────────────────────────────────────
def url_hoja(sheet_id=None, hoja=None):
    sheet_id = sheet_id or config.VISITAS_SHEET_ID
    hoja = hoja or config.VISITAS_HOJA
    return (f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
            f"?tqx=out:json&headers=1&sheet={urllib.parse.quote(hoja)}")


def leer_hoja(sheet_id=None, hoja=None, timeout=TIMEOUT_SEG, abrir=urllib.request.urlopen):
    """Texto crudo de la respuesta de Google (en memoria). ``OSError`` si no hay conexión."""
    pedido = urllib.request.Request(url_hoja(sheet_id, hoja), headers={"User-Agent": "InformesMana"})
    with abrir(pedido, timeout=timeout) as respuesta:
        return respuesta.read().decode("utf-8", errors="replace")


def parsear_hoja(texto):
    """Respuesta de ``gviz`` -> ``(DataFrame de COLUMNAS, filas repetidas descartadas)``.

    Descarta las filas vacías y las que tienen una fecha ilegible, y las copias exactas
    (un bloque pegado dos veces). Las visitas repetidas el mismo día a distinta hora se
    conservan. Ordena de la más reciente a la más vieja.
    """
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("La planilla respondió vacía.")
    m = re.search(r"setResponse\((.*)\)\s*;?\s*$", texto, re.S)
    if not m:
        raise ValueError("La respuesta no es de Google Sheets: la planilla no es de acceso público "
                         "(tiene que estar compartida con el enlace) o cambió el enlace.")
    try:
        cuerpo = json.loads(m.group(1))
    except ValueError:
        raise ValueError("La respuesta de la planilla llegó incompleta (JSON inválido). Probá de nuevo.")
    if cuerpo.get("status") != "ok":
        detalle = "; ".join(f"{e.get('reason', '')}: {e.get('message', '')}" for e in cuerpo.get("errors") or [])
        raise ValueError(f"Google no permitió leer la planilla (acceso denegado o hoja inexistente): {detalle}")

    tabla = cuerpo.get("table") or {}
    mapa = {}
    for i, col in enumerate(tabla.get("cols") or []):
        interna = _ENCABEZADOS.get(normalizar_texto(col.get("label")))
        if interna and interna not in mapa.values():
            mapa[i] = interna
    faltan = [c for c in _OBLIGATORIAS if c not in mapa.values()]
    if faltan:
        raise ValueError("La hoja no tiene las columnas de visitas (faltan: " + ", ".join(faltan)
                         + "). ¿Se cambió el nombre de la hoja? Google devuelve otra hoja si no la encuentra.")

    registros = []
    for fila in tabla.get("rows") or []:
        celdas = fila.get("c") or []
        reg = dict.fromkeys(COLUMNAS)
        for i, interna in mapa.items():
            celda = celdas[i] if i < len(celdas) else None
            reg[interna] = celda.get("v") if celda else None
        registros.append(reg)

    df = pd.DataFrame(registros, columns=COLUMNAS)
    df["FECHA"] = pd.to_datetime(df["FECHA"].map(_fecha), errors="coerce")
    df = df[df["FECHA"].notna()].copy()
    df["VENDEDOR"] = df["VENDEDOR"].map(_limpiar).str.title()
    for col in ("CLIENTE", "OBSERVACION"):
        df[col] = df[col].map(_limpiar)
    for col in ("NUEVO", "COMPRO"):
        df[col] = df[col].map(_si_no)
    df = df[(df["CLIENTE"] != "") | (df["VENDEDOR"] != "")]

    antes = len(df)
    df = df.drop_duplicates()
    repetidas = antes - len(df)
    df = df.sort_values("FECHA", ascending=False, kind="stable").reset_index(drop=True)
    return df, repetidas


def cargar_visitas(sheet_id=None, hoja=None, abrir=urllib.request.urlopen, ahora=dt.datetime.now):
    """Lee la hoja en vivo -> ``(df, info)``. ``info``: ``actualizado`` (hora de la lectura)
    y ``repetidas`` (filas copiadas descartadas). Los errores (``OSError``, ``ValueError``)
    suben: quien llama decide qué mostrar."""
    df, repetidas = parsear_hoja(leer_hoja(sheet_id, hoja, abrir=abrir))
    return df, {"actualizado": ahora(), "repetidas": repetidas}


# ── consulta ─────────────────────────────────────────────────────────────────
def _tope(fecha):
    """Primer instante DESPUÉS del día ``fecha`` (para incluir todo ese día)."""
    return pd.Timestamp(fecha).normalize() + pd.Timedelta(days=1)


def filtrar_visitas(visitas, texto="", vendedor=None, desde=None, hasta=None):
    """Filtros de la grilla (todos en AND). ``desde``/``hasta`` son días, inclusivos."""
    mascara = pd.Series(True, index=visitas.index)
    texto = normalizar_texto(texto)
    if texto:
        mascara &= visitas["CLIENTE"].map(normalizar_texto).str.contains(texto, regex=False)
    if vendedor:
        mascara &= visitas["VENDEDOR"] == vendedor
    if desde is not None:
        mascara &= visitas["FECHA"] >= pd.Timestamp(desde).normalize()
    if hasta is not None:
        mascara &= visitas["FECHA"] < _tope(hasta)
    return visitas[mascara].reset_index(drop=True)


def rango_preset(nombre, hoy=None):
    """Atajos de fecha: ``hoy``, ``ayer``, ``7dias`` (hoy y los 6 días anteriores) y ``mes`` (desde el día 1)."""
    hoy = hoy or dt.date.today()
    if nombre == "hoy":
        return hoy, hoy
    if nombre == "ayer":
        ayer = hoy - dt.timedelta(days=1)
        return ayer, ayer
    if nombre == "7dias":
        return hoy - dt.timedelta(days=6), hoy
    if nombre == "mes":
        return hoy.replace(day=1), hoy
    raise ValueError(f"Atajo de fecha desconocido: {nombre!r}")


def descripcion_filtros(desde, hasta, vendedor=None, texto="", hoy=None):
    """Una línea con lo aplicado, para mostrar con el panel de filtros oculto:
    ``Hoy · Jose Banco · cliente «gil»``."""
    hoy = hoy or dt.date.today()
    if desde is None and hasta is None:
        fechas = "Todas las fechas"
    elif desde is None:
        fechas = f"Hasta {hasta:%d/%m/%Y}"
    elif hasta is None:
        fechas = f"Desde {desde:%d/%m/%Y}"
    elif desde == hasta:
        fechas = "Hoy" if desde == hoy else "Ayer" if desde == hoy - dt.timedelta(days=1) else f"{desde:%d/%m/%Y}"
    else:
        fechas = f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}"
    partes = [fechas]
    if vendedor:
        partes.append(vendedor)
    if (texto or "").strip():
        partes.append(f"cliente «{texto.strip()}»")
    return " · ".join(partes)


def resumen_visitas(visitas):
    total = len(visitas)
    compraron = int((visitas["COMPRO"] == "Sí").sum())
    return {
        "visitas": total,
        "compraron": compraron,
        "pct_compra": round(compraron * 100 / total, 1) if total else 0.0,
        "nuevos": int((visitas["NUEVO"] == "Sí").sum()),
        "clientes": int(visitas["CLIENTE"].map(normalizar_texto).nunique()),
    }


def ultimo_dia(visitas, hasta=None):
    """Último día con visitas (opcionalmente hasta ``hasta``, inclusive), o ``None``."""
    sub = visitas if hasta is None else visitas[visitas["FECHA"] < _tope(hasta)]
    return sub["FECHA"].max().date() if len(sub) else None
