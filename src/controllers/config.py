import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Localizar .env ────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _env_base = Path(sys.executable).parent   # junto al .exe compilado
else:
    _env_base = Path(__file__).resolve().parents[2]  # raíz del proyecto

load_dotenv(_env_base / ".env")

# ── Auto-detección de entorno ─────────────────────────────────────────────────
# Prioridad: local (d:/tiempo) → remoto (Z:/) → fallback a local sin recursos
_LOCAL_BASE = os.getenv("BASE_PATH_LOCAL", "d:/tiempo")
_REMOTE_BASE = os.getenv("BASE_PATH_REMOTE", "Z:")

if Path(_LOCAL_BASE).exists():
    _BASE   = _LOCAL_BASE
    DB_HOST = os.getenv("DB_HOST_LOCAL", "localhost")
elif Path(_REMOTE_BASE + "/").exists():
    _BASE   = _REMOTE_BASE
    DB_HOST = os.getenv("DB_HOST_REMOTE", "DESKTOP-R8E4V7S")
else:
    # Sin conectividad a los recursos; se usa local como fallback
    _BASE   = _LOCAL_BASE
    DB_HOST = os.getenv("DB_HOST_LOCAL", "localhost")

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
