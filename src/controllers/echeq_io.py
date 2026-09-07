"""Carga cacheada de E-Cheques.

`config.ECHEQ_PATH` acumula un Excel por cada lote de "novedades de cobros"
que exporta el banco (cientos de archivos, y cada cheque aparece repetido en
muchos de ellos a medida que cambia su estado). Releer todo el directorio con
`pd.read_excel` en cada apertura es lento (~13s con ~400 archivos) y además la
implementación original recalculaba el set de duplicados desde cero por cada
archivo (O(archivos²)).

Acá se cachea el resultado combinado en un Parquet + un manifest JSON con la
firma (tamaño + mtime) de cada archivo ya procesado. En una recarga solo se
leen del disco los archivos nuevos o modificados — el caso común (0-2 archivos
nuevos) pasa de ~13s a menos de 1s.
"""
import json
import os

import pandas as pd

# Columnas del Excel de e-cheques (export del banco). El listado completo se
# preserva para que "Guardar" siga exportando todas las columnas, aunque la
# tabla solo muestre un subconjunto.
COLUMNAS = [
    'Pagador Nombre Apellido/Razón Social', 'Unnamed: 1', 'Pagador Cuit',
    'Beneficiario Cuit', 'Beneficiario Nombre Apellido/Razón Social',
    'Tenedor Cuit', 'Tenedor Nombre Apellido/Razón Social', 'Banco Emisor',
    'CMC7', 'Endoso: fecha y hora', 'Endoso: tipo', 'Endoso: Estado',
    'Endoso: tipo de documento beneficiario',
    'Endoso: número de documento beneficiario',
    'Endoso: Razón social / Nombre y apellido beneficiario',
    'Endoso: tipo de documento emisor del endoso',
    'Endoso: número de documento emisor del endoso',
    'Endoso: Razón social / Nombre y emisor del endoso', 'Agrupador ID',
    'Nro de Cheque', 'Echeq id', 'Código Visualización', 'Fecha de Emisión',
    'Fecha de Pago', 'Tipo', 'Carácter', 'Modo', 'Monto', 'Estado',
    'Concepto', 'Motivo de Pago', 'Motivo de Repudio en Emisión',
    'Código de Referencia 1', 'Referencia 1', 'Código de Referencia 2',
    'Referencia 2', 'Código de Referencia 3', 'Unnamed: 37', 'Referencia 3',
    'Codigo de banco', 'Sucursal', 'Código Postal', 'Nro de cuenta',
    'Emisor Cuit', 'Razón Social Emisor',
]

_EXTENSIONES = (".xls", ".xlsx")


def _tiene_letras(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return False
    return any(c.isalpha() for c in str(valor))


_COL_CUIT = "Pagador Cuit"
_COL_NOMBRE = "Pagador Nombre Apellido/Razón Social"


def _corregir_pagador_swapeado(df):
    """Algunos exports (y el propio `Echeqs_sistema.xlsx`, que puede quedar
    mezclado) traen el nombre en la columna "Pagador Cuit" y el CUIT en
    "Pagador Nombre...". La corrección tiene que ser POR FILA: un swap de
    columna entera rompe las filas que ya estaban bien cuando el archivo es
    mixto."""
    if _COL_CUIT not in df.columns or _COL_NOMBRE not in df.columns:
        return df
    swapear = df[_COL_CUIT].apply(_tiene_letras)
    if not swapear.any():
        return df
    df = df.copy()
    # a `object` para poder mezclar CUIT (numérico) y nombre (texto) sin que
    # pandas se queje por dtype incompatible.
    df[_COL_CUIT] = df[_COL_CUIT].astype(object)
    df[_COL_NOMBRE] = df[_COL_NOMBRE].astype(object)
    cuit = df.loc[swapear, _COL_CUIT].copy()
    nombre = df.loc[swapear, _COL_NOMBRE].copy()
    df.loc[swapear, _COL_CUIT] = nombre
    df.loc[swapear, _COL_NOMBRE] = cuit
    return df


def _leer_archivo(ruta, nombre):
    """Lee un Excel de e-cheques. Los que empiezan con 'E' son el propio
    export del sistema (`Echeqs*.xlsx`, header en la fila 0); el resto son
    exports del banco (header en la fila 1)."""
    df = pd.read_excel(ruta) if nombre.startswith("E") else pd.read_excel(ruta, header=1)
    df.columns = df.columns.astype(str).str.strip()
    df = _corregir_pagador_swapeado(df)

    columnas_validas = [c for c in COLUMNAS if c in df.columns]
    return df[columnas_validas]


def _firma(ruta):
    st = os.stat(ruta)
    return {"size": st.st_size, "mtime": st.st_mtime}


def _cargar_estado_previo(ruta_cache, ruta_meta):
    """(manifest, df_cache). Si falta o no se puede leer cualquiera de los dos,
    se descarta todo el caché (mejor releer de más que perder datos).

    Se usa pickle (no Parquet) porque acá no hay `pyarrow`/`fastparquet`
    instalado — pickle viene con pandas y evita sumar otra dependencia."""
    try:
        with open(ruta_meta, encoding="utf-8") as fh:
            manifest = json.load(fh)
        df_cache = pd.read_pickle(ruta_cache)
        return manifest, df_cache
    except Exception:
        return {}, pd.DataFrame(columns=COLUMNAS)


def _deduplicar(df):
    if "Nro de Cheque" not in df.columns or df.empty:
        return df
    df = df.dropna(subset=["Nro de Cheque"]).copy()
    df["Nro de Cheque"] = df["Nro de Cheque"].astype(str).str.strip()
    df = df[df["Nro de Cheque"] != ""]
    # keep="last": los archivos se procesan en orden cronológico (nombre con
    # fecha), así que el estado más reciente de cada cheque es el que queda.
    return df.drop_duplicates(subset=["Nro de Cheque"], keep="last").reset_index(drop=True)


def cargar_echeqs_cacheado(direc, ruta_cache):
    """Devuelve el DataFrame combinado y deduplicado de todos los e-cheques
    en `direc`, usando (y actualizando) el caché en `ruta_cache`."""
    ruta_meta = ruta_cache + ".meta"
    manifest, df_cache = _cargar_estado_previo(ruta_cache, ruta_meta)

    if not os.path.exists(direc):
        return df_cache

    archivos = sorted(f for f in os.listdir(direc) if f.lower().endswith(_EXTENSIONES))

    frames_nuevos = []
    manifest_actualizado = dict(manifest)
    hubo_cambios = False
    for archivo in archivos:
        ruta = os.path.join(direc, archivo)
        firma = _firma(ruta)
        if manifest.get(archivo) == firma:
            continue  # sin cambios desde la última carga
        try:
            frames_nuevos.append(_leer_archivo(ruta, archivo))
            manifest_actualizado[archivo] = firma
            hubo_cambios = True
        except Exception:
            continue  # archivo corrupto/formato inesperado: se ignora, no rompe la carga

    if not hubo_cambios:
        return df_cache

    partes = ([df_cache] if not df_cache.empty else []) + frames_nuevos
    df = pd.concat(partes, ignore_index=True) if partes else df_cache
    df = _deduplicar(df)

    try:
        os.makedirs(os.path.dirname(ruta_cache), exist_ok=True)
        df.to_pickle(ruta_cache)
        with open(ruta_meta, "w", encoding="utf-8") as fh:
            json.dump(manifest_actualizado, fh)
    except Exception:
        pass  # si no se pudo escribir el caché, la próxima carga relee de más — no es fatal

    return df
