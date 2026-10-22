"""Aviso por WhatsApp al vendedor (src/controllers/whatsapp.py).

El aviso se hace con un enlace ``wa.me`` con el mensaje ya escrito: se abre el chat
con el vendedor desde la cuenta de WhatsApp abierta en la PC (la de Martin).

Correr desde la raíz:  python tests/verificar_whatsapp.py
"""
import datetime as dt
import os
import sys
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers.whatsapp import armar_mensaje_reclamo, normalizar_telefono_ar, url_whatsapp

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def factura(comprobante, fecha, saldo):
    return {"comprobante": comprobante, "fecha_emision": fecha, "saldo": saldo}


print("=== número de teléfono argentino -> formato WhatsApp (549 + área + número) ===")
for entrada, esperado in (
    ("2645048307", "5492645048307"),
    ("264-504 8307", "5492645048307"),
    (" (264) 504-8307 ", "5492645048307"),
    ("02645048307", "5492645048307"),
    ("+54 9 264 504 8307", "5492645048307"),
    ("5492645048307", "5492645048307"),
    ("542645048307", "5492645048307"),
):
    try:
        r = normalizar_telefono_ar(entrada)
        check(f"{entrada!r} -> {esperado}", r == esperado, r)
    except ValueError as e:
        check(f"{entrada!r} -> {esperado}", False, str(e))
for malo in ("", "   ", "abc", "123", "26450483"):
    try:
        normalizar_telefono_ar(malo)
        check(f"{malo!r} rechazado", False)
    except ValueError as e:
        check(f"{malo!r} -> ValueError claro", "teléfono" in str(e).lower(), str(e))

print("=== mensaje al vendedor ===")
facturas = [
    factura("FC A 0003-00008834", dt.date(2026, 2, 26), 141685.77),
    factura("FC A 0003-00008808", dt.date(2026, 2, 23), 6007190.01),
]
msg = armar_mensaje_reclamo("MIGUEL ORTUÑO", "LOGISTICA FRONTERA S.A.S.", 1727, "4220647", facturas)
check("saluda al vendedor por su nombre de pila", msg.startswith("Hola Miguel"), msg.splitlines()[0])
check("pide contactar al cliente por las facturas adeudadas",
      "contactes con el cliente" in msg and "factura" in msg.lower())
check("datos del cliente (nombre, cuenta y teléfono)",
      "LOGISTICA FRONTERA S.A.S." in msg and "1727" in msg and "4220647" in msg)
check("lista cada factura con fecha e importe",
      all(t in msg for t in ("FC A 0003-00008808", "23/02/2026", "$ 6.007.190,01",
                             "FC A 0003-00008834", "26/02/2026", "$ 141.685,77")))
check("facturas ordenadas por fecha (la más vieja primero)",
      msg.index("FC A 0003-00008808") < msg.index("FC A 0003-00008834"))
check("rango de fechas de la deuda", "entre el 23/02/2026 y el 26/02/2026" in msg)
check("total adeudado", "$ 6.148.875,78" in msg, "")
check("recordatorio final: avisar por este medio al contactar",
      msg.rstrip().splitlines()[-1].lower().startswith("importante") and "por este medio" in msg.rstrip().splitlines()[-1])

una = armar_mensaje_reclamo("JOSE BANCO", "DREAM SRL", 7, "155", [factura("FC A 0003-00000001", dt.date(2026, 3, 1), 100.0)])
check("una sola factura: 'emitida el' sin rango", "emitida el 01/03/2026" in una and "entre el" not in una)
check("saluda con nombre de pila (José)", una.startswith("Hola Jose"))
mismo_dia = armar_mensaje_reclamo("JOSE BANCO", "X", 1, "1", [factura("A", dt.date(2026, 3, 1), 1.0), factura("B", dt.date(2026, 3, 1), 1.0)])
check("varias facturas del mismo día: 'emitidas el'", "emitidas el 01/03/2026" in mismo_dia)

muchas = [factura(f"FC A 0003-{i:08d}", dt.date(2026, 1, 1) + dt.timedelta(days=i), 1000.0) for i in range(40)]
largo = armar_mensaje_reclamo("MATIAS BARATA", "CLIENTE GRANDE", 9, "155", muchas)
check("con 40 facturas el mensaje no explota (resumido)", largo.count("FC A 0003-") <= 25 and len(largo) < 2200, str(len(largo)))
check("avisa cuántas facturas más hay", "y 15 facturas más" in largo or "15 facturas más" in largo)
check("el total incluye TODAS las facturas, no solo las listadas", "$ 40.000,00" in largo)

try:
    armar_mensaje_reclamo("X", "Y", 1, "1", [])
    check("sin facturas -> ValueError", False)
except ValueError:
    check("sin facturas -> ValueError", True)

print("=== enlace wa.me ===")
url = url_whatsapp("2645048307", "Hola! Mirá: $ 1.000,50\nlínea 2 & más")
p = urlparse(url)
check("host y número", p.scheme == "https" and p.netloc == "wa.me" and p.path == "/5492645048307", url[:40])
texto = parse_qs(p.query)["text"][0]
check("el texto viaja codificado y se recupera intacto (acentos, saltos, &, $)",
      texto == "Hola! Mirá: $ 1.000,50\nlínea 2 & más", repr(texto))
check("sin saltos de línea crudos en la URL", "\n" not in url and " " not in url)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
