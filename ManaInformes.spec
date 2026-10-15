# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\shell.ico', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\Logo Mana SRL.jpg', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\Logo Mana.jpg', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\LogoMasCalidadMana.jpg', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\calendario.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\IIBB.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\echeq.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\informe.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\gotas.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\compras.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\margen.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\pedidos.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\precio.png', 'src/Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\ui\\estilos.qss', 'src/ui')]
binaries = []
hiddenimports = ['psycopg2', 'psycopg2.extras', 'psycopg2.extensions', 'dbfread', 'dbf', 'duckdb', 'dotenv', 'mplcursors', 'openpyxl', 'openpyxl.cell._writer', 'qtawesome']
datas += collect_data_files('matplotlib')
datas += collect_data_files('pandas')
tmp_ret = collect_all('dbfread')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('dbf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('duckdb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mplcursors')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('qtawesome')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ManaInformes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\shell.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ManaInformes',
)
