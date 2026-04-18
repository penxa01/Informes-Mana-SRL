import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, 'frozen', False):
    # Ejecutable compilado: .env debe estar junto al .exe
    _env_base = Path(sys.executable).parent
else:
    # Desarrollo: .env en la raíz del proyecto
    _env_base = Path(__file__).resolve().parents[2]

load_dotenv(_env_base / ".env")

DBF_BASE_PATH  = os.getenv("DBF_BASE_PATH",  "d:/tiempo/vtiempoges/GESTION/MANA2014")
DBF_HOREB_PATH = os.getenv("DBF_HOREB_PATH", "d:/tiempo/vtiempoges/GESTION/HOREB25")

EXCEL_THALAMUS_PATH = os.getenv("EXCEL_THALAMUS_PATH", "d:/tiempo/Thalamus")
EXCEL_PRECIOS_PATH  = os.getenv("EXCEL_PRECIOS_PATH",  "d:/tiempo/Lista de precios")
EXCEL_LITROS_PATH   = os.getenv("EXCEL_LITROS_PATH",   "d:/tiempo/Thalamus/LITROS SHELL.xlsx")

OUTPUT_PATH = os.getenv("OUTPUT_PATH", "C:/tempdgr")
ECHEQ_PATH  = os.getenv("ECHEQ_PATH",  "d:/tiempo/E-cheqs")

DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_NAME     = os.getenv("DB_NAME",     "pedidosMana")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
