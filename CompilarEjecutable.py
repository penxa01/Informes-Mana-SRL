import os
import sys
from pathlib import Path
from PyInstaller.__main__ import run

BASE_DIR = Path(__file__).resolve().parent

# ── Assets: (origen, destino dentro del bundle) ──────────────────────────────
# El destino debe coincidir con la ruta que usa main.py (src/Distribuidora/...)
# para que resource_path() los resuelva correctamente en el ejecutable.
ASSETS_DIR = BASE_DIR / 'src' / 'Distribuidora'
assets = [
    (ASSETS_DIR / 'shell.ico',               'src/Distribuidora'),
    (ASSETS_DIR / 'Logo Mana SRL.jpg',        'src/Distribuidora'),
    (ASSETS_DIR / 'Logo Mana.jpg',            'src/Distribuidora'),
    (ASSETS_DIR / 'LogoMasCalidadMana.jpg',   'src/Distribuidora'),
    (ASSETS_DIR / 'calendario.png',           'src/Distribuidora'),
    (ASSETS_DIR / 'IIBB.png',                 'src/Distribuidora'),
    (ASSETS_DIR / 'echeq.png',                'src/Distribuidora'),
    (ASSETS_DIR / 'informe.png',              'src/Distribuidora'),
    (ASSETS_DIR / 'gotas.png',                'src/Distribuidora'),
    (ASSETS_DIR / 'compras.png',              'src/Distribuidora'),
    (ASSETS_DIR / 'margen.png',               'src/Distribuidora'),
    (ASSETS_DIR / 'pedidos.png',              'src/Distribuidora'),
    (ASSETS_DIR / 'precio.png',               'src/Distribuidora'),
]

ICON = ASSETS_DIR / 'shell.ico'
SEP = ';' if sys.platform == 'win32' else ':'

args = [
    str(BASE_DIR / 'main.py'),
    '--name=ManaInformes',
    '--windowed',          # Sin consola (app GUI)
    f'--icon={ICON}',
    '--noconfirm',         # Sobreescribir dist/ sin preguntar
    '--clean',             # Limpiar caché antes de compilar

    # ── Hidden imports ────────────────────────────────────────────────────────
    # Paquetes que PyInstaller no detecta automáticamente por importación dinámica
    '--hidden-import=psycopg2',
    '--hidden-import=psycopg2.extras',
    '--hidden-import=psycopg2.extensions',
    '--hidden-import=dbfread',
    '--hidden-import=dbf',
    '--hidden-import=dotenv',
    '--hidden-import=mplcursors',
    '--hidden-import=openpyxl',
    '--hidden-import=openpyxl.cell._writer',

    # ── Collect-all: paquetes con datos/metadatos internos ───────────────────
    '--collect-all=dbfread',
    '--collect-all=dbf',
    '--collect-all=mplcursors',
    '--collect-data=matplotlib',
    '--collect-data=pandas',
]

# Agregar todos los assets
for src, dest in assets:
    if not src.exists():
        print(f"[ADVERTENCIA] Asset no encontrado, se omite: {src}")
        continue
    args.append(f'--add-data={src}{SEP}{dest}')

if __name__ == '__main__':
    print(f"Compilando desde: {BASE_DIR}")
    print(f"Assets a incluir: {len([a for a in assets if a[0].exists()])}")
    run(args)
