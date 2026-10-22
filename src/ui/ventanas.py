"""Ventanas emergentes que se adaptan al tamaño de la pantalla.

Varios diálogos traen tamaños fijos pensados para un monitor grande (Reclamos 1020x760,
Detalle de Margen 1240x680, Detalle de Pedido 1040x720...) y en monitores chicos
(notebook 1366x768, 1280x720, 1024x768) se salían de la pantalla.

``instalar(app)`` (una vez, en ``main.py``) pone un filtro que corrige **toda** ventana
emergente (``QDialog``) la primera vez que se muestra, incluidas las que se agreguen
en el futuro, sin tocar cada una:

* achica el tamaño y los mínimos para que entre, descontando la barra de título y los
  bordes y dejando un margen (``FRACCION``) con la barra de tareas;
* si el contenido en sí no entra (su mínimo es mayor que la pantalla), lo envuelve en un
  área con **scroll**, conservando el layout (también las grillas);
* la centra sobre su ventana madre (o la activa) y la mantiene dentro del área útil del
  monitor **donde está el sistema**, no del principal.

No toca lo que ya entra, ni los avisos tipo toast (``Qt.Tool`` / sin marco), ni las ventanas
maximizadas, ni los cuadros nativos (``QMessageBox``, ``QFileDialog``...).
"""
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

#: fracción del área útil que puede ocupar una ventana (deja aire contra la barra de tareas)
FRACCION = 0.96
#: (ancho, alto) que suman bordes + barra de título al tamaño del contenido. Es un piso: si Qt
#: informa un marco real más grande se usa ese.
MARCO_DEFECTO = (16, 40)

_PROP = "_ventana_ajustada"
_NOMBRE_SCROLL = "_ajuste_scroll"
_NATIVOS = (widget.QMessageBox, widget.QFileDialog, widget.QInputDialog, widget.QColorDialog, widget.QFontDialog)


# ── geometría (pura, sin Qt) ─────────────────────────────────────────────────
def calcular_geometria(area, tam, minimo=(0, 0), marco=MARCO_DEFECTO, fraccion=FRACCION, centro=None):
    """Tamaño y posición para que una ventana entre en ``area``.

    :param area: ``(x, y, ancho, alto)`` del área útil del monitor (sin barra de tareas).
    :param tam: ``(ancho, alto)`` deseado del **contenido**.
    :param minimo: ``(ancho, alto)`` mínimo declarado; se baja si no entra.
    :param marco: ``(ancho, alto)`` que suma el marco (bordes + barra de título).
    :param centro: ``(x, y)`` sobre el que centrarla; por defecto el centro del área.
    :returns: ``dict`` con ``x, y`` (esquina del **marco**), ``w, h`` (contenido), ``min_w, min_h``,
        ``max_w, max_h`` (lo máximo que entra).
    """
    ax, ay, aw, ah = area
    max_w = max(int(aw * fraccion) - marco[0], 1)
    max_h = max(int(ah * fraccion) - marco[1], 1)
    min_w, min_h = min(minimo[0], max_w), min(minimo[1], max_h)
    w = max(min(tam[0], max_w), min_w)
    h = max(min(tam[1], max_h), min_h)

    total_w, total_h = w + marco[0], h + marco[1]
    cx, cy = centro if centro is not None else (ax + aw / 2, ay + ah / 2)
    x = max(ax, min(int(cx - total_w / 2), ax + aw - total_w))
    y = max(ay, min(int(cy - total_h / 2), ay + ah - total_h))
    return {"x": x, "y": y, "w": w, "h": h, "min_w": min_w, "min_h": min_h, "max_w": max_w, "max_h": max_h}


# ── pantalla ─────────────────────────────────────────────────────────────────
def pantalla_para(win):
    """El monitor donde está el sistema: el de la ventana madre; si no hay, el de la ventana
    activa; si no, el del cursor; si no, el principal."""
    app = widget.QApplication.instance()
    referencias = [win.parentWidget().window() if win.parentWidget() is not None else None,
                   app.activeWindow() if app is not None else None]
    for ref in referencias:
        if ref is None or ref is win:
            continue
        handle = ref.windowHandle()
        if handle is not None and handle.screen() is not None:
            return handle.screen()
        pantalla = gui.QGuiApplication.screenAt(ref.frameGeometry().center())
        if pantalla is not None:
            return pantalla
    return gui.QGuiApplication.screenAt(gui.QCursor.pos()) or gui.QGuiApplication.primaryScreen()


def area_disponible(win):
    """``QRect`` útil (sin barra de tareas) del monitor donde está el sistema."""
    return pantalla_para(win).availableGeometry()


def _referencia(win):
    """Ventana sobre la que centrar: la madre; si no hay, la activa."""
    app = widget.QApplication.instance()
    ref = win.parentWidget().window() if win.parentWidget() is not None else (app.activeWindow() if app else None)
    return ref if ref is not None and ref is not win and ref.isVisible() else None


# ── scroll ───────────────────────────────────────────────────────────────────
def hacer_desplazable(dialogo):
    """Envuelve el contenido de un diálogo en un ``QScrollArea``. Conserva el layout (grillas
    incluidas): Qt permite sacarle el layout a un widget y dárselo a otro."""
    layout = dialogo.layout()
    if layout is None or dialogo.findChild(widget.QScrollArea, _NOMBRE_SCROLL) is not None:
        return False
    contenedor = widget.QWidget()
    contenedor.setLayout(layout)                 # le saca el layout al diálogo, con todos sus widgets
    scroll = widget.QScrollArea()
    scroll.setObjectName(_NOMBRE_SCROLL)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(widget.QFrame.NoFrame)
    scroll.setWidget(contenedor)
    nuevo = widget.QVBoxLayout(dialogo)
    nuevo.setContentsMargins(0, 0, 0, 0)
    nuevo.addWidget(scroll)
    return True


# ── ajuste ───────────────────────────────────────────────────────────────────
def _es_ajustable(win):
    if not win.isWindow() or isinstance(win, _NATIVOS):
        return False
    if win.isMaximized() or win.isFullScreen():
        return False
    # OJO: se compara el TIPO de ventana, no los bits: ``flags & Qt.Tool`` da verdadero para
    # cualquier QDialog porque los bits de Qt.Dialog están contenidos en los de Qt.Tool.
    if win.windowType() in (core.Qt.Tool, core.Qt.Popup, core.Qt.ToolTip, core.Qt.SplashScreen):
        return False                                           # toasts, menús, avisos flotantes
    return not (win.windowFlags() & core.Qt.FramelessWindowHint)


def ajustar_ventana(win):
    """Hace que ``win`` entre en la pantalla. Devuelve ``True`` si cambió algo."""
    if not _es_ajustable(win):
        return False
    r = area_disponible(win)
    area = (r.x(), r.y(), r.width(), r.height())
    frame, geom = win.frameGeometry(), win.geometry()
    marco = (max(MARCO_DEFECTO[0], frame.width() - geom.width()), max(MARCO_DEFECTO[1], frame.height() - geom.height()))

    # El contenido no entra ni en su mínimo: se le da scroll. El umbral es el área útil completa
    # (no el 96 % con que se dimensiona): una ventana que apenas ocupa el alto es mejor que un
    # scroll anidado.
    max_w = int(r.width() * FRACCION) - marco[0]
    max_h = int(r.height() * FRACCION) - marco[1]
    hint = win.minimumSizeHint()
    no_entra = hint.height() > r.height() - marco[1] or hint.width() > r.width() - marco[0]
    if no_entra and hacer_desplazable(win):
        win.setMinimumSize(0, 0)
        # ancho para que no haga falta scroll horizontal (+ la barra vertical) y todo el alto útil
        win.resize(min(max(win.width(), hint.width() + 24), max_w), max_h)

    minimo = win.minimumSize()
    fijo = win.minimumSize() == win.maximumSize() and not win.minimumSize().isEmpty()
    ref = _referencia(win)
    centro = (ref.frameGeometry().center().x(), ref.frameGeometry().center().y()) if ref is not None else None
    g = calcular_geometria(area, (win.width(), win.height()), (minimo.width(), minimo.height()), marco, FRACCION, centro)

    cambio_tam = (g["w"], g["h"]) != (win.width(), win.height())
    fuera = not r.contains(frame)
    if (minimo.width(), minimo.height()) != (g["min_w"], g["min_h"]):
        win.setMinimumSize(g["min_w"], g["min_h"])
    if fijo:
        win.setMaximumSize(g["w"], g["h"])
    elif win.maximumWidth() < g["w"] or win.maximumHeight() < g["h"]:
        win.setMaximumSize(g["w"], g["h"])
    if cambio_tam:
        win.resize(g["w"], g["h"])
    if cambio_tam or fuera:
        win.move(g["x"], g["y"])
    return bool(cambio_tam or fuera)


class AjustadorDeVentanas(core.QObject):
    """Filtro de eventos de la aplicación: ajusta cada ``QDialog`` la primera vez que se muestra."""

    def eventFilter(self, obj, evento):
        if (evento.type() == core.QEvent.Show and isinstance(obj, widget.QDialog)
                and obj.isWindow() and not obj.property(_PROP)):
            obj.setProperty(_PROP, True)       # una sola vez: no pisa lo que el usuario haga después
            try:
                ajustar_ventana(obj)
            except Exception:  # noqa: BLE001 — un fallo de acomodo nunca debe impedir abrir la ventana
                pass
        return False


_instalado = None


def instalar(app):
    """Instala el ajustador en la aplicación (idempotente) y lo devuelve."""
    global _instalado
    if _instalado is None:
        _instalado = AjustadorDeVentanas(app)
        app.installEventFilter(_instalado)
    return _instalado


def limitar_minimo(win, ancho, alto):
    """``setMinimumSize`` que no pasa del área útil del monitor (para ventanas principales)."""
    r = area_disponible(win)
    win.setMinimumSize(min(ancho, int(r.width() * FRACCION)), min(alto, int(r.height() * FRACCION) - MARCO_DEFECTO[1]))
