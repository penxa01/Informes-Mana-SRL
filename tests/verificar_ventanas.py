"""Ventanas emergentes que se adaptan a la pantalla (src/ui/ventanas.py).

Problema: varios diálogos tienen tamaños fijos pensados para un monitor grande
(Reclamos 1020x760, Detalle de Margen 1240x680, Detalle de Pedido 1040x720...) y en
monitores chicos (notebook 1366x768, 1280x720, 1024x768) se salen de la pantalla.

Solución central: un ajustador instalado una vez en la aplicación corrige TODA ventana
emergente (QDialog) la primera vez que se muestra:
  * achica el tamaño (y los mínimos) para que entre, descontando la barra de título y bordes;
  * si aun así el contenido no entra, lo envuelve en un área con scroll;
  * la centra sobre su ventana madre y la mantiene dentro del área útil (sin barra de tareas).
No toca las que ya entran, ni los avisos tipo toast, ni las ventanas maximizadas.

Correr desde la raíz:  python tests/verificar_ventanas.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import PyQt5.QtCore as core
import PyQt5.QtWidgets as w

from src.ui import ventanas
from src.ui.ventanas import calcular_geometria

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


MARCO = (16, 40)    # ancho y alto que suman bordes + barra de título
f = lambda r, **k: calcular_geometria(r, **{"marco": MARCO, "fraccion": 0.96, **k})

print("=== geometría (función pura) ===")
g = f((0, 0, 1366, 728), tam=(1020, 760))
check("Reclamos 1020x760 en 1366x768: se achica en alto, no en ancho", g["w"] == 1020 and g["h"] == int(728 * .96 - 40), str(g))
check("el marco completo entra en el área útil", g["h"] + MARCO[1] <= 728 and g["w"] + MARCO[0] <= 1366)

g = f((0, 0, 1280, 680), tam=(1240, 680), minimo=(900, 480))
check("Detalle de Margen 1240x680 en 1280x720: se achica en ancho y alto",
      g["w"] == int(1280 * .96 - 16) and g["h"] == int(680 * .96 - 40), str(g))

g = f((0, 0, 1024, 728), tam=(1240, 680), minimo=(900, 480))
check("en 1024x768 el ancho entra (900 de mínimo cabe)", g["w"] <= 1024 - 16 and g["w"] >= g["min_w"], str(g))

g = f((0, 0, 1920, 1040), tam=(1020, 760))
check("pantalla grande: no se toca el tamaño", (g["w"], g["h"]) == (1020, 760), str(g))

g = f((0, 0, 800, 560), tam=(1040, 720), minimo=(820, 560))
check("los mínimos que no entran se bajan", g["min_w"] < 820 and g["min_h"] < 560, str(g))
check("y el tamaño nunca queda por debajo del mínimo ya ajustado", g["w"] >= g["min_w"] and g["h"] >= g["min_h"])

g = f((0, 0, 1366, 728), tam=(640, 420))
check("un diálogo chico no se agranda", (g["w"], g["h"]) == (640, 420))
check("queda centrado en el área si no hay referencia",
      abs((g["x"] + (640 + MARCO[0]) / 2) - 683) <= 1 and abs((g["y"] + (420 + MARCO[1]) / 2) - 364) <= 1, str((g["x"], g["y"])))

g = f((0, 0, 1366, 728), tam=(1000, 500), centro=(1300, 360))
check("centrado sobre la madre pero sin salirse por la derecha", g["x"] + 1000 + MARCO[0] <= 1366, str(g["x"]))
g = f((0, 0, 1366, 728), tam=(1000, 500), centro=(10, 10))
check("ni por la izquierda / arriba", g["x"] >= 0 and g["y"] >= 0, str((g["x"], g["y"])))
g = f((-1920, 0, 1920, 1040), tam=(1000, 500), centro=(-1900, 500))
check("monitor a la izquierda del principal (coordenadas negativas)", g["x"] >= -1920 and g["x"] + 1000 + MARCO[0] <= 0, str(g["x"]))
g = f((0, 0, 100, 60), tam=(1000, 700))
check("área diminuta: tamaños positivos, sin romper", g["w"] >= 1 and g["h"] >= 1, str(g))

print("=== con Qt ===")
app = w.QApplication.instance() or w.QApplication([])
original = ventanas.area_disponible
ventanas.instalar(app)


def con_pantalla(ancho, alto):
    ventanas.area_disponible = lambda _w: core.QRect(0, 0, ancho, alto)


def dialogo(ancho, alto, minimo=None, fijo=False, padre=None):
    d = w.QDialog(padre)
    lay = w.QVBoxLayout(d)
    lay.addWidget(w.QLabel("contenido"))
    if fijo:
        d.setFixedSize(ancho, alto)
    else:
        d.resize(ancho, alto)
        if minimo:
            d.setMinimumSize(*minimo)
    return d


def adentro(d, ancho, alto):
    """El diálogo entra en el área, contando el marco que Qt no simula en el modo offscreen."""
    fg = d.frameGeometry()
    return fg.width() + MARCO[0] <= ancho and fg.height() + MARCO[1] <= alto and fg.x() >= 0 and fg.y() >= 0


con_pantalla(1366, 728)
d = dialogo(1240, 680, minimo=(900, 480)); d.show(); app.processEvents()
check("Detalle de Margen en 1366x768 entra", adentro(d, 1366, 728), f"{d.width()}x{d.height()}")
d.close()
d = dialogo(1020, 760); d.show(); app.processEvents()
check("Reclamos en 1366x768 entra (antes se salía por abajo)", adentro(d, 1366, 728), f"{d.width()}x{d.height()}")
d.close()

con_pantalla(1280, 680)
d = dialogo(1240, 680, minimo=(900, 480)); d.show(); app.processEvents()
check("Detalle de Margen en 1280x720 entra", adentro(d, 1280, 680), f"{d.width()}x{d.height()}")
d.close()

con_pantalla(1024, 728)
d = dialogo(1240, 680, minimo=(900, 480)); d.show(); app.processEvents()
check("Detalle de Margen en 1024x768 entra (ancho)", adentro(d, 1024, 728), f"{d.width()}x{d.height()}")
d.close()

con_pantalla(1366, 728)
d = dialogo(640, 420); d.show(); app.processEvents()
check("un diálogo que ya entra queda del mismo tamaño", (d.width(), d.height()) == (640, 420), f"{d.width()}x{d.height()}")
d.close()

d = dialogo(1500, 900, fijo=True); d.show(); app.processEvents()
check("tamaño FIJO más grande que la pantalla: se achica", adentro(d, 1366, 728), f"{d.width()}x{d.height()}")
d.close()

padre = w.QWidget(); padre.setGeometry(300, 100, 600, 400); padre.show()
d = dialogo(500, 300, padre=padre); d.setWindowFlags(d.windowFlags() | core.Qt.Dialog); d.show(); app.processEvents()
cd = d.frameGeometry().center(); cp = padre.frameGeometry().center()
check("se centra sobre su ventana madre", abs(cd.x() - cp.x()) <= 25 and abs(cd.y() - cp.y()) <= 25, f"dialogo {cd.x()},{cd.y()} madre {cp.x()},{cp.y()}")
d.close(); padre.close()

print("=== contenido que no entra: scroll ===")
d = w.QDialog()
lay = w.QVBoxLayout(d)
for i in range(70):
    lay.addWidget(w.QLineEdit(f"campo {i}"))
btn = w.QPushButton("Guardar")
lay.addWidget(btn)
check("(precondición) el contenido pide más alto que la pantalla", d.minimumSizeHint().height() > 728)
d.show(); app.processEvents()
scrolls = d.findChildren(w.QScrollArea)
check("se envuelve en un área con scroll", len(scrolls) == 1)
check("el diálogo entra en la pantalla", adentro(d, 1366, 728), f"{d.width()}x{d.height()}")
check("y no queda diminuto: aprovecha el alto disponible", d.height() >= 500 and d.width() >= 150, f"{d.width()}x{d.height()}")
check("hay scroll vertical para llegar a todo el contenido", scrolls and scrolls[0].verticalScrollBar().maximum() > 0)
check("los campos siguen siendo los mismos widgets (los datos no se pierden)", len(d.findChildren(w.QLineEdit)) == 70 and btn.parent() is not None)
d.close()

d = w.QDialog()
lay = w.QVBoxLayout(d)
for i in range(12):
    lay.addWidget(w.QLineEdit())
d.show(); app.processEvents()
check("si el contenido SÍ entra en la pantalla, no se le agrega scroll", len(d.findChildren(w.QScrollArea)) == 0)
d.close()

d = w.QDialog()
grid = w.QGridLayout(d)
campos = []
for i in range(60):
    e = w.QLineEdit()
    campos.append(e)
    grid.addWidget(w.QLabel(f"c{i}"), i // 2, (i % 2) * 2)
    grid.addWidget(e, i // 2, (i % 2) * 2 + 1)
d.show(); app.processEvents()
check("una GRILLA también se envuelve y conserva su disposición (2 columnas)",
      len(d.findChildren(w.QScrollArea)) == 1 and campos[0].geometry().y() == campos[1].geometry().y()
      and campos[2].geometry().y() > campos[0].geometry().y())
d.close()

print("=== lo que NO hay que tocar ===")
con_pantalla(1366, 728)
toast = w.QWidget()
toast.setWindowFlags(core.Qt.WindowStaysOnTopHint | core.Qt.FramelessWindowHint | core.Qt.Tool)
toast.setFixedSize(350, 80)
toast.show(); app.processEvents()
check("un aviso tipo toast (sin marco, Qt.Tool) queda como está", (toast.width(), toast.height()) == (350, 80))
toast.close()

d = dialogo(1240, 680); d.showMaximized(); app.processEvents()
check("una ventana maximizada no se reacomoda", d.isMaximized())
d.close()

# (No se muestra: QMessageBox.show() se cae en la plataforma offscreen de Qt aun sin este módulo.)
check("los cuadros nativos (QMessageBox, QFileDialog...) no se ajustan",
      not ventanas._es_ajustable(w.QMessageBox(w.QMessageBox.Information, "t", "texto"))
      and not ventanas._es_ajustable(w.QFileDialog()))
check("un QDialog común sí es ajustable", ventanas._es_ajustable(w.QDialog()))
check("un menú/popup no es ajustable", not ventanas._es_ajustable(w.QMenu()))

print("=== una sola vez ===")
d = dialogo(1240, 680, minimo=(900, 480)); d.show(); app.processEvents()
d.resize(900, 500); d.hide(); d.show(); app.processEvents()
check("al volver a mostrarse no pisa lo que el usuario hizo", (d.width(), d.height()) == (900, 500), f"{d.width()}x{d.height()}")
d.close()
n_filtros = ventanas.instalar(app)
check("instalar dos veces no duplica el ajustador", ventanas.instalar(app) is n_filtros)

ventanas.area_disponible = original
print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
