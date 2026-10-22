"""Base de ventas (``fachist.DBF``): carga y actualización sin reiniciar la app.

``actualizar_si_cambio`` compara una *firma* barata del DBF (tamaño, fecha de
modificación y nº de registros: ver ``dbf_io._firma_dbf``) con la de la última carga:
si no cambió, no lee nada. Así el refresco automático cada 15 minutos no cuesta casi
nada y, sobre todo, no rehace los informes de la pantalla cuando no hay datos nuevos.

Sin Qt: todo se puede probar. El hilo que lo ejecuta está en ``ProgressBar.LoadDataThread``.
"""
import os

from src.controllers import config, dbf_io

INTERVALO_DEFECTO_MIN = 15
_INTERVALO_MAX_MIN = 240


def ruta_ventas():
    return os.path.join(config.DBF_BASE_PATH, "fachist.DBF")


def firma_ventas(ruta=None):
    """Firma del DBF de ventas. ``OSError`` si no se puede acceder (red caída)."""
    return dbf_io._firma_dbf(ruta or ruta_ventas())


def cargar_ventas():
    """Lee ``fachist`` con la caché Parquet y solo las columnas que usa la app."""
    cache = os.path.join(config.CACHE_PATH, "fachist.parquet")
    return dbf_io.leer_dbf_cacheado(ruta_ventas(), cache, dbf_io.COLUMNAS_VENTAS)


def actualizar_si_cambio(firma_previa, firma_fn=firma_ventas, leer_fn=cargar_ventas):
    """``(df, firma)`` si hay datos nuevos; ``(None, firma)`` si el DBF no cambió.

    ``firma_previa=None`` fuerza la lectura (primera carga). Si no se puede acceder
    al DBF el ``OSError`` sube: quien llama conserva los datos que ya tenía.
    """
    firma = firma_fn()
    if firma_previa is not None and firma == firma_previa:
        return None, firma
    return leer_fn(), firma


def texto_estado_ventas(df, ahora):
    """Texto para la barra de estado: ``ventas: 154.000 filas · 2014→2026 · act. 14:07``."""
    partes = [f"ventas: {len(df):,} filas".replace(",", ".")]
    try:
        fmin, fmax = df["FECHA"].min(), df["FECHA"].max()
        if fmin == fmin and fmax == fmax:      # descarta NaT (df vacío)
            partes.append(f"{fmin:%Y}→{fmax:%Y}")
    except (KeyError, ValueError, TypeError):
        pass
    partes.append(f"act. {ahora:%H:%M}")
    return " · ".join(partes)


def minutos_refresco(valor=None):
    """Intervalo del refresco automático, en minutos. ``valor`` viene de la variable
    de entorno ``VENTAS_ACTUALIZAR_MIN``; si falta o es absurdo, 15."""
    try:
        minutos = int(str(valor).strip())
    except (TypeError, ValueError):
        return INTERVALO_DEFECTO_MIN
    return minutos if 1 <= minutos <= _INTERVALO_MAX_MIN else INTERVALO_DEFECTO_MIN
