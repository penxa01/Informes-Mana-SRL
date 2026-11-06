"""Lógica pura del panel de control (sin Qt ni base de datos): formatos, filtro de productos,
litros por proveedor, deltas, cobranzas. Es la misma lógica que `movil/pwa/js/panel-comun.js` y
`cobranzas.js`, así las dos pantallas muestran lo mismo.

Los datos llegan hechos desde el servidor (ver `panel_io.py`); acá solo se arman los textos y las
cifras que se dibujan.
"""
import math
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

# Colores de las series: los mismos que las variables de estilos.css del celular.
COLORES = {
    "azul": "#2640dc",
    "ambar": "#f59e0b",
    "verde": "#059669",
    "violeta": "#7c3aed",
    "gris": "#94a3b8",
}

PROVEEDORES = [("SHELL", "Shell"), ("VALVOLINE", "Valvoline"), ("OTROS", "Otros")]

# (clave del servidor, nombre, color, ¿se muestra aunque sea 0?). Retenciones y Otros solo aparecen si hay algo:
# «Otros» es lo que no se pudo clasificar y no tiene que quedar escondido.
MEDIOS_DE_COBRO = [
    ("efectivo", "Efectivo", COLORES["verde"], True),
    ("transferencia", "Transferencia", COLORES["azul"], True),
    ("cheques", "Cheques", COLORES["violeta"], True),
    ("retenciones", "Retenciones", COLORES["gris"], False),
    ("otros", "Otros", COLORES["ambar"], False),
]

MAXIMO_RESULTADOS = 40


# ── formatos ─────────────────────────────────────────────────────────────────
def numero(n, decimales=0):
    """1234.5 -> '1.234,5'. Redondea .5 hacia afuera, como el navegador (no al par, como `round`)."""
    cuantos = Decimal(1).scaleb(-decimales)
    d = Decimal(repr(float(n))).quantize(cuantos, rounding=ROUND_HALF_UP)
    if d == 0:
        d = abs(d)
    texto = f"{d:,.{decimales}f}"
    return texto.replace(",", "@").replace(".", ",").replace("@", ".")


def dinero(v):
    """$ 89,8 M / $ 850 mil / $ 1.200."""
    if abs(v) >= 1e6:
        return f"$ {numero(v / 1e6, 1)} M"
    if abs(v) >= 1e4:
        return f"$ {numero(v / 1e3, 0)} mil"
    return f"$ {numero(v)}"


def pesos(v):
    return f"$ {numero(v)}"


def pesos_exactos(v):
    return f"$ {numero(v, 2)}"


def plural(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def texto_porcentaje(valor, total):
    if not total or valor <= 0:
        return "0 %"
    p = valor / total * 100
    return "<1 %" if p < 1 else f"{_redondear(p)} %"


def fecha_corta(iso):
    a, m, d = (int(x) for x in iso.split("-"))
    return date(a, m, d)


def fecha_larga(iso):
    return "/".join(reversed(iso.split("-")))


def sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).lower()


def _redondear(x):
    """Math.round de JavaScript: .5 hacia arriba."""
    return int(math.floor(x + 0.5))


def _redondear2(n):
    return math.floor(n * 100 + 0.5) / 100


# ── variación contra el período anterior ─────────────────────────────────────
def chip_delta(actual, anterior, texto_contra, puntos=False):
    """(clase, texto) del chip de variación. `puntos`: la diferencia se da en puntos (para porcentajes)."""
    if not anterior:
        return "neutro", "sin dato anterior"
    dif = actual - anterior if puntos else (actual - anterior) / abs(anterior) * 100
    if abs(dif) < 0.05:
        return "neutro", f"= igual {texto_contra}"
    flecha = "▲" if dif > 0 else "▼"
    return ("sube" if dif > 0 else "baja"), f"{flecha} {numero(abs(dif), 1)}{' pts' if puntos else ' %'} {texto_contra}"


# ── qué productos se cuentan (Shell / Valvoline / Otros) ─────────────────────
class FiltroProveedores:
    """Igual que los filtros del escritorio: litros y % premium se recalculan para lo elegido.
    Con todos elegidos nada se ve «apretado»; el primer toque aísla ese proveedor."""

    def __init__(self, seleccion=None):
        claves = [c for c, _ in PROVEEDORES]
        validos = {c for c in (seleccion or []) if c in claves}
        self.seleccion = validos or set(claves)

    def estan_todos(self):
        return len(self.seleccion) == len(PROVEEDORES)

    def activo(self, clave):
        return not self.estan_todos() and clave in self.seleccion

    def firma(self):
        """Lo elegido, como texto estable: sirve para saber si hay que volver a dibujar."""
        return ",".join(sorted(self.seleccion))

    def alternar(self, clave):
        if self.estan_todos():
            self.seleccion = {clave}
        elif clave in self.seleccion:
            self.seleccion.discard(clave)
            if not self.seleccion:   # sin ninguno no hay nada que mostrar
                self.todos()
        else:
            self.seleccion.add(clave)

    def todos(self):
        self.seleccion = {c for c, _ in PROVEEDORES}


def vista_litros(datos, filtro):
    """Lo que muestran las tarjetas de litros y premium: los números del servidor o, si se eligieron algunos
    proveedores, la suma de esos. Si el servidor manda el formato anterior (sin desglose) se muestra todo."""
    mes = datos["litros"]["mes"]
    ant = datos["litros"]["mes_anterior"]
    if "por_proveedor" not in mes or "por_proveedor" not in ant:
        return {
            "con_desglose": False, "etiqueta": None, "incluye_shell": True,
            "litros": mes["litros"], "premium": mes["premium"], "pct": mes["pct_premium"],
            "litros_ant": ant["litros"], "pct_ant": ant["pct_premium"],
            "por_dia": [{"fecha": d["fecha"], "litros": d["litros"], "premium": d["premium"]} for d in mes["por_dia"]],
        }
    claves = [c for c, _ in PROVEEDORES if c in filtro.seleccion]

    def sumar(por_proveedor):
        return {"litros": sum(por_proveedor[c]["litros"] for c in claves),
                "premium": sum(por_proveedor[c]["premium"] for c in claves)}

    def pct(x):
        return math.floor(x["premium"] / x["litros"] * 1000 + 0.5) / 10 if x["litros"] else 0

    actual = sumar(mes["por_proveedor"])
    anterior = sumar(ant["por_proveedor"])
    nombres = dict(PROVEEDORES)
    por_dia = []
    for d in mes["por_dia"]:
        dia = sumar(d["proveedores"])
        por_dia.append({"fecha": d["fecha"], "litros": _redondear2(dia["litros"]), "premium": _redondear2(dia["premium"])})
    return {
        "con_desglose": True,
        "etiqueta": None if filtro.estan_todos() else " + ".join(nombres[c] for c in claves),
        "incluye_shell": "SHELL" in filtro.seleccion,
        "litros": _redondear2(actual["litros"]), "premium": _redondear2(actual["premium"]), "pct": pct(actual),
        "litros_ant": _redondear2(anterior["litros"]), "pct_ant": pct(anterior),
        "por_dia": por_dia,
    }


# ── cómo se cobró lo recaudado ───────────────────────────────────────────────
def medios_de_cobro(d):
    """Filas (clave, nombre, color, valor, porcentaje) de los medios de cobro de un desglose."""
    filas = []
    for clave, nombre, color, siempre in MEDIOS_DE_COBRO:
        valor = d.get(clave, 0) or 0
        if siempre or abs(valor) >= 0.005:
            filas.append({"clave": clave, "nombre": nombre, "color": color, "valor": valor,
                          "porcentaje": texto_porcentaje(valor, d.get("total", 0))})
    return filas


def aviso_diferencia(d):
    """Control cruzado del servidor: si el desglose no coincide con el total, se dice en vez de esconderlo."""
    dif = d.get("diferencia") or 0
    if abs(dif) >= 0.5:
        return f"El desglose no coincide con el total (diferencia $ {numero(dif)}). Conviene revisarlo."
    return None


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def nombre_mes(clave):
    """'2026-03' -> 'marzo 2026'."""
    a, m = (int(x) for x in clave.split("-"))
    return f"{MESES[m - 1]} {a}"


def dia_corto(d):
    """date -> 'lun 2'."""
    return f"{DIAS_CORTOS[d.weekday()]} {d.day}"


def texto_actualizado(calculado_en, ahora=None):
    """'Datos de las 00:03' (con el día si no son de hoy). `calculado_en` es la hora del cálculo del servidor."""
    local = calculado_en.astimezone() if calculado_en.tzinfo else calculado_en
    hoy = (ahora or datetime.now()).date()
    base = f"Datos de las {local:%H:%M}"
    return base if local.date() == hoy else f"{base} del {local.day}/{local.month}"


# ── avisos sobre el estado del cálculo ───────────────────────────────────────
def avisos(respuesta, sin_conexion, ahora=None):
    """Textos de aviso arriba del panel: sin conexión, servidor sin latido, último cálculo fallido."""
    salida = []
    if sin_conexion:
        salida.append("Sin conexión con el servidor: se ven los últimos datos cargados.")
    if respuesta.get("desactualizado"):
        desde = (ahora or datetime.now()) - timedelta(seconds=respuesta.get("verificado_hace_seg", 0))
        salida.append(f"El cálculo del servidor no da señales desde las {desde:%H:%M}: los números pueden estar desactualizados.")
    if respuesta.get("error"):
        salida.append("El último cálculo falló y se muestran los datos anteriores. Revisar el servidor.")
    return salida


# ── cobranzas ────────────────────────────────────────────────────────────────
def estado_factura(vencimiento_iso, hoy_iso):
    """(clase, texto) de una factura según los días que faltan para vencer, contados desde el día de los datos."""
    dias = (fecha_corta(vencimiento_iso) - fecha_corta(hoy_iso)).days
    if dias < 0:
        return "vencida", f"Vencida hace {plural(-dias, 'día', 'días')}"
    if dias == 0:
        return "por-vencer", "Vence hoy"
    if dias == 1:
        return "por-vencer", "Vence mañana"
    if dias <= 7:
        return "por-vencer", f"Vence en {dias} días"
    return "al-dia", "Al día"


def texto_de_saldo(c):
    n = len(c["facturas"])
    if n:
        base = plural(n, "factura", "facturas")
        return f"{base} · {pesos(c['vencido'])} vencido" if c["vencido"] > 0 else base
    return "Saldo a favor del cliente" if c["saldo"] < 0 else "Sin deuda"


def filtrar_clientes(datos, busqueda, todos=True):
    """(clientes a mostrar, texto de resumen). Sin búsqueda: los que tienen deuda o saldo a favor."""
    q = sin_acentos(busqueda.strip())
    clientes = datos["clientes"]
    de = "los clientes" if todos else "tus clientes"
    if not q:
        lista = [c for c in clientes if c["facturas"] or c["saldo"] != 0]
        n = datos["cartera"]["clientes_con_deuda"]
        if lista:
            resumen = f"{plural(n, 'cliente con deuda', 'clientes con deuda')}. Buscá por nombre o número para ver a cualquiera de {de}."
        else:
            resumen = (f"No hay clientes con deuda. " if todos else "No tenés clientes con deuda. ") + "Buscá por nombre o número para consultar a cualquiera."
        return lista, resumen
    lista = [c for c in clientes if q in sin_acentos(c["nombre"]) or q in str(c["cuenta"])]
    if not lista:
        resumen = f"No hay clientes {'' if todos else 'tuyos '}con ese nombre o número."
    elif len(lista) > MAXIMO_RESULTADOS:
        resumen = f"Mostrando {MAXIMO_RESULTADOS} de {len(lista)}: escribí más para acotar."
    else:
        resumen = plural(len(lista), "cliente", "clientes")
    return lista[:MAXIMO_RESULTADOS], resumen
