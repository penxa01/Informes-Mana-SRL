import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from src.controllers.entorno import SUBRUTA_DBF, normalizar_base, resolver_entorno, resolver_host_db

# ── Localizar .env ────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _env_base = Path(sys.executable).parent   # junto al .exe compilado
else:
    _env_base = Path(__file__).resolve().parents[2]  # raíz del proyecto

load_dotenv(_env_base / ".env")

# ── Auto-detección de entorno ─────────────────────────────────────────────────
# Prioridad: local (d:/tiempo) → remoto (Z:). Un entorno vale solo si tiene la
# carpeta de DBF (ver `entorno.py`). ENTORNO = "LOCAL" | "REMOTO" | None.
_LOCAL_BASE = os.getenv("BASE_PATH_LOCAL", "d:/tiempo")
_REMOTE_BASE = os.getenv("BASE_PATH_REMOTE", "Z:")

ENTORNO, _BASE = resolver_entorno([("LOCAL", _LOCAL_BASE), ("REMOTO", _REMOTE_BASE)])

if ENTORNO is None:
    # No se encontró ninguno. Se deja la ruta local solo para que el import no
    # falle; `main.py` avisa con ENTORNO_ERROR y no abre la app.
    _BASE = normalizar_base(_LOCAL_BASE)

# Base de datos (Pedidos / reclamos): es UNA sola, la del servidor. Solo el propio
# servidor la usa como localhost; el resto de las PCs —incluida la de desarrollo,
# aunque tenga D:/tiempo y un Postgres local de prueba— se conectan al servidor.
# Va por nombre de equipo, no por "¿hay Postgres local?" (ver `resolver_host_db`).
DB_SERVIDOR = os.getenv("DB_HOST_REMOTE", "DESKTOP-R8E4V7S")
DB_HOST = resolver_host_db(DB_SERVIDOR, host_local=os.getenv("DB_HOST_LOCAL", "localhost"))

ENTORNO_ERROR = "" if ENTORNO else (
    "No se encontraron los datos del sistema de gestión.\n\n"
    f"Se buscó en:\n  • {_LOCAL_BASE}  (esta PC)\n  • {_REMOTE_BASE}  (unidad de red)\n\n"
    f"En ambos se esperaba la carpeta «{SUBRUTA_DBF}».\n"
    "Verificá que la PC servidor esté encendida y la unidad de red conectada."
)
BASE_DATOS = _BASE   # carpeta base elegida (para mostrar en la barra de estado)

# ── Rutas derivadas automáticamente de la base detectada ─────────────────────
_b = Path(_BASE)

DBF_BASE_PATH  = str(_b / "vtiempoges/GESTION/MANA2014")
DBF_HOREB_PATH = str(_b / "vtiempoges/GESTION/HOREB25")

EXCEL_THALAMUS_PATH = str(_b / "Thalamus")
EXCEL_PRECIOS_PATH  = str(_b / "Lista de precios")
EXCEL_LITROS_PATH   = str(_b / "Thalamus/LITROS SHELL.xlsx")
ECHEQ_PATH          = str(_b / "E-cheqs")

# OUTPUT_PATH es local a cada máquina, no depende del base remoto
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "C:/tempdgr")

# Caché local de DBF -> Parquet (acelera el arranque). Local a cada máquina.
CACHE_PATH = os.getenv("CACHE_PATH", str(Path(OUTPUT_PATH) / "cache_dbf"))

# ── Encoding de los archivos DBF ──────────────────────────────────────────────
# Todos los .DBF del sistema de gestión declaran LDID 0x02 en el header, que es
# codepage 850 (MS-DOS Internacional). Decodificarlos como 'latin1' (como se hacía
# antes) rompe caracteres como Ñ (aparecía como '¥'), ° y º. Fuente única de verdad
# para dbfread y para GDAL/DuckDB (ver src/controllers/dbf_io.py).
DBF_ENCODING = os.getenv("DBF_ENCODING", "cp850")

# ── Credenciales BD ───────────────────────────────────────────────────────────
DB_NAME     = os.getenv("DB_NAME",     "pedidosMana")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
