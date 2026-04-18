# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\shell.ico', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\Logo Mana SRL.jpg', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\calendario.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\IIBB.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\echeq.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\informe.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\gotas.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\compras.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\margen.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\pedidos.png', 'Distribuidora'), ('D:\\Trabajo\\SoftInformes\\App PyQt5 y Pandas\\src\\Distribuidora\\precio.png', 'Distribuidora')],
    hiddenimports=[],
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
    icon=['Distribuidora\\shell.ico'],
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
