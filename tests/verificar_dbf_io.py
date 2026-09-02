"""Verificación funcional de src/controllers/dbf_io.py contra dbfread + los filtros reales.

Requiere acceso a los DBF reales (config.DBF_BASE_PATH). Correr desde la raíz del proyecto:
    python tests/verificar_dbf_io.py
"""
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from dbfread import DBF
from src.controllers import dbf_io, config

FACHIST = os.path.join(config.DBF_BASE_PATH, "fachist.DBF")
IVATEMP = os.path.join(config.DBF_BASE_PATH, "ivatemp.DBF")
COLS = ["FECHA","MODELO","U_VENDIDAS","TOTAVEN","TC","NC","CUENTA","NROEST","LETRA","VENDNUMERO","CODMOV","DESC"]

fails = []
def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond: fails.append(name)

print("=== 1. cargar fachist (old dbfread) ===")
t=time.perf_counter()
old = pd.DataFrame(iter(DBF(FACHIST, encoding="cp850")))
print(f"   dbfread completo: {time.perf_counter()-t:.1f}s  {old.shape}")
old = old[COLS].copy()
old["FECHA"] = pd.to_datetime(old["FECHA"])   # los módulos hacen esto siempre

print("=== 2. leer_dbf (DuckDB, 12 cols) ===")
cache = os.path.join(config.CACHE_PATH, "fachist.parquet")
if os.path.exists(cache): os.remove(cache)
t=time.perf_counter()
new = dbf_io.leer_dbf(FACHIST, COLS)
print(f"   leer_dbf: {time.perf_counter()-t:.1f}s  {new.shape}")

print("=== 3. leer_dbf_cacheado (crea parquet) ===")
t=time.perf_counter()
c1 = dbf_io.leer_dbf_cacheado(FACHIST, cache, COLS)
dt1 = time.perf_counter()-t
t=time.perf_counter()
c2 = dbf_io.leer_dbf_cacheado(FACHIST, cache, COLS)   # 2da vez: desde parquet
dt2 = time.perf_counter()-t
print(f"   1ra (convierte): {dt1:.1f}s   2da (desde parquet): {dt2:.2f}s")
check("cache existe", os.path.exists(cache))
check("meta existe", os.path.exists(cache + ".meta"))
check("2da lectura mucho mas rapida", dt2 < dt1/3, f"{dt2:.2f}s < {dt1/3:.2f}s")
check("cache no se regenera si el DBF no cambio", dt2 < 3.0, f"{dt2:.2f}s (reconvertir tardaría >10s)")

# --- invalidación por firma: DBF con mtime ANTERIOR a la caché pero contenido distinto ---
print("--- invalidacion: DBF 'cambiado' con mtime viejo ---")
import json as _json
meta = _json.loads(open(cache + ".meta", encoding="utf-8").read())
meta["n_reg"] = meta["n_reg"] - 1          # simula: el DBF real tiene otro nº de registros
open(cache + ".meta", "w", encoding="utf-8").write(_json.dumps(meta))
os.utime(cache, None)                       # caché "recién tocada" (mtime nuevo)
t = time.perf_counter()
c3 = dbf_io.leer_dbf_cacheado(FACHIST, cache, COLS)
dt3 = time.perf_counter() - t
check("reconvierte aunque el mtime del DBF sea viejo", dt3 > 1.5, f"{dt3:.2f}s")
check("tras reconvertir, filas correctas", len(c3) == len(old), f"{len(c3)} vs {len(old)}")
nuevo_meta = _json.loads(open(cache + ".meta", encoding="utf-8").read())
check("meta actualizado tras reconvertir", nuevo_meta["n_reg"] != meta["n_reg"])

print("=== 4. dtypes / filas ===")
check("mismas filas leer_dbf", len(old)==len(new), f"{len(old)} vs {len(new)}")
check("mismas filas cacheado", len(old)==len(c2), f"{len(old)} vs {len(c2)}")
for df,label in [(new,"leer_dbf"),(c2,"cacheado")]:
    for c in COLS:
        od, nd = str(old[c].dtype), str(df[c].dtype)
        compat = (od==nd) or (c=="FECHA" and "datetime64" in nd) \
                 or (od in ("int64","float64") and nd in ("int64","float64"))
        check(f"[{label}] dtype {c}: {nd}", compat, f"(old {od})")

print("=== 5. valores identicos (muestra 5000 filas) ===")
for df,label in [(new,"leer_dbf"),(c2,"cacheado")]:
    o = old.reset_index(drop=True); n = df.reset_index(drop=True)
    idx = list(range(0, len(o), max(1,len(o)//5000)))
    for c in COLS:
        oc, nc = o[c].iloc[idx], n[c].iloc[idx]
        if c == "FECHA":
            eq = (pd.to_datetime(oc).values == pd.to_datetime(nc).values).all()
        elif str(old[c].dtype) in ("int64","float64"):
            eq = ((oc.fillna(-9e9) - nc.fillna(-9e9)).abs() < 1e-6).all()
        else:
            # GDAL recorta espacios a ambos lados de los CHAR; dbfread solo a la
            # derecha. Todos los consumidores de estas columnas hacen .strip(),
            # así que comparamos ya normalizado (equivalencia funcional).
            eq = (oc.astype(str).str.strip().values == nc.astype(str).str.strip().values).all()
        check(f"[{label}] valores {c} (tras strip)", eq)

print("=== 6. FILTROS REALES de cada modulo (mismo resultado) ===")
def f_thalamus(df):
    return df[
        (pd.to_datetime(df["FECHA"]).dt.date == pd.Timestamp("2025-06-10").date()) &
        (df["MODELO"].str.match(r'^L\d')) &
        (df["CUENTA"].notna()) &
        ((df["TC"]=="FC")|(df["TC"]=="NC")|(df["TC"]=="FE")|(df["TC"]=="CR"))
    ]
def f_sellin(df):
    d = df.copy(); d["FECHA"] = pd.to_datetime(d["FECHA"])
    return d[
        (d["FECHA"]>=pd.Timestamp("2025-01-01")) & (d["FECHA"]<=pd.Timestamp("2025-06-30 23:59:59")) &
        (d["MODELO"].astype(str).str.startswith("L")) & (d["CODMOV"]=="RI")
    ]
def f_litros_vend(df):
    d = df.copy(); d["FECHA"] = pd.to_datetime(d["FECHA"])
    return d[
        (d["FECHA"]>=pd.Timestamp("2025-01-01")) & (d["FECHA"]<=pd.Timestamp("2025-06-30 23:59:59")) &
        (d["VENDNUMERO"]==4) &
        ((d["TC"]=="FC")|(d["TC"]=="NC")|(d["TC"]=="ND")|(d["TC"]=="FE")|(d["TC"]=="CR"))
    ]
def f_margen(df):
    d = df.copy(); fechas = pd.to_datetime(d["FECHA"])
    return d[
        (fechas>=pd.Timestamp("2025-01-01")) & (fechas<=pd.Timestamp("2025-06-30")) &
        (d["MODELO"].astype(str).str.startswith("L")) &
        ((d["TC"]=="FC")|(d["TC"]=="NC")|(d["TC"]=="ND")|(d["TC"]=="FE"))
    ]
for nombre, fn in [("thalamus",f_thalamus),("sellIn",f_sellin),("litros+vend",f_litros_vend),("margen",f_margen)]:
    try:
        no = len(fn(old)); nn = len(fn(new)); ncc = len(fn(c2))
        check(f"filtro {nombre}: old={no} new={nn} cache={ncc}", no==nn==ncc)
    except Exception as e:
        check(f"filtro {nombre} corre sin error", False, repr(e))

print("=== 7. sub-DataFrame de Thalamus: .astype(int) sobre CUENTA/U_VENDIDAS ===")
try:
    sub = f_thalamus(new)
    _ = sub["CUENTA"].astype(int); _ = sub["U_VENDIDAS"].astype(int)
    _ = sub.apply(lambda r: "{} {} {} {}".format(r["TC"], r["LETRA"], r["NROEST"], str(r["NC"]).zfill(8)), axis=1)
    check("astype(int) + Transaction ID sobre resultado DuckDB", True)
except Exception as e:
    check("astype(int) + Transaction ID sobre resultado DuckDB", False, repr(e))

print("=== 8. ivatemp (IIBB) via leer_dbf ===")
try:
    iv_old = pd.DataFrame(iter(DBF(IVATEMP, encoding="cp850")))
    t=time.perf_counter()
    iv_new = dbf_io.leer_dbf(IVATEMP, ["FECHA","NROEST","CUENTA","NC","NETO","PERCE_1","TC"])
    print(f"   ivatemp leer_dbf: {time.perf_counter()-t:.1f}s  {iv_new.shape}  (old {iv_old.shape})")
    check("ivatemp mismas filas", len(iv_old)==len(iv_new))
    ivf = iv_new.copy(); ivf["FECHA"] = pd.to_datetime(ivf["FECHA"], errors="coerce")
    m = ((ivf["FECHA"].dt.month==6) & (ivf["FECHA"].dt.year==2025) &
         ((ivf["NROEST"]=="00002")|(ivf["NROEST"]=="00003")))
    iv_old["FECHA"] = pd.to_datetime(iv_old["FECHA"], errors="coerce")
    mo = ((iv_old["FECHA"].dt.month==6) & (iv_old["FECHA"].dt.year==2025) &
          ((iv_old["NROEST"]=="00002")|(iv_old["NROEST"]=="00003")))
    check(f"filtro IIBB: old={mo.sum()} new={m.sum()}", mo.sum()==m.sum())
    # str(NC).split()[0].zfill(12) sobre el resultado
    _ = ivf[m]["NC"].apply(lambda x: str(x).split()[0].zfill(12))
    check("NC .split()[0].zfill(12) sobre DuckDB", True)
except Exception as e:
    check("ivatemp / IIBB", False, repr(e))

print("=== 9. fallback dbfread (simula spatial no disponible) ===")
dbf_io._spatial_estado = False
try:
    fb = dbf_io.leer_dbf(FACHIST, COLS)
    check("fallback devuelve las filas", len(fb)==len(old), f"{len(fb)}")
    check("fallback tiene las 12 columnas", list(fb.columns)==COLS)
finally:
    dbf_io._spatial_estado = None

print("=== 10. encoding: caracteres especiales bien decodificados (cp850) ===")
# DESC de abmartic/fachist tiene 'Ñ' (byte 0xA5), 'º' (0xA7) y '°' (0xF8) en cp850.
# Con el bug latin1 salían como '¥', '§', 'ø'.
muestra_desc = new["DESC"].astype(str)
tiene_enie = muestra_desc.str.contains("Ñ", regex=False).any()
tiene_bug = muestra_desc.str.contains("¥", regex=False).any()
check("hay descripciones con 'Ñ' (decodificado OK)", tiene_enie)
check("NO hay '¥' (bug latin1 corregido)", not tiene_bug,
      f"filas con ¥: {muestra_desc.str.contains('¥', regex=False).sum()}")
# el clásico "PICO ... PIÑAS"
pinas = muestra_desc[muestra_desc.str.contains("PICO PARA ENGRASE CHICO", regex=False)]
if len(pinas):
    val = pinas.iloc[0]
    check(f"'PICO...' -> {val!r}", "Ñ" in val)
# ivatemp/ctaclien no tienen texto libre relevante; abmartic sí -> se prueba abajo
import importlib
from src.controllers import others
ab = others.buscaArtic(pd.DataFrame({"MODELO": new["MODELO"].dropna().unique()[:500]}))
if "DESC" in ab.columns:
    ab_bug = ab["DESC"].astype(str).str.contains("¥", regex=False).sum()
    check("buscaArtic (abmartic) sin '¥'", ab_bug == 0, f"{ab_bug} filas")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
