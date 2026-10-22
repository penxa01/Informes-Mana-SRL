"""
Lectura eficiente de archivos DBF.

Reemplaza el patrón lento ``pd.DataFrame(iter(DBF(ruta, encoding='latin1')))``
por DuckDB (extensión ``spatial`` / GDAL), que:

* lee solo las columnas pedidas (proyección),
* castea tipos automáticamente,
* usa ~3x menos RAM y es ~4x más rápido en archivos grandes.

``leer_dbf_cacheado`` agrega una caché Parquet: si el DBF no cambió desde la
última conversión, lee el ``.parquet`` (instantáneo) en lugar de reprocesar el DBF.

Si DuckDB o la extensión ``spatial`` no están disponibles, ambas funciones caen
automáticamente a ``dbfread`` para no romper la app.

**Compatibilidad de tipos:** el DataFrame devuelto se normaliza con
``_emular_dbfread`` para comportarse como el que producía ``dbfread`` + pandas
(texto vacío en vez de ``NaN``; enteros ``float64``/``int64`` en vez de los
nullable de DuckDB). ``FECHA`` y otras columnas de fecha quedan como
``datetime64`` (equivalente y evita conversiones repetidas aguas abajo).

**Encoding:** los DBF declaran codepage 850 en el header (``config.DBF_ENCODING``).
Se decodifica con ese codepage tanto en GDAL como en el fallback ``dbfread``.
"""
import json
import os
import struct

import pandas as pd

from src.controllers import config

# GDAL/iconv espera el nombre en mayúsculas (p. ej. 'CP850').
_OPEN_OPTIONS = f"open_options=['ENCODING={config.DBF_ENCODING.upper()}']"

# Columnas de fachist.DBF que la app realmente usa (de 59 totales). Proyectar a
# estas baja la RAM de ~186 MB a ~58 MB. Si un módulo pasa a necesitar otra
# columna de fachist, agregala acá.
#   FECHA, MODELO, TC                -> filtros de todos los informes
#   U_VENDIDAS, TOTAVEN              -> Litros, Margen, Thalamus
#   CUENTA, NROEST, LETRA, NC        -> Thalamus (Transaction ID / Systemid), Margen (detalle)
#   VENDNUMERO                       -> filtro por vendedor (Litros, Margen)
#   CODMOV                           -> Sell In (CODMOV == 'RI')
#   DESC                            -> nombre de producto en Margen
COLUMNAS_VENTAS = [
    "FECHA", "MODELO", "U_VENDIDAS", "TOTAVEN", "TC", "NC",
    "CUENTA", "NROEST", "LETRA", "VENDNUMERO", "CODMOV", "DESC",
]

# Columnas de ivatemp.DBF que usa el Informe IIBB (de 98 totales).
COLUMNAS_IVATEMP = ["FECHA", "NROEST", "CUENTA", "NC", "NETO", "PERCE_1", "TC"]

_ENTEROS_NULLABLE = {
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
}
# Enteros/floats no-nullable de DuckDB que pandas, al inferir desde dicts, ensancha.
_ENTEROS_ESTRECHOS = {"int8", "int16", "int32", "uint8", "uint16", "uint32"}

# Chequeo de disponibilidad de la extensión spatial (una sola vez por proceso).
_spatial_estado = None  # None = sin chequear, True = ok, False = no disponible


def _cargar_spatial(con):
    """Deja lista la extensión spatial en la conexión. Lanza si no se puede."""
    global _spatial_estado
    if _spatial_estado is False:
        raise RuntimeError("extensión spatial de DuckDB no disponible")
    try:
        con.execute("LOAD spatial;")
        _spatial_estado = True
        return
    except Exception:
        pass
    # Primer uso en la máquina: intentar instalarla (requiere internet una vez).
    con.execute("INSTALL spatial;")
    con.execute("LOAD spatial;")
    _spatial_estado = True


def _conexion():
    import duckdb

    con = duckdb.connect()
    _cargar_spatial(con)
    return con


def _sql_path(ruta):
    """Normaliza una ruta para interpolarla en SQL de forma segura.

    Las rutas provienen de ``config.py`` (no de entrada de usuario); aun así
    rechazamos comillas simples para evitar cualquier inyección.
    """
    ruta = os.path.abspath(ruta).replace("\\", "/")
    if "'" in ruta:
        raise ValueError(f"ruta con comilla simple no soportada: {ruta}")
    return ruta


def _proyeccion(columnas):
    if not columnas:
        return "*"
    return ", ".join('"' + c.replace('"', '') + '"' for c in columnas)


def _emular_dbfread(df):
    """Ajusta los dtypes de DuckDB para que se comporten como dbfread + pandas."""
    for col in df.columns:
        s = df[col]
        dt = str(s.dtype)
        if dt == "object":
            # dbfread devuelve '' para campos de texto vacíos, no NaN/None.
            df[col] = s.where(s.notna(), "")
        elif dt in _ENTEROS_NULLABLE:
            # pandas, al inferir desde dicts, usa int64 (sin nulos) o float64 (con nulos).
            df[col] = s.astype("int64" if not s.isna().any() else "float64")
        elif dt in _ENTEROS_ESTRECHOS:
            df[col] = s.astype("int64")
        elif dt == "float32":
            df[col] = s.astype("float64")
        elif dt == "boolean":
            df[col] = s.astype("object")
    return df


def _leer_dbfread(ruta, columnas=None):
    """Fallback: lectura clásica con dbfread."""
    from dbfread import DBF

    tabla = DBF(ruta, encoding=config.DBF_ENCODING)
    if columnas:
        pedidas = list(columnas)
        registros = [
            {c: reg[c] for c in pedidas if c in reg}
            for reg in tabla
        ]
        df = pd.DataFrame(registros, columns=pedidas)
    else:
        df = pd.DataFrame(iter(tabla))
    return df


def leer_dbf(ruta, columnas=None):
    """Lee un DBF a ``DataFrame``.

    Usa DuckDB (rápido, poca RAM); si no está disponible cae a ``dbfread``.

    :param ruta: ruta al archivo ``.dbf``.
    :param columnas: lista de columnas a traer (proyección). ``None`` = todas.
    """
    try:
        con = _conexion()
        sql = f"SELECT {_proyeccion(columnas)} FROM st_read(?, {_OPEN_OPTIONS})"
        df = con.execute(sql, [ruta]).df()
        return _emular_dbfread(df)
    except Exception:
        return _leer_dbfread(ruta, columnas)


def _firma_dbf(ruta):
    """Firma barata del DBF para detectar cambios: tamaño + mtime + nº de registros.

    El nº de registros vive en los bytes 4..7 del header (little-endian). Leer 32
    bytes + ``os.stat`` es instantáneo. No se usa solo ``mtime`` porque al
    actualizar el DBF (copia, restore, reescritura del sistema de gestión) el
    ``mtime`` puede quedar **igual o anterior** al de la caché y servir datos
    viejos.
    """
    with open(ruta, "rb") as fh:
        hdr = fh.read(32)
    n_reg = struct.unpack("<I", hdr[4:8])[0] if len(hdr) >= 8 else -1
    st = os.stat(ruta)
    return {"size": st.st_size, "mtime": int(st.st_mtime), "n_reg": n_reg}


def leer_dbf_cacheado(ruta_dbf, ruta_cache, columnas=None):
    """Como :func:`leer_dbf` pero cachea el DBF completo en Parquet.

    Reconvierte si el DBF cambió (tamaño, mtime o nº de registros — ver
    :func:`_firma_dbf`) o si falta la caché. Junto al ``.parquet`` se guarda un
    ``.parquet.meta`` (JSON) con la firma del DBF de origen.
    El Parquet guarda **todas** las columnas; la proyección se aplica al leer.

    :param ruta_dbf: ruta al ``.dbf`` de origen.
    :param ruta_cache: ruta del ``.parquet`` de caché.
    :param columnas: columnas a traer al leer. ``None`` = todas.
    """
    try:
        ruta_meta = ruta_cache + ".meta"
        firma = _firma_dbf(ruta_dbf)

        firma_previa = None
        if os.path.exists(ruta_cache) and os.path.exists(ruta_meta):
            try:
                with open(ruta_meta, encoding="utf-8") as fh:
                    firma_previa = json.load(fh)
            except Exception:
                firma_previa = None

        con = _conexion()

        if firma_previa != firma:
            os.makedirs(os.path.dirname(ruta_cache) or ".", exist_ok=True)
            tmp = ruta_cache + ".tmp"
            con.execute(
                f"COPY (SELECT * FROM st_read('{_sql_path(ruta_dbf)}', {_OPEN_OPTIONS})) "
                f"TO '{_sql_path(tmp)}' (FORMAT parquet)"
            )
            os.replace(tmp, ruta_cache)
            with open(ruta_meta, "w", encoding="utf-8") as fh:
                json.dump(firma, fh)

        sql = f"SELECT {_proyeccion(columnas)} FROM read_parquet(?)"
        df = con.execute(sql, [ruta_cache]).df()
        return _emular_dbfread(df)
    except Exception:
        return _leer_dbfread(ruta_dbf, columnas)
