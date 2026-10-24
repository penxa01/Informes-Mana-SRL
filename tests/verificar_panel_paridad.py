"""Paridad del panel del celular (movil/panel/) con el escritorio, con los DATOS REALES.

1. El mapa de medidas y las reglas de litros de `movil/panel/litros.py` son una copia de las de
   `src/Views/Litros/LitrosDBF.py`: tienen que ser idénticas (si se agrega un CODMEDIDA nuevo en
   el escritorio y no acá, esto falla).
2. Litros del mes y litros Premium: el panel (lee con dbfread) contra el informe de Litros del
   escritorio (`ReportLts`, con los datos que carga la app) para el mismo período.
3. Recaudado de la semana: el panel contra el cálculo hecho con los datos de Cuentas Corrientes.

Solo lee archivos. Tarda ~1 minuto (lee fachist.DBF, 80 MB).

    QT_QPA_PLATFORM=offscreen python tests/verificar_panel_paridad.py
"""
import datetime as dt
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.controllers import config, cuentas_corrientes_io, dbf_io
from src.Views.Litros import LitrosDBF as desktop

from movil.panel import calculo, lectura, litros, recaudado

fallas = []


def check(nombre, cond, extra=""):
    print(("OK   " if cond else "FALLA"), nombre, extra)
    if not cond:
        fallas.append(nombre)


print("=== 1. reglas copiadas del escritorio ===")
check("mapa de medidas idéntico", litros._CODMEDIDA_LITROS == desktop._CODMEDIDA_LITROS,
      f"{len(litros._CODMEDIDA_LITROS)} vs {len(desktop._CODMEDIDA_LITROS)} entradas")
muestras = list(desktop._CODMEDIDA_LITROS) + ["7 lts", "12 L", "caja", "0.25 l", "", "  500 C  "]
check("misma conversión a litros para todos los códigos y varios no mapeados",
      all(litros.codmedida_a_litros(m) == desktop._codmedida_a_litros(m) for m in muestras))
skus = ["L100", "l55", "01VA133", "ABC", "01va133", "99XX12", "1234", "L"]
check("misma clasificación de proveedor",
      all(litros.clasificar_proveedor(s) == desktop.ReportLts._clasificar_proveedor(None, s) for s in skus))
check("mismos tipos de comprobante que la pantalla de Litros", set(litros.TC_LITROS) == {"FC", "NC", "ND", "FE", "CR"})

print("=== 2. litros del mes: panel vs informe del escritorio ===")
hoy = dt.date.today()
p = calculo.periodos(hoy)
desde, hasta = p["mes"]
print(f"   período {desde} a {hasta} | datos en {config.DBF_BASE_PATH} ({config.ENTORNO})")

t0 = time.time()
ventas_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "fachist.DBF"), lectura.COLUMNAS_VENTAS)
abmartic_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "abmartic.DBF"), lectura.COLUMNAS_ABMARTIC)
clasif = lectura.leer_clasificacion(config.EXCEL_LITROS_PATH)
print(f"   lectura del panel: {time.time() - t0:.1f} s, {len(ventas_panel)} renglones de ventas")
mio = litros.periodo(ventas_panel, abmartic_panel, clasif, desde, hasta)

# El escritorio: carga con su propio lector y filtra igual que src/ui/paginas/litros.py
df_ventas = dbf_io.leer_dbf_cacheado(
    os.path.join(config.DBF_BASE_PATH, "fachist.DBF"), os.path.join(config.CACHE_PATH, "fachist.parquet"), dbf_io.COLUMNAS_VENTAS)
df_ventas["FECHA"] = pd.to_datetime(df_ventas["FECHA"])
filtro = (df_ventas["FECHA"] >= pd.Timestamp(desde)) & (df_ventas["FECHA"] <= pd.Timestamp(hasta)) & df_ventas["TC"].isin(["FC", "NC", "ND", "FE", "CR"])
periodo_escritorio = df_ventas[filtro]
check("hay ventas en el período (si no, la comparación no prueba nada)", len(periodo_escritorio) > 0, f"{len(periodo_escritorio)} renglones")

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
informe = desktop.ReportLts(periodo_escritorio, df_ventas=df_ventas, graficos=False)
informe.hide()
print(f"   escritorio: {informe.TotalLts:,.2f} L ({informe.TotalPremium:,.2f} premium)   panel: {mio['litros']:,.2f} L ({mio['premium']:,.2f} premium, {mio['pct_premium']} %)")
check("litros totales iguales", abs(mio["litros"] - informe.TotalLts) < 0.01, f"dif {mio['litros'] - informe.TotalLts:+.2f}")
check("litros premium iguales", abs(mio["premium"] - informe.TotalPremium) < 0.01, f"dif {mio['premium'] - informe.TotalPremium:+.2f}")
pct_escritorio = round(informe.TotalPremium / informe.TotalLts * 100, 1) if informe.TotalLts else 0.0
check("mismo % premium que el KPI del escritorio", mio["pct_premium"] == pct_escritorio, f"{mio['pct_premium']} vs {pct_escritorio}")
check("la serie por día suma los litros del mes (± centavos de redondeo)",
      abs(sum(d["litros"] for d in mio["por_dia"]) - mio["litros"]) < 0.5, f"{sum(d['litros'] for d in mio['por_dia']):.2f}")

print("=== 3. recaudado de la semana: panel vs Cuentas Corrientes ===")
sem_desde, sem_hasta = p["semana"]
t0 = time.time()
ctacorr_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "ctacorr.DBF"), lectura.COLUMNAS_CTACORR)
print(f"   lectura de ctacorr: {time.time() - t0:.1f} s, {len(ctacorr_panel)} renglones")
rec = recaudado.periodo(ctacorr_panel, sem_desde, sem_hasta)

ctacorr_cc, _ = cuentas_corrientes_io.cargar_datos()
tc = ctacorr_cc["TC"].astype(str).str.strip().str.upper()
fechas = pd.to_datetime(ctacorr_cc["FECHA"])
esperado = -pd.to_numeric(ctacorr_cc.loc[(tc == "RC") & (fechas >= pd.Timestamp(sem_desde)) & (fechas <= pd.Timestamp(sem_hasta)), "TOTALL"], errors="coerce").sum()
print(f"   semana {sem_desde} a {sem_hasta}: panel ${rec['total']:,.2f} en {rec['recibos']} recibos | Cuentas Corrientes ${esperado:,.2f}")
check("hay recibos en la semana (si no, no prueba nada; los lunes puede no haber)", rec["recibos"] > 0 or hoy.weekday() == 0)
check("recaudado igual al de Cuentas Corrientes", abs(rec["total"] - float(esperado)) < 0.01, f"dif {rec['total'] - float(esperado):+.2f}")
positivos = ctacorr_cc.loc[(tc == "RC") & (pd.to_numeric(ctacorr_cc["TOTALL"], errors="coerce") > 0)]
check("ningún recibo con importe positivo (si hubiera, serían anulaciones y habría que mirarlos)", len(positivos) == 0, f"{len(positivos)} encontrados")

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S): {fallas}")
sys.exit(1 if fallas else 0)
