"""Detección del entorno de datos: PC local (``D:/tiempo``) o remota (``Z:``).

El sistema corre en dos tipos de PC: la que tiene los datos en ``D:/tiempo`` y la
que los consume por red a través de la unidad ``Z:`` (``\\\\DESKTOP-R8E4V7S\\tiempo``).
Se prefiere el entorno local y, si no está, se usa el remoto.

Sin dependencias de config/Qt para poder probarlo con un disco simulado.
"""
import os
import re
import socket

#: Carpeta (relativa a la base) donde viven los DBF del sistema de gestión. Es lo que
#: se comprueba: que exista ``D:/tiempo`` no garantiza que estén los datos.
SUBRUTA_DBF = "vtiempoges/GESTION/MANA2014"


def normalizar_base(base):
    """Limpia una ruta base. Una unidad sola (``Z:``) pasa a ``Z:/``: en Windows
    ``Z:vtiempoges`` es relativa al *directorio actual* de la unidad Z, no a su
    raíz, y no la abren bien todas las librerías (DuckDB/GDAL)."""
    base = str(base or "").strip()
    if re.fullmatch(r"[A-Za-z]:", base):
        return base + "/"
    return base


def _nombre_corto(nombre):
    """'DESKTOP-R8E4V7S.local ' -> 'desktop-r8e4v7s'."""
    return str(nombre or "").strip().split(".")[0].lower()


def resolver_host_db(host_servidor, nombre_equipo=None, host_local="localhost"):
    """Host del Postgres de Pedidos/reclamos para ESTA PC.

    Solo la PC que **aloja** la base (el servidor) usa su Postgres local. Las demás
    —la remota, y también la de desarrollo, que tiene un Postgres propio de prueba
    con otros datos— van a la base del servidor. Se decide por nombre de equipo y no
    por "¿hay un Postgres local?", porque en la PC de desarrollo lo hay y no es el real.

    :param nombre_equipo: nombre de esta PC; ``None`` = el real (``socket.gethostname``).
    """
    if not _nombre_corto(host_servidor):
        return host_local
    if nombre_equipo is None:
        nombre_equipo = socket.gethostname()
    if _nombre_corto(nombre_equipo) == _nombre_corto(host_servidor):
        return host_local
    return str(host_servidor).strip()


def resolver_entorno(candidatos, existe=os.path.isdir):
    """Primer candidato cuya carpeta de DBF existe.

    :param candidatos: ``[(nombre, base), ...]`` en orden de prioridad.
    :param existe: función ``ruta -> bool`` (inyectable para los tests).
    :returns: ``(nombre, base_normalizada)`` o ``(None, None)`` si no hay ninguno.

    Corta en el primero que sirve: con el entorno local disponible no se consulta
    la red (un ``Z:`` caído puede demorar el arranque varios segundos).
    """
    for nombre, base in candidatos:
        base = normalizar_base(base)
        if base and existe(os.path.join(base, SUBRUTA_DBF)):
            return nombre, base
    return None, None
