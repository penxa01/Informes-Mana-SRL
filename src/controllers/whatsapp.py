"""Aviso por WhatsApp al vendedor para que reclame una deuda a su cliente.

Se arma un enlace ``https://wa.me/<número>?text=<mensaje>``: abre el chat con el
vendedor con el mensaje ya escrito, desde la cuenta de WhatsApp que esté abierta en
la PC (la de Martin). Quien usa la app toca "Enviar" en WhatsApp: no hay envío
automático, así que la app no puede saber si el mensaje salió realmente.

Sin Qt: solo arma textos, para poder probarlo.
"""
import re
from urllib.parse import quote

from src.Views.CuentasCorrientes.formato import fmt_monto

#: Con más facturas que esto el mensaje se resume (la URL y el chat no son para listas largas).
MAX_FACTURAS_EN_MENSAJE = 25


def normalizar_telefono_ar(telefono):
    """Celular argentino -> formato internacional de WhatsApp: ``549`` + área + número.

    Acepta ``2645048307``, ``264-504 8307``, ``02645048307``, ``+54 9 264 504 8307``.
    No admite el ``15`` (celular dentro de la misma área): sin el área no se sabe a dónde ir.
    """
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if digitos.startswith("549") and len(digitos) == 13:
        return digitos
    if digitos.startswith("54") and len(digitos) == 12:
        return "549" + digitos[2:]
    if digitos.startswith("0") and len(digitos) == 11:
        digitos = digitos[1:]
    if len(digitos) == 10:
        return "549" + digitos
    raise ValueError(
        f"Número de teléfono inválido para WhatsApp: «{str(telefono).strip()}». "
        "Debe tener código de área y número (10 dígitos, ej. 2645048307)."
    )


def url_whatsapp(telefono, mensaje):
    """Enlace que abre WhatsApp con el chat de ``telefono`` y ``mensaje`` precargado."""
    return f"https://wa.me/{normalizar_telefono_ar(telefono)}?text={quote(mensaje, safe='')}"


def _fecha(f):
    return f.strftime("%d/%m/%Y")


def _periodo(fechas):
    """'emitida el 01/03/2026' | 'emitidas el ...' | 'emitidas entre el X y el Y'."""
    desde, hasta = min(fechas), max(fechas)
    if desde == hasta:
        return f"{'emitida' if len(fechas) == 1 else 'emitidas'} el {_fecha(desde)}"
    return f"emitidas entre el {_fecha(desde)} y el {_fecha(hasta)}"


def armar_mensaje_reclamo(vendedor_nombre, cliente, cuenta, telefono_cliente, facturas):
    """Mensaje para el vendedor: contactar al cliente por las facturas adeudadas.

    :param facturas: lista de dicts ``comprobante``, ``fecha_emision`` (date/Timestamp) y
        ``saldo``. Se ordenan por fecha. Pasado ``MAX_FACTURAS_EN_MENSAJE`` se resumen,
        pero el total siempre incluye todas.
    """
    if not facturas:
        raise ValueError("El reclamo no tiene facturas para informar.")
    facturas = sorted(facturas, key=lambda f: (f["fecha_emision"], f["comprobante"]))
    total = sum(float(f["saldo"]) for f in facturas)
    nombre_pila = str(vendedor_nombre).strip().split()[0].title() if str(vendedor_nombre).strip() else ""

    lineas_facturas = [
        f"- {f['comprobante']} | {_fecha(f['fecha_emision'])} | {fmt_monto(float(f['saldo']))}"
        for f in facturas[:MAX_FACTURAS_EN_MENSAJE]
    ]
    resto = len(facturas) - MAX_FACTURAS_EN_MENSAJE
    if resto > 0:
        lineas_facturas.append(f"... y {resto} facturas más")

    return "\n".join([
        f"Hola {nombre_pila},".strip(),
        "",
        "Necesitamos que te contactes con el cliente para reclamarle el pago de las facturas que adeuda.",
        "",
        f"*Cliente:* {cliente} (cuenta {cuenta})",
        f"*Teléfono:* {telefono_cliente}",
        "",
        f"*Facturas adeudadas* ({_periodo([f['fecha_emision'] for f in facturas])}):",
        *lineas_facturas,
        "",
        f"*Total adeudado:* {fmt_monto(total)}",
        "",
        "Importante: avisanos por este medio cuando te hayas contactado con el cliente.",
    ])
