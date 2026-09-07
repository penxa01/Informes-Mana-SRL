"""Verificación funcional del rediseño de Margen / Detalle Beneficio.

Levanta la ventana real con datos reales (fachist + catálogos), ejerce filtros,
edición de costo con cascada bidireccional, y toma screenshots.

Correr desde la raíz:  python tests/verificar_beneficio_ui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import PyQt5.QtWidgets as widget

from src.controllers import config, dbf_io
from src.Views.Beneficio.margenBeneficio import margenBeneficio, _C_SKU, _C_COSTO, _C_MARGEN
from src.Views.Beneficio.DetalleBeneficio import DetalleDialog, _D_COSTO
from src.ui.widgets.indicadores import barra_porcentaje, color_margen

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


app = widget.QApplication([])

print("=== 0. widget indicadores ===")
check("color >25 verde", color_margen(30) == "#059669")
check("color 22 ambar", color_margen(22) == "#d97706")
check("color 10 rojo", color_margen(10) == "#e11d48")
b = barra_porcentaje(21.31)
check("barra_porcentaje devuelve QWidget", isinstance(b, widget.QWidget))

print("=== 1. cargar período real desde fachist ===")
cols = ["FECHA", "MODELO", "U_VENDIDAS", "TOTAVEN", "CUENTA", "TC", "NC", "DESC"]
fachist = dbf_io.leer_dbf_cacheado(
    os.path.join(config.DBF_BASE_PATH, "fachist.DBF"),
    os.path.join(config.CACHE_PATH, "fachist.parquet"),
    cols,
)
fachist["FECHA"] = pd.to_datetime(fachist["FECHA"], errors="coerce")
desde = pd.Timestamp("2025-01-01")
hasta = pd.Timestamp("2025-06-30 23:59:59")
mask = (
    (fachist["FECHA"] >= desde) & (fachist["FECHA"] <= hasta)
    & fachist["MODELO"].astype(str).str.startswith("L")
    & fachist["TC"].isin(["FC", "NC", "ND", "FE"])
)
periodo = fachist[mask]
print(f"   período: {periodo.shape}")
check("hay filas en el período", len(periodo) > 50, f"{len(periodo)}")

win = margenBeneficio()
win.resize(1360, 820)
win.cargar(periodo)
app.processEvents()

tabla = win.tabla
n_prod = tabla.rowCount()
print(f"   productos en tabla: {n_prod}")
check("tabla poblada", n_prod > 0)
check("8 columnas", tabla.columnCount() == 8)
check("header # / SKU / Acción",
      [tabla.horizontalHeaderItem(i).text() for i in (0, 1, 7)] == ["#", "SKU", "Acción"])
check("celda Margen % es cell widget (barra)", tabla.cellWidget(0, 6) is not None)
check("info_periodo actualizado", "Registros de ventas" in win.info_periodo.text())
check("pill Total Ventas con valor", win.label_total_ventas[1].text() not in ("—", ""))

print("=== 2. filtro por texto ===")
sku0 = tabla.item(0, _C_SKU).text()
win.search_input.setText(sku0)
app.processEvents()
check("filtro reduce filas", tabla.rowCount() <= n_prod and tabla.rowCount() >= 1, f"{tabla.rowCount()}")
check("fila filtrada corresponde", tabla.item(0, _C_SKU).text() == sku0)
win.limpiar_busqueda()
app.processEvents()
check("limpiar restaura filas", tabla.rowCount() == n_prod, f"{tabla.rowCount()} vs {n_prod}")

print("=== 3. preset de margen ===")
win._toggle_preset("alto")
app.processEvents()
altos = win.datos_originales[win.datos_originales["Margen %"] > 25]
check("preset >25% filtra bien", tabla.rowCount() == len(altos), f"{tabla.rowCount()} vs {len(altos)}")
win._toggle_preset("alto")  # apagar
app.processEvents()
check("apagar preset restaura", tabla.rowCount() == n_prod)

print("=== 4. edición de costo en tabla principal (recalcula margen) ===")
fila = 0
sku_edit = tabla.item(fila, _C_SKU).text()
margen_antes = tabla.item(fila, _C_MARGEN).text()
tabla.item(fila, _C_COSTO).setText("999999.0000")  # dispara cellChanged
app.processEvents()
margen_desp = tabla.item(fila, _C_MARGEN).text()
check("margen cambió tras editar costo", margen_antes != margen_desp, f"{margen_antes} -> {margen_desp}")
row_ct = win.content_table[win.content_table["SKU"].astype(str) == sku_edit].iloc[0]
check("content_table.Costo actualizado", abs(row_ct["Costo"] - 999999.0) < 1e-3)
row_orig = win.datos_originales[win.datos_originales["SKU"].astype(str) == sku_edit].iloc[0]
check("datos_originales.Costo sincronizado", abs(row_orig["Costo"] - 999999.0) < 1e-3)

print("=== 5. DetalleDialog: banner, tabla, filtros ===")
dlg = DetalleDialog(sku_edit, win.obtener_nombre_producto(sku_edit),
                    win.detalles_por_sku[sku_edit], win.clientes_dict, win,
                    on_costo_cambiado_cb=lambda: win._cascada_desde_detalle(sku_edit))
dlg.resize(1300, 720)
app.processEvents()
td = dlg.tabla_detalle
n_lineas = td.rowCount()
print(f"   líneas de detalle: {n_lineas}")
check("detalle 13 columnas", td.columnCount() == 13)
check("detalle poblado", n_lineas == len(win.detalles_por_sku[sku_edit]))
check("KPI Total Beneficio con valor", dlg._kpi_benef.text() not in ("—", ""))
check("pie Margen con valor", dlg._foot_margen[1].text() not in ("—", ""))
check("barra Margen % en detalle", td.cellWidget(0, 12) is not None)

dlg.buscar.setText("zzz-no-existe-nada")
app.processEvents()
ocultas = sum(td.isRowHidden(r) for r in range(n_lineas))
check("búsqueda sin match oculta todo", ocultas == n_lineas, f"{ocultas}/{n_lineas}")
dlg._limpiar_filtros()
app.processEvents()
check("limpiar muestra todo de nuevo", sum(td.isRowHidden(r) for r in range(n_lineas)) == 0)

print("=== 6. cascada detalle -> tabla principal ===")
margen_princ_antes = tabla.item(fila, _C_MARGEN).text()
td.item(0, _D_COSTO).setText("$ 0,00")  # costo 0 -> margen máximo en esa línea
app.processEvents()
check("cascada actualizó la fila del SKU en la tabla principal",
      tabla.item(fila, _C_MARGEN).text() != margen_princ_antes,
      f"{margen_princ_antes} -> {tabla.item(fila, _C_MARGEN).text()}")
det0 = win.detalles_por_sku[sku_edit][0]
check("detalle[0].PRECIO_COSTO = 0 (referencia compartida)", abs(det0["PRECIO_COSTO"]) < 1e-6)

print("=== 7. screenshots ===")
out1 = r"D:\Trabajo\SoftInformes\App PyQt5 y Pandas\scratch_margen.png"
out2 = r"D:\Trabajo\SoftInformes\App PyQt5 y Pandas\scratch_detalle.png"
win.grab().save(out1)
dlg.grab().save(out2)
print(f"   {out1}")
print(f"   {out2}")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
