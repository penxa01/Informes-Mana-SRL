"""Verificación funcional de src/controllers/echeq_io.py (carga cacheada de e-cheques).

Requiere acceso a los Excel reales (config.ECHEQ_PATH). Correr desde la raíz:
    python tests/verificar_echeq_io.py
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.controllers import config, echeq_io

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def solo_digitos(serie):
    """Cantidad de valores no nulos que son puramente numéricos (un CUIT mal
    puesto en la columna de nombre)."""
    s = serie.dropna().astype(str).str.strip()
    s = s[s != ""]
    return int(s.str.match(r"^\d+(\.\d+)?$").sum()), len(s)


DIREC = config.ECHEQ_PATH
CACHE = os.path.join(config.CACHE_PATH, "echeqs_test.pkl")
META = CACHE + ".meta"

for f in (CACHE, META):
    if os.path.exists(f):
        os.remove(f)

print("=== 1. carga en frío (reconstruye caché desde", DIREC, ") ===")
t = time.perf_counter()
df1 = echeq_io.cargar_echeqs_cacheado(DIREC, CACHE)
dt1 = time.perf_counter() - t
print(f"   frío: {dt1:.2f}s   {df1.shape}")
check("caché .pkl creada", os.path.exists(CACHE))
check("caché .meta creada", os.path.exists(META))
check("hay filas", len(df1) > 1000, f"{len(df1)} filas")
check("Nro de Cheque único (deduplicado)", df1["Nro de Cheque"].is_unique)

print("=== 2. carga en caliente (sin archivos nuevos) ===")
t = time.perf_counter()
df2 = echeq_io.cargar_echeqs_cacheado(DIREC, CACHE)
dt2 = time.perf_counter() - t
print(f"   caliente: {dt2:.2f}s   {df2.shape}")
check("caliente mucho más rápida", dt2 < dt1 / 5, f"{dt2:.2f}s vs frío {dt1:.2f}s")
check("mismas filas frío/caliente", len(df1) == len(df2), f"{len(df1)} vs {len(df2)}")

print("=== 3. swap Pagador Cuit / Nombre corregido por fila ===")
n_num_nombre, n_nombre = solo_digitos(df1["Pagador Nombre Apellido/Razón Social"])
n_num_cuit, n_cuit = solo_digitos(df1["Pagador Cuit"])
print(f"   'Pagador Nombre...' puramente numérico: {n_num_nombre}/{n_nombre}")
print(f"   'Pagador Cuit' puramente numérico:      {n_num_cuit}/{n_cuit}")
check("columna Nombre casi sin CUITs sueltos", n_num_nombre < n_nombre * 0.02,
      f"{n_num_nombre}/{n_nombre}")
check("columna Cuit mayormente numérica", n_num_cuit > n_cuit * 0.9,
      f"{n_num_cuit}/{n_cuit}")

print("=== 4. unitario: archivo MIXTO no rompe filas correctas ===")
mixto = pd.DataFrame({
    "Pagador Cuit": ["30715403079", "TRANSPORTE AMANCAY SRL", "20304050607", None],
    "Pagador Nombre Apellido/Razón Social": ["ACME SA", "30999888777", "OTRA SRL", "SIN CUIT SA"],
    "Nro de Cheque": ["1", "2", "3", "4"],
})
corr = echeq_io._corregir_pagador_swapeado(mixto)
check("fila ya correcta se mantiene (cuit numérico)",
      corr.loc[0, "Pagador Cuit"] == "30715403079" and corr.loc[0, "Pagador Nombre Apellido/Razón Social"] == "ACME SA")
check("fila swapeada se corrige",
      corr.loc[1, "Pagador Cuit"] == "30999888777" and corr.loc[1, "Pagador Nombre Apellido/Razón Social"] == "TRANSPORTE AMANCAY SRL")
check("fila con NaN en Cuit no se toca",
      pd.isna(corr.loc[3, "Pagador Cuit"]) and corr.loc[3, "Pagador Nombre Apellido/Razón Social"] == "SIN CUIT SA")

print("=== 5. archivo nuevo se incorpora sin releer los viejos ===")
nro_falso = "ZZZ-TEST-9999"
nuevo = df1.head(1).copy()
nuevo["Nro de Cheque"] = nro_falso
ruta_nuevo = os.path.join(config.CACHE_PATH, "E_test_nuevo_echeq.xlsx")
nuevo.to_excel(ruta_nuevo, index=False)
try:
    # el loader lista archivos del propio DIREC; copiamos ahí el de prueba
    destino = os.path.join(DIREC, "E_test_nuevo_echeq.xlsx")
    shutil.copy(ruta_nuevo, destino)
    try:
        t = time.perf_counter()
        df3 = echeq_io.cargar_echeqs_cacheado(DIREC, CACHE)
        dt3 = time.perf_counter() - t
        print(f"   con 1 archivo nuevo: {dt3:.2f}s   {df3.shape}")
        check("archivo nuevo incorporado", nro_falso in set(df3["Nro de Cheque"]))
        check("solo +1 fila respecto al frío", len(df3) == len(df1) + 1, f"{len(df3)} vs {len(df1)}+1")
        check("reincorporar es rápido (no relee 399)", dt3 < dt1 / 3, f"{dt3:.2f}s")
    finally:
        os.remove(destino)
finally:
    os.remove(ruta_nuevo)

print("=== 6. .pkl borrado pero .meta presente -> reconstrucción total (no pérdida) ===")
os.remove(CACHE)  # queda META
df4 = echeq_io.cargar_echeqs_cacheado(DIREC, CACHE)
check("reconstruye todas las filas aunque el .meta siguiera ahí",
      len(df4) == len(df1), f"{len(df4)} vs {len(df1)}")

for f in (CACHE, META):
    if os.path.exists(f):
        os.remove(f)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
