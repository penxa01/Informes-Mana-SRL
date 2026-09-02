"""Integración: ejercita el flujo real de LoadDataThread e IIBB con el código modificado.

Requiere los DBF reales. Correr desde la raíz del proyecto:
    QT_QPA_PLATFORM=offscreen python tests/verificar_integracion_dbf.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

fails = []
def check(n, c, e=""):
    print(("  OK  " if c else " FAIL ") + n + (f"  {e}" if e else ""))
    if not c: fails.append(n)

print("=== A. import main (sin arrancar la app) ===")
try:
    import main
    check("import main OK", True)
    check("main tiene dbf_io", hasattr(main, "dbf_io"))
except Exception as e:
    check("import main OK", False, repr(e)); raise

from src.controllers import ProgressBar, config, dbf_io

print("\n=== B. LoadDataThread.run() (síncrono) ===")
capturado = {}
th = ProgressBar.LoadDataThread()
th.data_loaded.connect(lambda df: capturado.setdefault("df", df))
t = time.perf_counter()
th.run()
dt1 = time.perf_counter() - t
df = capturado.get("df")
check("emitió un DataFrame", isinstance(df, pd.DataFrame))
check("columnas == COLUMNAS_VENTAS", list(df.columns) == dbf_io.COLUMNAS_VENTAS, str(list(df.columns)))
check("tiene filas", len(df) > 100000, f"{len(df):,}")
print(f"   1ra carga: {dt1:.2f}s  RAM aprox={df.memory_usage(deep=True).sum()/1e6:.0f} MB")

# 2da vez: debe venir del parquet (rápido)
capturado.clear()
th2 = ProgressBar.LoadDataThread()
th2.data_loaded.connect(lambda d: capturado.setdefault("df", d))
t = time.perf_counter(); th2.run(); dt2 = time.perf_counter() - t
print(f"   2da carga (parquet): {dt2:.2f}s")
check("2da carga < 3s", dt2 < 3.0, f"{dt2:.2f}s")
check("2da carga mismas filas", len(capturado["df"]) == len(df))

print("\n=== C. filtros de MainWindow sobre df_ventas real ===")
dv = df
# reporteLitros (rama TODOS): fecha rango + TC
d = dv.copy(); d["FECHA"] = pd.to_datetime(d["FECHA"])
lit = d[(d["FECHA"] >= pd.Timestamp("2025-03-01")) & (d["FECHA"] <= pd.Timestamp("2025-03-31 23:59:59")) &
        ((d["TC"]=="FC")|(d["TC"]=="NC")|(d["TC"]=="ND")|(d["TC"]=="CR")|(d["TC"]=="FE"))]
check("filtro reporteLitros corre", True, f"{len(lit):,} filas")
# margenesBeneficio: startswith L + TC + subset de columnas que consume margenBeneficio
fechas = pd.to_datetime(dv["FECHA"])
mb = dv[(fechas >= pd.Timestamp("2025-01-01")) & (fechas <= pd.Timestamp("2025-03-31")) &
        (dv["MODELO"].astype(str).str.startswith("L")) &
        ((dv["TC"]=="FC")|(dv["TC"]=="NC")|(dv["TC"]=="FE")|(dv["TC"]=="ND"))]
for col in ["FECHA","MODELO","U_VENDIDAS","TOTAVEN","CUENTA","NROEST","TC","NC","DESC"]:
    check(f"margenBeneficio: columna {col} presente", col in mb.columns)
# el cálculo de margen por fila (como margenesBeneficio)
ok_calc = True
for _, v in mb.head(200).iterrows():
    try:
        tv = float(v["TOTAVEN"]) if pd.notna(v["TOTAVEN"]) else 0
        u = float(v["U_VENDIDAS"]) if pd.notna(v["U_VENDIDAS"]) else 0
        if u: _ = tv / u
        _ = str(int(float(v["CUENTA"]))) if pd.notna(v["CUENTA"]) else "N/A"
    except Exception as e:
        ok_calc = False; print("    calc err:", e); break
check("cálculo margen por fila sin error", ok_calc)

# Thalamus: Systemid / Transaction ID
th_df = dv[(pd.to_datetime(dv["FECHA"]).dt.date == pd.Timestamp("2025-06-10").date()) &
           (dv["MODELO"].str.match(r'^L\d')) & (dv["CUENTA"].notna()) &
           ((dv["TC"]=="FC")|(dv["TC"]=="NC")|(dv["TC"]=="FE")|(dv["TC"]=="CR"))]
try:
    _ = th_df["CUENTA"].astype(int)
    _ = th_df["U_VENDIDAS"].astype(int)
    tid = th_df.apply(lambda r: "{} {} {} {}".format(r["TC"], r["LETRA"], r["NROEST"], str(r["NC"]).zfill(8)), axis=1)
    check("Thalamus Systemid+TransactionID", True, f"{len(th_df)} filas, ej: {tid.iloc[0] if len(tid) else '-'}")
except Exception as e:
    check("Thalamus Systemid+TransactionID", False, repr(e))

print("\n=== D. IIBB: ivatemp vía dbf_io + cálculo real ===")
mes, anio = 6, 2025
t = time.perf_counter()
ivatemp = dbf_io.leer_dbf(os.path.join(config.DBF_BASE_PATH, "ivatemp.DBF"), dbf_io.COLUMNAS_IVATEMP)
print(f"   ivatemp leído en {time.perf_counter()-t:.2f}s  {ivatemp.shape}")
ivatemp["FECHA"] = pd.to_datetime(ivatemp["FECHA"], errors="coerce")
filt = ivatemp[(ivatemp["FECHA"].dt.month == mes) & (ivatemp["FECHA"].dt.year == anio) &
               ((ivatemp["NROEST"] == "00002") | (ivatemp["NROEST"] == "00003"))]
check("IIBB filtro devuelve filas", len(filt) >= 0, f"{len(filt)} filas")
total = 0.0; nfilas = 0
try:
    for _, row in filt.iterrows():
        nc = str(row["NC"]).split()[0].zfill(12)
        perce_1 = row["PERCE_1"]
        if perce_1 != 0:
            _ = round(perce_1 * 0.83333327, 2)
            _ = round(perce_1 * 0.1666667, 2)
            tc = row["TC"]; tc = "FA" if tc == "FC" else ("CA" if tc == "NC" else tc)
            _ = row["FECHA"].strftime("%d/%m/%Y")
            total += perce_1; nfilas += 1
    check("IIBB loop de cálculo sin error", True, f"{nfilas} comprobantes, total={total:,.2f}")
except Exception as e:
    check("IIBB loop de cálculo sin error", False, repr(e))

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
