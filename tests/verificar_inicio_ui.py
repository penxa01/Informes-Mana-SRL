"""Verifica la página Inicio (General, Desglose de litros y Cobranzas) con datos de prueba: sin base de datos.

    QT_QPA_PLATFORM=offscreen python tests/verificar_inicio_ui.py
"""
import os
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.controllers import panel_io
from src.ui.paginas.inicio import PaginaInicio
from src.ui.paginas.panel_cobranzas import DetalleCliente
from src.ui.widgets.graficos import Anillo, BarraProporcion, GraficoBarras
from src.ui.widgets.panel_piezas import TarjetaPanel

app = widget.QApplication.instance() or widget.QApplication([])
from src.ui import recursos

app.setStyleSheet(recursos.leer_estilos())
fallas = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallas.append(nombre)


def esperar(cond, segundos=4):
    fin = time.time() + segundos
    while time.time() < fin:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def prov(l, p):
    return {"litros": l, "premium": p}


DESGLOSE = {"total": 1000.0, "efectivo": 500.0, "transferencia": 300.0, "cheques": 200.0, "retenciones": 0.0,
            "otros": 0.0, "diferencia": 0.0, "recibos": 3}
GENERAL = {
    "hoy": "2026-11-04",
    "periodos": {
        "mes": {"desde": "2026-11-01", "hasta": "2026-11-04"}, "mes_anterior": {"desde": "2026-10-01", "hasta": "2026-10-04"},
        "semana": {"desde": "2026-11-02", "hasta": "2026-11-04"}, "semana_anterior": {"desde": "2026-10-26", "hasta": "2026-10-28"},
    },
    "litros": {
        "mes": {"litros": 100.0, "premium": 30.0, "pct_premium": 30.0,
                "por_dia": [{"fecha": "2026-11-02", "litros": 60.0, "premium": 20.0,
                             "proveedores": {"SHELL": prov(40, 20), "VALVOLINE": prov(15, 0), "OTROS": prov(5, 0)}},
                            {"fecha": "2026-11-03", "litros": 40.0, "premium": 10.0,
                             "proveedores": {"SHELL": prov(20, 10), "VALVOLINE": prov(10, 0), "OTROS": prov(10, 0)}}],
                "por_proveedor": {"SHELL": prov(60, 30), "VALVOLINE": prov(25, 0), "OTROS": prov(15, 0)}},
        "mes_anterior": {"litros": 80.0, "premium": 16.0, "pct_premium": 20.0,
                         "por_proveedor": {"SHELL": prov(40, 16), "VALVOLINE": prov(30, 0), "OTROS": prov(10, 0)}},
    },
    "recaudado": {
        "semana": {"total": 1000.0, "recibos": 3, "por_dia": [{"fecha": "2026-11-02", "monto": 600.0}, {"fecha": "2026-11-03", "monto": 400.0}],
                   "desglose": DESGLOSE},
        "semana_anterior": {"total": 800.0, "recibos": 2, "desglose": DESGLOSE},
    },
}
COBRANZAS = {
    "hoy": "2026-11-04",
    "cartera": {"al_dia": 50.0, "a_favor": 5.0, "vencido": 30.0, "en_calle": 100.0, "facturas": 3, "por_vencer": 20.0,
                "pct_vencido": 30.0, "clientes_con_deuda": 2},
    "cobrado": {"2026-10": {**DESGLOSE, "desde": "2026-10-01", "hasta": "2026-10-31"},
                "2026-11": {**DESGLOSE, "desde": "2026-11-01", "hasta": "2026-11-04"}},
    "clientes": [
        {"cuenta": 101, "nombre": "Pérez Hnos", "saldo": 80.0, "vencido": 30.0,
         "facturas": [{"comprobante": "FA 1", "emision": "2026-10-01", "vencimiento": "2026-10-31", "total": 100.0, "saldo": 80.0}]},
        {"cuenta": 102, "nombre": "Gómez", "saldo": -5.0, "vencido": 0.0, "facturas": []},
        {"cuenta": 103, "nombre": "Sin deuda SA", "saldo": 0.0, "vencido": 0.0, "facturas": []},
    ],
}
AHORA = datetime.now(timezone.utc)


def respuesta(datos, **extra):
    return {"datos": datos, "calculado_en": AHORA, "verificado_hace_seg": 5, "desactualizado": False, "error": None, **extra}


modo = {"falla": None}


def app_falsa():
    """Lo mínimo que usa Inicio del AppWindow: la acción de actualizar ventas y la barra de estado."""
    a = widget.QMainWindow()
    a.accion_actualizar_ventas = widget.QAction("Actualizar ventas", a)
    a.status = a.statusBar()
    app_falsa.vivas.append(a)
    return a


app_falsa.vivas = []


def leer_falso(seccion):
    if modo["falla"] == "red":
        raise OSError("sin red")
    if modo["falla"] == "vacio":
        raise panel_io.PanelNoDisponible("todavía no se calculó")
    return respuesta(GENERAL if seccion == "general" else COBRANZAS)


panel_io.leer = leer_falso

pagina = PaginaInicio(app_falsa())
pagina.resize(1280, 800)
pagina.show()
pagina.on_activar()
vg = pagina._vistas["general"]
check("General: llegan los datos y se muestran", esperar(lambda: pagina._pilas["general"].currentIndex() == 1))
check("General: tres tarjetas", vg._grilla.count() == 3)
check("General: un gráfico de barras en Litros y otro en Recaudado", len(pagina.findChildren(GraficoBarras)) == 2)
check("General: un anillo de premium", len(pagina.findChildren(Anillo)) == 1)
check("General: barra de proporciones de «Cómo se cobró»", len(pagina.findChildren(BarraProporcion)) == 1)
check("Encabezado dice de qué hora son los datos", pagina._lbl_actualizado.text().startswith("Datos de las"))
check("Sin avisos con datos al día", not pagina._aviso.isVisible())

primera = vg._grilla.itemAtPosition(0, 0).widget()
vg.actualizar(GENERAL)
check("Los mismos datos no vuelven a armar las tarjetas", vg._grilla.itemAtPosition(0, 0).widget() is primera)

vg._chips["SHELL"].click()
check("Elegir Shell vuelve a armar las tarjetas", vg._grilla.itemAtPosition(0, 0).widget() is not primera)
tarjeta = vg._grilla.itemAtPosition(0, 0).widget()
check("Con Shell elegido la tarjeta lo dice", isinstance(tarjeta, TarjetaPanel) and any(
    "Shell" in l.text() for l in tarjeta.findChildren(widget.QLabel)))
check("El chip de Shell queda marcado y «Todos» no", vg._chips["SHELL"].isChecked() and not vg._chips["TODOS"].isChecked())
vg._chips["TODOS"].click()
check("«Todos» restablece la selección", vg._chips["TODOS"].isChecked() and not vg._chips["SHELL"].isChecked())

# Cambiar el filtro con la página scrolleada no tiene que mandarla al principio.
pagina.resize(1280, 380)
app.processEvents()
barra = pagina._pilas["general"].widget(1).verticalScrollBar()
barra.setValue(barra.maximum())
app.processEvents()
antes = barra.value()
vg._chips["VALVOLINE"].click()
app.processEvents()
check(f"Cambiar el filtro scrolleado conserva la posición (antes {antes}, después {barra.value()})",
      antes > 0 and barra.value() > 0)
vg._chips["TODOS"].click()
pagina.resize(1280, 800)

# ── Cobranzas ────────────────────────────────────────────────────────────────
pagina._pestanas.elegir(2)
vc = pagina._vistas["cobranzas"]
check("Cobranzas: llegan los datos", esperar(lambda: pagina._pilas["cobranzas"].currentIndex() == 1))
check("Cobranzas: seis tiles de cartera", len([t for t in vc._cartera.findChildren(TarjetaPanel)]) == 6)
check("Cobranzas: sin búsqueda, solo clientes con deuda o a favor", vc._tabla.rowCount() == 2)
vc._buscar.setText("perez")
check("Cobranzas: la búsqueda ignora acentos", vc._tabla.rowCount() == 1 and vc._tabla.item(0, 0).text() == "Pérez Hnos")
vc._buscar.setText("zzz")
check("Cobranzas: búsqueda sin resultados", vc._tabla.rowCount() == 0 and "No hay clientes" in vc._resumen.text())
vc._buscar.setText("")

combo = vc._cobrado.findChildren(widget.QComboBox)[0]
check("Cobranzas: el combo de meses arranca en el más nuevo", combo.currentData() == "2026-11" and combo.count() == 2)
combo.setCurrentIndex(1)
check("Cobranzas: cambiar de mes vuelve a armar el bloque", esperar(lambda: vc._mes == "2026-10" and
      vc._cobrado.findChildren(widget.QComboBox)[0].currentData() == "2026-10"))

dlg = DetalleCliente(COBRANZAS["clientes"][0], COBRANZAS["hoy"])
check("Detalle de cliente: una fila por factura", len([f for f in dlg.findChildren(widget.QFrame) if f.objectName() == "facturaFila"]) == 1)
check("Detalle de cliente: la factura vencida se marca", any(l.property("estado") == "vencida" for l in dlg.findChildren(widget.QLabel)))
dlg.deleteLater()

# ── Reclamos y desglose de litros ────────────────────────────────────────────
pedidos = []
abiertos = []
pagina._reclamos.abrir = lambda cuenta=None: abiertos.append(cuenta)   # no abrir el modal de verdad
vc.reclamos_solicitado.connect(pedidos.append)
btn = [b for b in vc.findChildren(widget.QPushButton) if b.objectName() == "btnReclamos"][0]
btn.click()
check("Cobranzas: el botón Reclamos pide abrir los reclamos sin cliente", pedidos == [None])
dlg = DetalleCliente(COBRANZAS["clientes"][0], COBRANZAS["hoy"], al_reclamar=pedidos.append)
reclamar = [b for b in dlg.findChildren(widget.QPushButton) if b.objectName() == "btnReclamos"]
check("Detalle de cliente: tiene botón Reclamar", len(reclamar) == 1)
dlg.deleteLater()
pagina._pestanas.elegir(0)
abiertos.clear()
pagina.abrir_reclamos(101)
check("abrir_reclamos lleva a Cobranzas y pide el reclamo del cliente", pagina._seccion == "cobranzas" and abiertos == [101])

import pandas as pd
pagina._pestanas.elegir(1)
check("Desglose de litros: pestaña propia, sin «Datos de las…» ni boton de actualizar", pagina._seccion == "litros" and not pagina._btn.isVisible())
check("Desglose de litros: avisa que está cargando hasta tener ventas", pagina._litros._overlay.isVisible())
pagina.on_ventas_listas(pd.DataFrame({c: [] for c in ("FECHA", "TC", "MODELO", "U_VENDIDAS", "VENDNUMERO", "CODMOV")}))
check("Desglose de litros: con ventas se habilita Generar y se quita el aviso",
      pagina._litros._btn.isEnabled() and not pagina._litros._overlay.isVisible())
pagina._pestanas.elegir(0)
check("Volver a General muestra de nuevo el boton de actualizar", pagina._btn.isVisible())

# ── Fallas ───────────────────────────────────────────────────────────────────
modo["falla"] = "red"
pagina._pestanas.elegir(0)
pagina._hilos["general"].wait()
pagina._cargar("general")
check("Sin conexión, con datos previos: se siguen viendo y se avisa",
      esperar(lambda: pagina._aviso.isVisible()) and "Sin conexión" in pagina._aviso.text() and pagina._pilas["general"].currentIndex() == 1)
pagina.al_cerrar()

pagina2 = PaginaInicio(app_falsa())
modo["falla"] = "vacio"
pagina2.show()
pagina2.on_activar()
check("Sin datos todavía: se explica y no hay pantalla vacía", esperar(lambda: "todavía no se calculó" in pagina2._estados["general"]._texto.text()))
pagina2.al_cerrar()

print()
if fallas:
    print(f"{len(fallas)} FALLA(S)")
    sys.exit(1)
print("TODO OK")
