"""Verifica la ubicacion del cliente (enlace de Google Maps + mapita) en el detalle de pedidos.

Parte 1: funciones puras (leer coordenadas del enlace, calculo de teselas). Sin red.
Parte 2: la tarjeta en el detalle del pedido contra la base real, dentro de UNA transaccion
que se revierte (commit()/close() de la app quedan anulados). La descarga de teselas y la
resolucion de enlaces cortos estan reemplazadas: la prueba no sale a internet.

    QT_QPA_PLATFORM=offscreen python tests/verificar_ubicacion_maps.py
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtGui import QColor, QDesktopServices, QImage
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from src.controllers import ubicacion_maps as um
from src.Views.Pedidos import mapa_ubicacion as mu
from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond, extra=""):
    print(("OK   " if cond else "FALLA"), nombre, extra)
    if not cond:
        fallas.append(nombre)


# ── 1. funciones puras ─────────────────────────────────────────────────────────
print("=== 1. leer coordenadas del enlace ===")
casos = {
    "pin del lugar (!3d!4d)": ("https://www.google.com/maps/place/Mana/@-31.4201,-64.1888,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d-31.4167!4d-64.1833",
                               (-31.4167, -64.1833)),
    "centro de la vista (@)": ("https://www.google.com/maps/@-31.4201,-64.1888,15z", (-31.4201, -64.1888)),
    "parametro q=": ("https://maps.google.com/?q=-31.4201,-64.1888", (-31.4201, -64.1888)),
    "parametro q= con %2C": ("https://www.google.com/maps?q=-31.4201%2C-64.1888", (-31.4201, -64.1888)),
    "parametro ll=": ("https://maps.google.com/?ll=-31.42,-64.18&z=14", (-31.42, -64.18)),
}
for nombre, (url, esperado) in casos.items():
    check(f"extrae de {nombre}", um.extraer_coordenadas(url) == esperado, str(um.extraer_coordenadas(url)))
check("un enlace corto no trae coordenadas a la vista", um.extraer_coordenadas("https://maps.app.goo.gl/AbCdEf123") is None)
check("fuera de rango se descarta", um.extraer_coordenadas("https://maps.google.com/?q=95.5,-64.1") is None)
check("resolver un enlace largo no sale a la red",
      um.resolver_coordenadas("https://www.google.com/maps/@-31.4,-64.1,15z", timeout=0.001) == (-31.4, -64.1))
check("resolver sin red devuelve None, no lanza",
      um.resolver_coordenadas("http://127.0.0.1:9/no-existe", timeout=0.5) is None)
check("enlace valido: https", um.es_enlace_valido("https://maps.app.goo.gl/x"))
check("enlace valido: rechaza javascript:", not um.es_enlace_valido("javascript:alert(1)"))
check("enlace valido: rechaza texto suelto", not um.es_enlace_valido("Av. Colon 123"))

print("=== 1b. teselas ===")
# (0, 0) en zoom 1 cae justo en la esquina entre 4 teselas: x=1, y=1 -> pixel (256, 256)
plan = um.plan_teselas(0.0, 0.0, 1, 100, 60)
check("(0,0) z1 necesita las 4 teselas vecinas", sorted((t[0], t[1]) for t in plan) == [(0, 0), (0, 1), (1, 0), (1, 1)], str(plan))
check("y las ubica alrededor del centro", {(t[0], t[1]): (t[2], t[3]) for t in plan}[(1, 1)] == (50, 30))
plan = um.plan_teselas(-31.4167, -64.1833, 16, mu.ANCHO_MAPA, mu.ALTO_MAPA)
check("una vista chica usa de 1 a 4 teselas", 1 <= len(plan) <= 4, str(len(plan)))
cubre = all(any(dx <= px < dx + 256 and dy <= py < dy + 256 for _, _, dx, dy in plan)
            for px in (0, mu.ANCHO_MAPA - 1) for py in (0, mu.ALTO_MAPA - 1))
check("las teselas cubren las 4 esquinas de la vista", cubre)

# ── 2. tarjeta en el detalle del pedido ────────────────────────────────────────
print("=== 2. tarjeta de ubicacion (base real, transaccion revertida) ===")
for m in ("information", "warning", "critical"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: None))
avisos = []
QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(a[2]))

img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(QColor("#88aa88"))
buf = QBuffer()
buf.open(QIODevice.WriteOnly)
img.save(buf, "PNG")
PNG = bytes(buf.data())
um.descargar_tesela = lambda zoom, tx, ty, timeout=5: PNG   # sin internet

abiertos = []
QDesktopServices.openUrl = staticmethod(lambda url: abiertos.append(url.toString()) or True)

respuesta = {"texto": "", "ok": True}
QInputDialog.getText = staticmethod(lambda *a, **k: (respuesta["texto"], respuesta["ok"]))
coords_resueltas = {"valor": (-31.4167, -64.1833)}
um.resolver_coordenadas = lambda enlace, timeout=6: coords_resueltas["valor"]


def mapa_dibujado(tarjeta):
    pm = tarjeta.mapa.pixmap()   # None mientras no hay imagen
    return pm is not None and not pm.isNull()


def esperar(cond, segundos=5):
    fin = time.time() + segundos
    while time.time() < fin and not cond():
        app.processEvents()
        time.sleep(0.01)
    return cond()


try:
    real = pp._conexion()
except Exception as e:
    print("SIN BASE:", e)
    sys.exit(1 if fallas else 0)


class _Proxy:
    def __init__(self, real):
        self._real = real

    def commit(self):
        pass

    def close(self):
        pass

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


con = _Proxy(real)
pp._conexion = lambda: con

try:
    cur = con.cursor()
    cur.execute("SELECT id_cliente FROM Cliente ORDER BY id_cliente LIMIT 1")
    id_cliente = cur.fetchone()[0]
    cur.execute("UPDATE Cliente SET ubicacion_maps = NULL, ubicacion_lat = NULL, ubicacion_lng = NULL "
                "WHERE id_cliente = %s", (id_cliente,))
    cur.execute("INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido) VALUES (%s, CURRENT_DATE, 'pendiente') "
                "RETURNING id_pedido", (id_cliente,))
    id_pedido = cur.fetchone()[0]

    def en_base():
        cur.execute("SELECT ubicacion_maps, ubicacion_lat, ubicacion_lng FROM Cliente WHERE id_cliente = %s",
                    (id_cliente,))
        return cur.fetchone()

    d = pp.VentanaDetallePedido(id_pedido, None, None)
    t = d.tarjeta_ubicacion
    d.show()
    app.processEvents()
    check("sin enlace: se ofrece cargarlo", t.vacio.isVisible() and not t.mapa.isVisible())
    check("sin enlace: no hay boton Cambiar", not t.btn_cambiar.isVisible())

    # enlace invalido: avisa y no guarda nada
    respuesta.update(texto="javascript:alert(1)", ok=True)
    t.cambiar()
    check("enlace invalido: avisa", len(avisos) == 1)
    check("enlace invalido: no se guarda", en_base() == (None, None, None))

    # cancelar el cuadro: tampoco guarda
    respuesta.update(texto="https://maps.google.com/?q=1,1", ok=False)
    t.cambiar()
    check("cancelar: no se guarda", en_base() == (None, None, None))

    # enlace bueno
    enlace = "https://maps.app.goo.gl/AbCdEf123"
    respuesta.update(texto=enlace, ok=True)
    t.cambiar()
    check("enlace bueno: queda en el cliente con sus coordenadas", en_base() == (enlace, -31.4167, -64.1833), str(en_base()))
    check("se muestra el mapa y el boton Cambiar", t.mapa.isVisible() and t.btn_cambiar.isVisible() and not t.vacio.isVisible())
    check("el mapa se dibuja (tamano exacto)", esperar(lambda: mapa_dibujado(t)) and
          (t.mapa.pixmap().width(), t.mapa.pixmap().height()) == (mu.ANCHO_MAPA, mu.ALTO_MAPA))

    # recargar el detalle no vuelve a pedir el mapa (mismo cliente, mismos datos)
    hilos_antes = len(mu._hilos_vivos)
    token = t._token
    d.cargar_datos_pedido()
    check("recargar el detalle no redibuja el mapa", t._token == token and len(mu._hilos_vivos) == hilos_antes)

    # una ventana nueva ya lo muestra desde la base
    d2 = pp.VentanaDetallePedido(id_pedido, None, None)
    d2.show()
    app.processEvents()
    check("otra ventana del mismo cliente lo muestra", d2.tarjeta_ubicacion.mapa.isVisible())
    check("y dibuja su mapa", esperar(lambda: mapa_dibujado(d2.tarjeta_ubicacion)))

    # tocar el mapa abre Maps
    t.mapa.clicked.emit()
    check("tocar el mapa abre el enlace en Google Maps", abiertos == [enlace], str(abiertos))

    # enlace que no se puede ubicar: se guarda igual, sin mapa
    coords_resueltas["valor"] = None
    enlace2 = "https://maps.app.goo.gl/SinCoordenadas"
    respuesta.update(texto=enlace2, ok=True)
    t.cambiar()
    check("sin coordenadas: guarda el enlace igual", en_base() == (enlace2, None, None), str(en_base()))
    check("sin coordenadas: ofrece abrirlo", t.mapa.isVisible() and "abrirlo" in t.mapa.text())

    # vaciar el campo quita la ubicacion
    respuesta.update(texto="", ok=True)
    t.cambiar()
    check("dejar vacio la quita", en_base() == (None, None, None))
    check("vuelve a ofrecer cargarla", t.vacio.isVisible() and not t.mapa.isVisible())

    # esperar a que no queden hilos antes de revertir
    esperar(lambda: not mu._hilos_vivos)
    d.close()
    d2.close()
finally:
    real.rollback()
    real.close()

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
sys.exit(1 if fallas else 0)
