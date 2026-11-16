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
tabla_escritorio = informe.content_table
for proveedor in litros.PROVEEDORES:
    del_proveedor = tabla_escritorio[tabla_escritorio["Proveedor"] == proveedor]
    esperado = (round(float(del_proveedor["Litros"].sum()), 2), round(float(del_proveedor.loc[del_proveedor["Premium"] == "Premium", "Litros"].sum()), 2))
    mio_p = (mio["por_proveedor"][proveedor]["litros"], mio["por_proveedor"][proveedor]["premium"])
    check(f"{proveedor}: litros y premium iguales a los de la tabla del escritorio", mio_p == esperado, f"{mio_p} vs {esperado}")
check("los tres proveedores suman el total", abs(sum(v["litros"] for v in mio["por_proveedor"].values()) - mio["litros"]) < 0.01)
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

print("=== 4. desglose del recaudado (plan_caj + placaja) con datos reales ===")
t0 = time.time()
recibos_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "plan_caj.DBF"), lectura.COLUMNAS_RECIBOS, tolerante=True)
caja_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "placaja.DBF"), lectura.COLUMNAS_CAJA, tolerante=True)
print(f"   lectura: {time.time() - t0:.1f} s, {len(recibos_panel)} comprobantes y {len(caja_panel)} movimientos de caja")

# Semana cerrada (lunes 19 a domingo 25/10/2026), con los montos que salieron del análisis hecho aparte
# (cruce de pandas recibo por recibo): los datos pasados no cambian, así que sirve de regresión.
fijo = recaudado.desglose(recibos_panel, caja_panel, dt.date(2026, 10, 19), dt.date(2026, 10, 25))
esperado_fijo = {"total": 95868623.02, "recibos": 117, "efectivo": 10474725.58, "transferencia": 13709020.17 + 15103796.14,
                 "cheques": 55812436.87, "retenciones": 768644.26, "otros": 0.0}
for k, v in esperado_fijo.items():
    check(f"semana 19-25/10, {k}", abs(fijo[k] - v) < 0.02, f"{fijo[k]:,.2f} vs {v:,.2f}")

# Cualquier semana: el desglose cuadra con el total que ya muestra el panel (ctacorr) y no deja resto escondido.
for nombre in ("semana", "semana_anterior"):
    r_desde, r_hasta = p[nombre]
    d = recaudado.desglose(recibos_panel, caja_panel, r_desde, r_hasta)
    total_ctacorr = recaudado.periodo(ctacorr_panel, r_desde, r_hasta)["total"]
    print(f"   {nombre} {r_desde} a {r_hasta}: {d}")
    check(f"{nombre}: total de plan_caj = total de ctacorr (el que ya mostraba el panel)", abs(d["total"] - total_ctacorr) < 0.01,
          f"{d['total']:,.2f} vs {total_ctacorr:,.2f}")
    check(f"{nombre}: los cinco medios suman el total",
          abs(d["efectivo"] + d["transferencia"] + d["cheques"] + d["retenciones"] + d["otros"] - d["total"]) < 0.01)
    # "otros" tiene que ser solo tarjetas/documentos: si trajera un efectivo sin ligar, el cruce con placaja falló.
    check(f"{nombre}: ningún efectivo quedó sin ligar con placaja (otros chico)", abs(d["otros"]) < 0.01 * max(d["total"], 1) + 1e-9,
          f"otros {d['otros']:,.2f}")
completo = calculo.calcular(ventas_panel, abmartic_panel, clasif, ctacorr_panel, hoy, recibos_panel, caja_panel)
check("calcular() trae el desglose de la semana y su diferencia con ctacorr es 0",
      completo["recaudado"]["semana"]["desglose"]["diferencia"] == 0.0, str(completo["recaudado"]["semana"]["desglose"]))

print("=== 5. panel de cada vendedor: la suma de todos cuadra con el panel general y con Cuentas Corrientes ===")
from movil.panel import vendedores

t0 = time.time()
clientes_panel = lectura.leer_dbf(os.path.join(config.DBF_BASE_PATH, "ctaclien.DBF"), lectura.COLUMNAS_CLIENTES)
todos = vendedores.calcular(ventas_panel, abmartic_panel, clasif, ctacorr_panel, clientes_panel, recibos_panel, caja_panel, hoy, p)
print(f"   cálculo de los vendedores: {time.time() - t0:.1f} s; vendedores {sorted(todos['vendedores'], key=int)}")
vs = todos["vendedores"]
check("mismos tipos de comprobante contables que Cuentas Corrientes", vendedores.TC_CONTABLES == cuentas_corrientes_io.TC_CONTABLES)
check("mismo umbral de saldo que Cuentas Corrientes", vendedores.UMBRAL_SALDO == cuentas_corrientes_io.UMBRAL_SALDO)

# litros: cada litro lo vendió un vendedor
suma_litros = sum(v["litros"]["mes"]["litros"] for v in vs.values())
suma_premium = sum(v["litros"]["mes"]["premium"] for v in vs.values())
check("litros del mes: la suma de los vendedores = el panel general", abs(suma_litros - mio["litros"]) < 0.05, f"{suma_litros:,.2f} vs {mio['litros']:,.2f}")
check("premium del mes: la suma de los vendedores = el panel general", abs(suma_premium - mio["premium"]) < 0.05, f"{suma_premium:,.2f} vs {mio['premium']:,.2f}")
for proveedor in litros.PROVEEDORES:
    suma = sum(v["litros"]["mes"]["por_proveedor"][proveedor]["litros"] for v in vs.values())
    check(f"litros de {proveedor}: la suma de los vendedores = el panel general", abs(suma - mio["por_proveedor"][proveedor]["litros"]) < 0.05, f"{suma:,.2f}")
anterior = litros.periodo(ventas_panel, abmartic_panel, clasif, *p["mes_anterior"])
suma_ant = sum(v["litros"]["mes_anterior"]["litros"] for v in vs.values())
check("litros del mes anterior: la suma de los vendedores = el panel general", abs(suma_ant - anterior["litros"]) < 0.05, f"{suma_ant:,.2f} vs {anterior['litros']:,.2f}")

# cobrado: cada recibo es de un vendedor; para cualquier mes la suma da el desglose general
dif_cobrado = []
for clave, m_desde, m_hasta in vendedores.meses(hoy):
    general_mes = recaudado.desglose(recibos_panel, caja_panel, m_desde, m_hasta)
    for medio in ("total", "efectivo", "transferencia", "cheques", "retenciones", "otros"):
        suma = sum(v["cobrado"][clave][medio] for v in vs.values())
        if abs(suma - general_mes[medio]) >= 0.02:
            dif_cobrado.append(f"{clave} {medio}: {suma:,.2f} vs {general_mes[medio]:,.2f}")
    suma_recibos = sum(v["cobrado"][clave]["recibos"] for v in vs.values())
    if suma_recibos != general_mes["recibos"]:
        dif_cobrado.append(f"{clave} recibos: {suma_recibos} vs {general_mes['recibos']}")
check("cobrado de los 12 meses: la suma de los vendedores = el desglose general en cada medio de pago y cantidad de recibos",
      not dif_cobrado, "; ".join(dif_cobrado[:4]))

# cartera: contra Cuentas Corrientes del escritorio (todas las facturas, sin filtro de fecha de emisión)
ctacorr_cc, clientes_cc = cuentas_corrientes_io.cargar_datos()
desde_siempre = dt.date(1990, 1, 1)
deudores = cuentas_corrientes_io.calcular_deudores(ctacorr_cc, clientes_cc, desde_siempre)
en_calle = sum(v["cartera"]["en_calle"] for v in vs.values())
check("en calle: la suma de los vendedores = el saldo bruto de Cuentas Corrientes", abs(en_calle - float(deudores["Saldo"].sum())) < 0.05,
      f"{en_calle:,.2f} vs {float(deudores['Saldo'].sum()):,.2f}")
check("en calle = vencido + por vencer + al día, en todos los vendedores",
      all(abs(v["cartera"]["vencido"] + v["cartera"]["por_vencer"] + v["cartera"]["al_dia"] - v["cartera"]["en_calle"]) < 0.02 for v in vs.values()))
check("facturas con saldo: las mismas cantidades que Cuentas Corrientes",
      sum(v["cartera"]["facturas"] for v in vs.values()) == len(cuentas_corrientes_io._facturas_con_saldo(ctacorr_cc, desde_siempre)))
favor_escritorio = -float(cuentas_corrientes_io.saldos_a_favor(ctacorr_cc, deudores).sum())
favor = sum(v["cartera"]["a_favor"] for v in vs.values())
check("a favor: la suma de los vendedores = los saldos a favor de Cuentas Corrientes", abs(favor - favor_escritorio) < 0.05, f"{favor:,.2f} vs {favor_escritorio:,.2f}")

# clientes: detalle contra el del escritorio, y cada cliente de un solo vendedor
cuentas_listadas = [c_["cuenta"] for v in vs.values() for c_ in v["clientes"]]
check("ningún cliente aparece en dos vendedores", len(cuentas_listadas) == len(set(cuentas_listadas)))
con_deuda = {c_["cuenta"]: c_ for v in vs.values() for c_ in v["clientes"] if c_["facturas"]}
check("cada cliente con deuda de Cuentas Corrientes está en la lista de un vendedor", set(int(x) for x in deudores["Cuenta"]) == set(con_deuda),
      f"{len(deudores)} vs {len(con_deuda)}")
distintos = []
for _, fila in deudores.iterrows():
    mio_c = con_deuda.get(int(fila["Cuenta"]))
    d_cc = cuentas_corrientes_io.detalle_facturas(ctacorr_cc, fila["Cuenta"], desde_siempre)
    if mio_c is None or len(mio_c["facturas"]) != len(d_cc) or abs(mio_c["saldo"] - float(d_cc["Saldo"].sum())) >= 0.02 \
            or sorted(f["comprobante"] for f in mio_c["facturas"]) != sorted(" ".join(x.split()) for x in d_cc["Comprobante"]):
        distintos.append(int(fila["Cuenta"]))
check("el detalle de cada cliente (comprobantes y saldo) es el mismo que el del escritorio", not distintos, f"{len(distintos)} distintos: {distintos[:5]}")
con_codigo = clientes_cc.dropna(subset=["VENDEDOR"])
esperado = {int(c_): int(v_) for c_, v_ in zip(con_codigo["CNUMERO"], con_codigo["VENDEDOR"])}
asignado = {c_["cuenta"]: int(cod) for cod, v in vs.items() for c_ in v["clientes"]}
check("cada cliente quedó en el vendedor que dice ctaclien.VENDEDOR", all(esperado.get(c_) == cod for c_, cod in asignado.items()))
check("el panel de cada vendedor es JSON y de tamaño razonable (< 400 KB cada uno)",
      all(len(__import__("json").dumps(v)) < 400_000 for v in vs.values()))

# La empresa entera (lo que ve el admin): todos los clientes, contra Cuentas Corrientes y contra el panel general
emp = todos["empresa"]
ce = emp["cartera"]
tam_empresa = len(__import__("json").dumps(emp))
print(f"   empresa: {ce}, {len(emp['clientes'])} clientes, {tam_empresa / 1024:.0f} KB")
check("empresa: en calle = el saldo bruto de Cuentas Corrientes (todos los clientes, tengan o no vendedor)",
      abs(ce["en_calle"] - float(deudores["Saldo"].sum())) < 0.05, f"{ce['en_calle']:,.2f} vs {float(deudores['Saldo'].sum()):,.2f}")
check("empresa: a favor = los saldos a favor de Cuentas Corrientes", abs(ce["a_favor"] - favor_escritorio) < 0.05, f"{ce['a_favor']:,.2f} vs {favor_escritorio:,.2f}")
check("empresa: mismas facturas y mismos clientes con deuda que Cuentas Corrientes",
      ce["facturas"] == len(cuentas_corrientes_io._facturas_con_saldo(ctacorr_cc, desde_siempre)) and ce["clientes_con_deuda"] == len(deudores),
      f"{ce['facturas']} facturas, {ce['clientes_con_deuda']} clientes vs {len(deudores)}")
check("empresa: en calle = vencido + por vencer + al día", abs(ce["vencido"] + ce["por_vencer"] + ce["al_dia"] - ce["en_calle"]) < 0.02)
check("empresa: lo que está en calle = la suma de los vendedores (si no hay clientes sin vendedor)", abs(ce["en_calle"] - en_calle) < 0.05, f"{ce['en_calle']:,.2f} vs {en_calle:,.2f}")
con_deuda_empresa = {c_["cuenta"]: c_ for c_ in emp["clientes"] if c_["facturas"]}
check("empresa: cada cliente con deuda de Cuentas Corrientes está en la lista, ni uno más", set(int(x) for x in deudores["Cuenta"]) == set(con_deuda_empresa), f"{len(deudores)} vs {len(con_deuda_empresa)}")
distintos_empresa = [int(f_["Cuenta"]) for _, f_ in deudores.iterrows()
                     if int(f_["Cuenta"]) not in con_deuda_empresa
                     or abs(con_deuda_empresa[int(f_["Cuenta"])]["saldo"] - float(cuentas_corrientes_io.detalle_facturas(ctacorr_cc, f_["Cuenta"], desde_siempre)["Saldo"].sum())) >= 0.02]
check("empresa: el saldo de cada cliente es el del escritorio", not distintos_empresa, f"{len(distintos_empresa)} distintos")
check("empresa: están todos los clientes de todos los vendedores", {c_["cuenta"] for c_ in emp["clientes"]} >= set(cuentas_listadas))
dif_empresa = []
for clave, m_desde, m_hasta in vendedores.meses(hoy):
    general_mes = recaudado.desglose(recibos_panel, caja_panel, m_desde, m_hasta)
    for medio in ("total", "efectivo", "transferencia", "cheques", "retenciones", "otros", "recibos"):
        if abs(emp["cobrado"][clave][medio] - general_mes[medio]) >= 0.02:
            dif_empresa.append(f"{clave} {medio}")
check("empresa: lo cobrado de los 12 meses = el desglose del panel general (todos los recibos)", not dif_empresa, "; ".join(dif_empresa[:4]))
check("empresa: es JSON y de tamaño razonable para el celular (< 1 MB)", tam_empresa < 1_000_000, f"{tam_empresa / 1024:.0f} KB")

print()
print("TODO OK" if not fallas else f"{len(fallas)} FALLA(S): {fallas}")
sys.exit(1 if fallas else 0)
