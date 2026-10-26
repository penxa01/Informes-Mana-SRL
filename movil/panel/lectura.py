"""Lectura de los archivos del sistema de gestión (DBF y el Excel de clasificación Premium).

Se usa `dbfread` (Python puro, sin extensiones nativas) y solo se guardan las columnas pedidas.
`fachist.DBF` pesa ~80 MB: leerlo lleva unos 15-20 s, por eso el proceso que arma el panel
(`worker.py`) solo lo relee cuando el archivo cambió.
"""
import os

import pandas as pd

ENCODING = "cp850"   # los DBF del sistema son cp850 (ver guideline/rendimiento-dbf.md)

COLUMNAS_VENTAS = ["FECHA", "TC", "MODELO", "U_VENDIDAS"]
COLUMNAS_ABMARTIC = ["CODART", "CODMEDIDA"]
COLUMNAS_CTACORR = ["TC", "FECHA", "TOTALL", "NROEST", "NC"]


def leer_dbf(ruta, columnas):
    from dbfread import DBF

    tabla = DBF(ruta, encoding=ENCODING, load=False, ignore_missing_memofile=True)
    return pd.DataFrame(([reg[c] for c in columnas] for reg in tabla), columns=columnas)


def leer_clasificacion(ruta_excel):
    """LITROS SHELL.xlsx, hoja GENERAL: articulo, Clasificacion ('Premium' o no) y Artiprov."""
    df = pd.read_excel(ruta_excel, sheet_name="GENERAL")
    return df[["articulo", "Clasificacion", "Artiprov"]]


def archivos(base_dbf, ruta_excel):
    """Rutas de todo lo que usa el panel."""
    return {
        "fachist": os.path.join(base_dbf, "fachist.DBF"),
        "abmartic": os.path.join(base_dbf, "abmartic.DBF"),
        "ctacorr": os.path.join(base_dbf, "ctacorr.DBF"),
        "clasificacion": ruta_excel,
    }


def firma_de_archivos(base_dbf, ruta_excel):
    """{nombre: [tamaño, fecha de modificación]}: si no cambió, no hace falta recalcular."""
    firma = {}
    for nombre, ruta in archivos(base_dbf, ruta_excel).items():
        st = os.stat(ruta)
        firma[nombre] = [st.st_size, int(st.st_mtime)]
    return firma
