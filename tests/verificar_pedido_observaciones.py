"""Observaciones del pedido en la PC (src/Views/Pedidos/programarPedido.py): el cuadro del diálogo "Nuevo Pedido", el detalle
del pedido y la grilla. Y que la PC siga funcionando si la base todavía NO tiene la columna `pedido.observaciones`
(la agrega `movil/migrar.py`): no debe fallar al crear ni al cargar pedidos.

La parte de base corre dentro de UNA transacción que se revierte: commit() y close() de las conexiones que usa la app
quedan anulados, y la columna se agrega / se quita solo ahí adentro.

    QT_QPA_PLATFORM=offscreen python tests/verificar_pedido_observaciones.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox, QTableWidget, QTableWidgetItem

from movil import migraciones
from src.Views.Pedidos import programarPedido as pp

app = QApplication.instance() or QApplication([])
fallas = []


def check(nombre, cond, extra=""):
    print(("OK   " if cond else "FALLA"), nombre, extra)
    if not cond:
        fallas.append(nombre)


avisos = []   # los cuadros de aviso no bloquean la prueba, pero se anotan
for m in ("information", "critical"):
    setattr(QMessageBox, m, staticmethod(lambda *a, **k: None))
QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(" ".join(str(x) for x in a[1:])))   # título y texto

# ── 1. sin base: el resumen y la fila de la grilla ────────────────────────────
print("=== resumen y grilla (sin base) ===")
check("el resumen junta los renglones en uno", pp._resumen_observaciones("Dejar en la portería\nLlamar antes") == "Dejar en la portería Llamar antes")
largo = "x" * 200
check("el resumen se corta con … al largo pedido", len(pp._resumen_observaciones(largo, 60)) == 60 and pp._resumen_observaciones(largo, 60).endswith("…"))
check("un texto corto queda igual", pp._resumen_observaciones("Portón rojo") == "Portón rojo")
check("el tope es el mismo que el de la API y la app", pp.OBSERVACIONES_MAX == 500)

tabla = QTableWidget(2, 6)
ventana = pp.VentanaProgramarPedido.__new__(pp.VentanaProgramarPedido)
hoy = __import__("datetime").date(2026, 11, 6)
pp.VentanaProgramarPedido._fila_pedido(ventana, tabla, 0, 1, "ACME", "20-1", hoy, None, "pendiente", observaciones="Dejar en la portería\nLlamar antes de ir")
pp.VentanaProgramarPedido._fila_pedido(ventana, tabla, 1, 2, "BETA", "20-2", hoy, None, "pendiente")


def textos(celda):
    return [l.text() for l in celda.findChildren(QLabel)]


con_obs, sin_obs = tabla.cellWidget(0, 1), tabla.cellWidget(1, 1)
check("con observaciones: el subtítulo trae el CUIT y el resumen", any("CUIT 20-1" in t and "Obs.: Dejar en la portería Llamar antes de ir" in t for t in textos(con_obs)), textos(con_obs))
check("con observaciones: el mouse encima las muestra enteras (con sus renglones)", con_obs.toolTip() == "Dejar en la portería\nLlamar antes de ir", repr(con_obs.toolTip()))
check("sin observaciones: ni resumen ni ayuda", not any("Obs." in t for t in textos(sin_obs)) and sin_obs.toolTip() == "", textos(sin_obs))

# ── 2. con base (transacción revertida) ───────────────────────────────────────
try:
    real = pp._conexion()
except Exception as e:  # sin base disponible no se puede seguir
    print("SIN BASE:", e)
    sys.exit(1 if fallas else 0)


class _Proxy:
    """commit() y close() no hacen nada: todo se revierte al final."""
    def __init__(self, real):
        self._real = real

    def commit(self):
        pass

    def close(self):
        pass

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


real.autocommit = False
con = _Proxy(real)
pp._conexion = lambda: con
cur = con.cursor()


def nuevo_dialogo(observaciones):
    d = pp.DialogoNuevoPedido(None, None)
    d.combo_cliente.setCurrentIndex(0)
    d.tabla_productos.setRowCount(1)
    d.tabla_productos.setItem(0, d._NP_ID, QTableWidgetItem(id_producto))
    d.tabla_productos.setItem(0, d._NP_CANT, QTableWidgetItem("2"))
    d.txt_observaciones.setPlainText(observaciones)
    return d


def ultimo_pedido():
    cur.execute("SELECT max(id_pedido) FROM pedido")
    return cur.fetchone()[0]


try:
    cur.execute("SELECT id_producto FROM Producto ORDER BY id_producto LIMIT 1")
    id_producto = cur.fetchone()[0]

    print("=== la base NO tiene la columna (todavía no se migró): la PC sigue andando ===")
    cur.execute("ALTER TABLE pedido DROP COLUMN IF EXISTS observaciones")
    pp._OBSERVACIONES_EN_LA_BASE = False
    check("la PC detecta que falta la columna", pp._observaciones_disponibles(con) is False)
    avisos.clear()
    d = nuevo_dialogo("Dejar en la portería")
    previo = ultimo_pedido()
    d.crear_pedido()
    creado = ultimo_pedido()
    check("crear un pedido con observaciones NO falla: se crea igual", creado != previo and d.pedido_fue_creado)
    check("y avisa que las observaciones no se guardaron (con el comando para arreglarlo)", len(avisos) == 1 and "migrar.py" in avisos[0], avisos)
    det = pp.VentanaDetallePedido(creado, None, None)
    check("el detalle abre igual y no muestra la tarjeta de observaciones", det._card_obs.isHidden())
    avisos.clear()
    d2 = nuevo_dialogo("")
    d2.crear_pedido()
    check("sin observaciones: se crea y no avisa nada", d2.pedido_fue_creado and avisos == [])

    print("=== la base YA tiene la columna ===")
    migraciones.aplicar(real)   # agrega la columna, dentro de esta transacción
    pp._OBSERVACIONES_EN_LA_BASE = False
    check("la PC detecta la columna", pp._observaciones_disponibles(con) is True)
    avisos.clear()
    d3 = nuevo_dialogo("  Dejar en la portería\nLlamar antes de ir  ")
    d3.crear_pedido()
    id3 = ultimo_pedido()
    cur.execute("SELECT observaciones FROM pedido WHERE id_pedido = %s", (id3,))
    check("el pedido se crea con sus observaciones, sin espacios sobrantes en los bordes y con sus renglones",
          cur.fetchone()[0] == "Dejar en la portería\nLlamar antes de ir")
    check("y no avisa nada raro", avisos == [], avisos)
    cur.execute("SELECT origen, observaciones IS NULL FROM pedido WHERE id_pedido = %s", (id3,))
    check("un pedido de la PC (origen pc)", cur.fetchone()[0] == "pc")

    d4 = nuevo_dialogo("   ")
    d4.crear_pedido()
    cur.execute("SELECT observaciones FROM pedido WHERE id_pedido = %s", (ultimo_pedido(),))
    check("observaciones en blanco -> NULL (no un texto vacío)", cur.fetchone()[0] is None)

    d5 = pp.DialogoNuevoPedido(None, None)
    d5.txt_observaciones.setPlainText("x" * 700)
    check("el cuadro no deja pasar del tope", len(d5.txt_observaciones.toPlainText()) == pp.OBSERVACIONES_MAX)

    det3 = pp.VentanaDetallePedido(id3, None, None)
    check("el detalle muestra la tarjeta con las observaciones", not det3._card_obs.isHidden() and det3._lbl_obs.text() == "Dejar en la portería\nLlamar antes de ir", det3._lbl_obs.text())
    det_sin = pp.VentanaDetallePedido(ultimo_pedido(), None, None)
    check("un pedido sin observaciones no muestra la tarjeta", det_sin._card_obs.isHidden())

    # un pedido que viene del celular, con observaciones, aparece con ellas en la grilla de pendientes
    cur.execute("INSERT INTO pedido (id_cliente, fecha_pedido, estado_pedido, origen, creado_por, observaciones) "
                "SELECT id_cliente, CURRENT_DATE, 'pendiente', 'movil', 'jose', 'Cobrar en efectivo' FROM cliente LIMIT 1 RETURNING id_pedido")
    id_movil = cur.fetchone()[0]
    v = pp.VentanaProgramarPedido.__new__(pp.VentanaProgramarPedido)
    v.obtener_conexion = lambda: con
    v.tabla_pendientes = QTableWidget(0, 6)
    v.contador_pendientes = QLabel()
    v._actualizar_kpis = lambda: None
    v._fila_pedido = lambda *a, **k: pp.VentanaProgramarPedido._fila_pedido(v, *a, **k)
    pp.VentanaProgramarPedido.cargar_pedidos_pendientes(v)
    fila = next(i for i in range(v.tabla_pendientes.rowCount()) if v.tabla_pendientes.item(i, 0).text() == str(id_movil))
    check("la grilla de pendientes carga con la columna nueva y muestra las observaciones de un pedido del celular",
          v.tabla_pendientes.cellWidget(fila, 1).toolTip() == "Cobrar en efectivo")
    v2 = pp.VentanaProgramarPedido.__new__(pp.VentanaProgramarPedido)
    v2.obtener_conexion = lambda: con
    v2.tabla_entregados = QTableWidget(0, 6)
    v2.contador_entregados = QLabel()
    v2._actualizar_kpis = lambda: None
    v2._fila_pedido = lambda *a, **k: pp.VentanaProgramarPedido._fila_pedido(v2, *a, **k)
    pp.VentanaProgramarPedido.cargar_pedidos_entregados(v2)
    check("la grilla de entregados también carga con la columna nueva", v2.tabla_entregados.rowCount() >= 0)
finally:
    real.rollback()
    real.close()
    pp._OBSERVACIONES_EN_LA_BASE = False

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S): {fallas}")
sys.exit(1 if fallas else 0)
